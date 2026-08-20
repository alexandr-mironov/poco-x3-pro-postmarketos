# Modem test stand for vayu

Everything needed to poke at the cellular modem on postmarketOS without
losing the phone every time it crashes. Background and findings: issue #1
in the project tracker; this directory is issue #2.

## What is in here

| file | goes to | purpose |
|---|---|---|
| `install-stand.sh` | run on the phone as root | installs everything below, idempotent |
| `90-mpss-no-recovery.rules` | `/etc/udev/rules.d/` | `remoteproc0/recovery=disabled` — the kernel hangs (RCU stall) when it tries to recover a crashed modem |
| `modem-lowpower.service`, `modem-lowpower.sh` | systemd, `/usr/bin/` | puts the modem in `persistent-low-power` at every boot; `online` persists in NV and the radio kills the modem within a second |
| `ipa-blacklist.conf` | `/etc/modprobe.d/ipa.conf` | with IPA up, ModemManager brings the radio online on its own at boot |
| `diagcli.py` | `/usr/local/bin/` | minimal DM client: listens for diag-router, sets F3/log masks, dumps the stream |
| `capture-radio.sh` | `/usr/local/bin/` | the one-shot-per-boot experiment: bring up DIAG, verify the modem streams, then `online` / `nosim` / `none` |
| `diag-router/*.patch` | `build-diag-router.sh` | 0001 fixes a SIGSEGV in andersson/diag (upstreamable); 0002 adds the `[DBG]` trace `capture-radio.sh` relies on |
| `diag-router/diag-router` | `/usr/local/bin/` | aarch64 build of the above |
| `build-diag-router.sh` | run on the build host | rebuilds the binary from clean upstream + patches inside the pmbootstrap buildroot |
| `captures/` | — | DIAG captures: 2026-08-18 (radio with SIM / SIM slot off / with log masks, r2 / r3 qlink rails on), 2026-08-19 (r8, QLINK pins muxed) |
| `try-kernel.sh` | run on the build host | install a kernel apk, reboot, bring the radio up, report registered/crashed — the bisect loop |
| `regpoll.sh` | run on the phone | radio online + poll `--nas-get-serving-system` until crash |
| `rat-test.sh` | run on the phone | same, with the RAT restricted first (`umts`, `gsm`, `lte`) |
| `pmic-status.sh`, `pmic-tx.sh` | run on the phone | read regulator status straight from both PMICs over SPMI regmap; `pmic-tx.sh` samples every 0.5 s around radio-on |
| `parse-rf-journal.py` | anywhere | per-RF-device answer counts from log 0x1843 in a capture |
| `restore-after-reflash.sh` | run on the phone | stand + home + stock modem fw + ssh key after a rootfs reflash |

## Rules learned the hard way

- **One experiment per boot.** The modem registers with DIAG once; a second
  `diag-router` in the same boot gets nothing. `capture-radio.sh` refuses to run twice.
- **Never talk to a crashed modem** — no `qmicli`, no DIAG. It hangs the system.
- **Never stop `rmtfs` while the modem runs.** Same result.
- **Work over USB networking** (`172.16.42.1`) for anything that touches the radio.
  The WCN3990 Wi-Fi firmware lives on the modem DSP and dies with it.
- After a crash: reboot. `echo start > remoteproc0/state` from `crashed` returns `EINVAL`.
- SIM slot numbers are reversed between the tray and the modem on this device:
  the card in physical slot 1 is the modem's slot 2.

## Findings so far (2026-08-19)

- The RFLM assert on radio-on is cured by muxing gpio61/gpio62 into
  `qlink_request`/`qlink_enable` via a pinctrl state on `remoteproc_mpss`
  (`patches/local/0007-...`). With that the modem registers (MTS, LTE) within
  3 s. `wmss_reset`/`pa_indicator`/`mss_lte` make no difference.
- It then dies ~3 s after registering (UMTS-only: ~30 s, while searching it is
  fine) - i.e. at the first TX. PM8150L RF LDOs held on do not change that.
- Reading the PMICs around radio-on: the modem raises pm8150 l3/l6/l10/l11/l15/l16
  itself within 0.5 s and leaves l17 (3.0 V, no consumer anywhere) off.
- Ruled out for the second crash, each by a kernel and a run: PM8150L RF LDOs
  on (r8), l17a on (r9), QLINK pins at 8 mA + pull-up (r10 - worse: no
  registration), function-only mux (r11 - same as 2 mA), antenna-detect
  pull-ups (r12), keeping the PAS proxy votes cx/mx/mss after handover (r13 -
  held at max, still dies), unloading ath10k before radio-on (worse).
  `--nas-get-tx-rx-info` stays empty until the crash: the modem dies before
  its first TX, while reconfiguring the transceiver for the serving cell.

### 2026-08-19, evening

- ModemManager `--debug` with IPA up from boot gives the exact sequence:
  `searching (RSSI -73) -> MTS RUS -> registering/LTE, TAC 00A0FC, cell 05BEFD1F
  -> home -> registered -> PS attached` and the modem is dead 20 ms after
  `attached`. Its last indication is DSD System Status: LTE available,
  `so_mask = lte-fdd, lte-ca-dl`, APNs ims/internet.mts.ru/sos. See
  `captures/2026-08-19-mm-debug-attach-crash.log`.
- The modem's EFS is reachable read/write over DIAG: `efs2-client.py` (HELLO,
  OPENDIR/READDIR, OPEN/READ/WRITE/CLOSE) behind `diag-router` via
  `diag-relay.py`; one router per boot, >= 1 s between commands, rmtfs must
  run without `-r` for writes to persist. `/nv/item_files/modem/lte/rrc/cap/`
  holds `disable_cap_ies`, `diff_fdd_tdd_fgi_enable`, `mdt_r10_feature_disable`;
  no `ca_disable` anywhere obvious. Setting `disable_cap_ies` bits 0/1 changed
  nothing (3/3 runs: registered +3 s, crash +6 s); restored to `10 00...`.
- Modem memory cannot be dumped from the AP: `/dev/mem` on mpss_mem blocks
  forever (XPU) and kills the USB gadget; remoteproc minidump is TZ-encrypted
  and the kernel hangs in recovery.

## Typical run

    # on the phone, over USB, as root, right after boot
    capture-radio.sh /home/poco/modem-captures online

Then pull `/home/poco/modem-captures/<stamp>-online.{bin,log}` and reboot.

### 2026-08-19, night — the QLINK gear, and why GNSS is the tell

The second crash is a **QLINK gear-switch failure**, not anything the AP does.
Evidence, in order of weight:

- **GNSS alone runs forever.** `qmicli --loc-start` with the radio in
  persistent-low-power drives QLINK but pins it at its lowest gear (1.5 Gbps,
  `RFLM_QLNK_GEAR_SEL_1p5Gbps`) with no gear switch. Watched two minutes:
  gpio62/QLINK_EN toggling, the modem entering/leaving power collapse
  (`/sys/kernel/debug/qcom_stats/modem`) normally, never a crash. The instant
  LTE registers and the MCPM vote pushes QLINK to a higher gear
  (`rflm_qlnk_gear_switch_mcpm_vote`, up to `_8p5Gbps`), the same
  `rflm_qlnk_ls_retry_cnt < 2` assert fires 2-6 s later. So the low gear is
  stable on this board; the high-speed link is what cannot be established.
- The crash is a **hard timer**, 2-6 s after `online`, independent of: deep
  cpuidle (disabled all states > 0 on every CPU — no change), QMI polling
  (silent 60 s run still crashes), network/RAT, and the modem's own power
  collapse (it keeps sleeping/waking right up to the assert).
- The QLINK PHY supplies are correct: pm8150 l5a (0.88 V) and pm8150l l3c
  (1.2 V) are both HPM, right voltage, matching raphael/hdk. Read live over
  SPMI regmap: MODE=0x07 (HPM), VSET as expected.
- Stock MCFG makes no difference. The modem partition ships
  `image/modem_pr/mcfg/{mcfg_hw,mcfg_sw}`; tqftpserv could not serve it
  (missing from /lib/firmware). Copied it in, and loaded+activated the
  `sm8150/la/7+7_mode` platform config over QMI PDC (`pdc.py` — qmicli 1.39
  segfaults on `--pdc-load-config`). Config activates, modem restarts, still
  crashes on `online`.

The lever we found and have not yet made work: the modem reads
`/rflm_debug/rflm_qlnk_debug.dat` in `rflm_qlnk_efs_get_data` (rflm_cmn_dbg.c),
fields `qsleep_enabled | cdr_logging_enabled | cdr_retrain_enabled`.
`cdr_retrain_enabled` should retrain the QLINK CDR on lane mis-alignment
instead of asserting after two retries. Wrote it as three LE u32
(`00 00 00 00  01 00 00 00  01 00 00 00`), rebooted, still crashes — most
likely the wrong file size (the code checks it exactly; "wrong EFS file size"
is a distinct F3 line) or it is gated behind `/rflm_debug/rflm_debug.txt`
enabling debug. Determining the exact struct size needs Hexagon disassembly of
the modem image (it is QDSP6, not aarch64).

New tools this session:
- `pdc.py` — QMI PDC client over QRTR: list/load/select/activate/delete MCFG
  configs. Finds the PDC service by scraping `qmicli -v` (raw QRTR name-server
  lookups return ENODEV from unprivileged sockets on this kernel).
- `f3parse.py` — decodes F3 debug text from a capture, including QShrink
  (0x92) terse messages via the `qdsp6m.qdb` hash database shipped in the
  modem firmware. Zlib-inflate the qdb, match `<hash>:...:<file>:<fmt>`.

### 2026-08-19, late — the debug-EFS knob, and the RE wall

Tried to make `/rflm_debug/rflm_qlnk_debug.dat` work and to pin its struct:

- Wrote it as three LE u32 (12 bytes) and as three bytes (`01 01 01`), each on
  a clean boot with rmtfs writable, verified the read-back. Both still crash on
  `online` at the same assert. So either the size is still wrong, or the file
  is gated behind `/rflm_debug/rflm_debug.txt` enabling the RFLM debug
  subsystem (not active in a production modem build), or the CDR-retrain knob
  does not prevent this particular link-setup assert.
- Stood up Ghidra 12.1.3 (ships a native Hexagon processor) on the build host,
  driven headless through PyGhidra (`pgvenv`, the bundled wheel + jpype; the
  OSGi Java script engine is broken under JDK 21, PyGhidra is the way).
  Imported and fully analysed `modem.mbn`. Scripts live in `~node1/*.py`.
- Dead end for now: **no code references the path strings by any means Ghidra
  can resolve** — not an absolute `Rx=##addr` const-extender, not a data
  pointer, not for the full path nor its parts. The MPSS is a position-
  independent image the bootloader relocates at load (runtime base 0x8e000000
  vs the ELF's 0xc0800000), so the code's absolute immediates carry *runtime*
  addresses, not the file addresses. Matching them needs the relocation delta
  modelled first — a real RE task, not a quick lookup.

Net: the second crash is a QLINK high-speed-gear link failure in firmware. The
knob that could force the low gear / retrain the CDR lives in the modem's debug
EFS, but is gated or of undetermined layout; reaching it needs either the PIL
relocation worked out in Ghidra, or the RFLM debug subsystem enabled first.
A stale, wrong-sized `/rflm_debug/rflm_qlnk_debug.dat` is left on the device
(the modem ignores it); remove or resize it before the next attempt.

### 2026-08-19, conclusion — a known sm8150 wall

Two more live tests and a look at the wider community settle where this stands:

- **No cellular works on any RAT.** GSM-only crashes at +3 s with the same
  `rflm_qlnk_ls_retry_cnt < 2` assert — same as LTE and UMTS. 2G uses one
  antenna and a tiny sample rate, so this rules out throughput/bandwidth as the
  trigger: the high-speed QLINK link is set up as part of standard WTR bring-up
  for *any* cellular TX/RX ("default gear is 8.5Gbps"), and it fails. There is
  no cellular mode that stays on the stable low gear.
- **This is a known, unsolved sm8150 problem, not a vayu-specific oversight.**
  The OnePlus 7/7 Pro (guacamole, also sm8150) modem is documented
  non-functional on mainline — "the error came from the firmware itself",
  patches not merged. Our diagnosis is more specific than the public record:
  we pinned it to the QLINK high-gear SerDes link modem<->WTR.
- Every AP-side resource we can identify is matched to stock: QLINK pins,
  every RF LDO on both PMICs, rf_clk1/2/3, CX/MSS power-domains, the AOSS QMP
  mailbox (`qcom,qmp` is present in mainline), and the reserved memory regions
  (sm8150 has no separate "Qlink Logging" region — that is sm8650+).

So the second crash is a firmware-side QLINK bring-up failure that the whole
sm8150-mainline effort is stuck on. The levers that might force the low gear or
retrain the CDR live in the modem's RFLM debug subsystem, whose code is
demand-paged/compressed into `d963xxxx` (not in the plain `modem.mbn`
segments), so reaching them is research-grade RE. GNSS is the one RF function
that comes up, because it only ever uses the low QLINK gear.

**Bottom line for issue #1:** cellular on vayu mainline is blocked on the same
QLINK/RFLM firmware wall as the rest of sm8150. Realistic ways past it are all
high-cost: reverse the paged RFLM code to enable its debug and read the failure
mode, find an AP resource nobody has spotted yet, or move with the upstream
sm8150 community. Not a quick fix.

### 2026-08-19, the unlock is Q6ZIP, and it is not hardware

Reframed after community + image evidence: cellular works on stock Android on
this exact unit, the modem firmware is byte-identical, so the hardware is
capable and the gap is AP-side software - not a hardware wall. Every AP
resource we can see matches stock; the missing understanding is *why* the
high-gear QLINK link fails (timeout vs mis-alignment), and that lives in the
RFLM debug F3 stream, which is gated off.

The RFLM code that reads `/rflm_debug/*` and gates its own debug is **not in
the plain `modem.mbn` segments** - it is demand-paged and **Q6ZIP-compressed**
in the modem's dlpager swap pool. Confirmed directly: the image carries
`dlpager_q6zip_iface.c`, `dlpager_swappool.c`, `dlpager_meta.c`, `cache_mmu.c`,
and segment [23] (`c6f20000`, 30 MB, entropy 7.73) is the compressed store;
the runtime decompression target is the `d963xxxx` VA space the resident code
thunks into.

So the path to a fix is concrete, not magic:
1. Decompress the Q6ZIP code with **`nlitsme/qualcomm-q6zip`** (`q6unzip.py`) -
   cloned on the build host at `~node1/qualcomm-q6zip`. It parses the header
   (npages/version, dict1, dict2, ptrlist) but the ptrs are decompression VAs
   (`d963xxxx`), so it needs the dlpager meta mapping and the right dict sizes
   (dict1 ~10-bit, dict2 ~14-bit, lookback ~8-bit) fitted for this ROM.
2. Load the decompressed code into the Ghidra 12.1.3 + PyGhidra env (already on
   the build host) at its `d963xxxx` base, find `rflm_qlnk_efs_get_data` and the
   `rflm_read_debug_file` dbg-command table.
3. That yields the `rflm_debug.txt` command to enable RFLM F3 (so we can read
   the failure mode) and the exact `rflm_qlnk_debug.dat` struct (to try forcing
   the low QLINK gear / CDR retrain).

This is a bounded reverse-engineering task, not an impossibility. It is also
exactly the wall the whole sm8150-mainline effort sits behind, so cracking it
would be broadly useful, not just for vayu.

Reusable infra on the build host: `~node1/ghidra-inst` (Ghidra 12.1.3, native
Hexagon), `~node1/pgvenv` (PyGhidra), `~node1/ghidra-proj` (analysed
`modem.mbn`), `~node1/qualcomm-q6zip`, `~node1/modem.mbn`.

### 2026-08-20, emulation harness: qemu-hexagon built, pipeline mapped

Started the Q6ZIP unpacking via emulation (the robust route). Concrete progress:

- **Built `qemu-hexagon` 9.1.0 from source** on the build host
  (`~node1/qemu-src/build/qemu-hexagon`, copied to `~node1/bin/`). No prebuilt
  exists; quic/toolchain_for_hexagon ships no release assets and there is no
  distro package. Needed flex/bison/glib2-devel and a one-line patch to
  `linux-user/syscall.c` (drop qemu's `struct sched_attr`, use the kernel uapi
  one) for the newer OL9 headers. This is the hard toolchain piece and it works.
- Cloned both toolkits: `~node1/qualcomm-q6zip` (nlitsme) and `~node1/qbb`
  (mzakocs) with the `dlpage_extractor` + inject scripts. Confirmed our modem
  is q6zip (old scheme), which `dlpage_extractor` targets.
- Mapped the compressed layout by immext-referencing (validated decoder):
  - **`c6f01000` (seg22) is the q6zip metadata/section base** — 49 resident
    code sites load `c6f01xxx`; seg23 (`c6f20000`, entropy 7.73) holds the
    compressed blocks (referenced only indirectly).
  - **`0xd0000000` is the decompression output base** (as on Pixel 5).
  - The dlpager page-fault handler is `FUN_c08d98bc` (guards the faulting VA to
    `0xcfffffff..0xd04fa000`, the paged region); it schedules an async page
    load through lock-free work queues (`FUN_c08cede4` -> callbacks
    `DAT_c08cf360/364`).

**Remaining crux:** pin the q6zip decompressor entry (signature
`(out, &out_size, in_block, block_size, dict)` per Check Point's writeup). The
async scheduler defeats static tracing, so the next move is dynamic: hand-craft
a minimal Hexagon entry ELF (illegal-insn at entry -> SIGILL), inject the modem
segments + a `0xd8d00000` output page via `lief`, run under
`qemu-hexagon` in gdb, and test candidate decompressor addresses (regions
`c084xxxx`-`c08dxxxx` and `c0Bxxxxx` per Pixel 5's `c0BAC240`) by calling each
on a seg22 block and checking the output is valid Hexagon. Once the address is
known, dump `0xd0000000..` and load it into the Ghidra env at `d963xxxx`.

### 2026-08-20, harness built; blocked on the Hexagon toolchain

Built the injection harness and probed qemu-hexagon execution. Where it stands:

- `build_harness.py` (on the build host) crafts a runnable ELF: a trap entry
  page at `0x00100000`, every `modem.mbn` LOAD segment mapped at its VA, a
  zero-filled RWX output region at `0xd0000000..0xd2000000`, and scratch at
  `0x40000000`. `qemu-hexagon` loads it (v66 is supported).
- **Blocked on execution, three ways:**
  1. **No Hexagon compiler.** OL9's `llvm`/`clang` (21.1.8) is built without the
     Hexagon target, and `quic/toolchain_for_hexagon` ships no release assets -
     so there is no `hexagon-unknown-linux-musl-clang` to compile the extractor
     stub. Building it from source (LLVM + musl) is the real next step.
  2. **qemu-hexagon runs zero guest instructions** on the hand-crafted ELF -
     `-d in_asm,exec` traces nothing and it exits 1 with no message, so control
     never reaches the entry. Likely a user-mode ELF/guest-base detail; a
     toolchain-produced binary would sidestep it.
  3. **gdb path is out too:** `qemu-hexagon -g` never opens the stub port here,
     and OL9 `gdb` has no Hexagon support anyway.

So the emulation route is sound and the pieces are staged (qemu-hexagon,
harness, both q6zip toolkits, the analysed image in Ghidra), but it is gated on
the **Hexagon LLVM+musl toolchain built from source** - which yields the
extractor compiler, a validated qemu run, and a Hexagon-aware gdb in one go.
That build is the dedicated next chunk. Once it exists: compile a *parametric*
`dlpage_extractor` (decompressor address + section pointers as args), run it
under qemu-hexagon to find the decompressor by testing candidates
(`c084xxxx`-`c08dxxxx`, `c0Bxxxxx`) against a seg22 block, then dump
`0xd0000000` and load it at `d963xxxx` in Ghidra.
