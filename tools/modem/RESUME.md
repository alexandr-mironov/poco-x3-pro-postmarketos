# RESUME — cellular / QLINK reverse (pick-up point)

Last worked: **2026-08-21**. Goal unchanged: make cellular work on vayu/pmOS.

═══════════════════════════════════════════════════════════════════════════════
## ⚠️ CURRENT DEVICE STATE (read first — 2026-08-21)
═══════════════════════════════════════════════════════════════════════════════
**pmOS is WIPED. The phone is currently running rooted stock MIUI**, booted
deliberately for the Android-DIAG comparison (see this session's block below).

- Installed MIUI: **V14.0.3.0.TJUMIXM** (Android 13, vayu_global), Magisk v30.7 root.
  - We flashed `magisk_patched-boot.img` + MIUI `dtbo`/`vbmeta`, did `fastboot -w`,
    then MIUI-recovery "Wipe Data" (host `make_f2fs` failed, so recovery formatted /data).
  - Reach it: `adb` over USB **from the build server** (phone is USB-wired to node1).
    `adb shell su -c '<cmd>'`. Root prompt: open the Magisk app once, grant "shell".
  - `sys.usb.config` reverts to `mtp,adb` (MIUI USB HAL overrides it) — the USB **diag
    port** can't be forced; use `/vendor/bin/diag_mdlog` instead (see session block).
- **super (sda23) is untouched stock MIUI**; `modem` partition (sde52) = the same
  `c3-00205` build mainline loads. Cellular WORKS on MIUI (MTS RUS, LTE, IN_SERVICE).
- To go back to pmOS you must **rebuild + reflash** (see "NEXT ACTION"). pmOS packages
  are already built (`~/.local/var/pmbootstrap/packages/edge/aarch64/`), so it's a
  `pmbootstrap install` + fastboot flash, not a from-scratch build.

═══════════════════════════════════════════════════════════════════════════════
## ▶ STATUS — clk_ignore_unused experiment DONE (2026-08-21): NEGATIVE
═══════════════════════════════════════════════════════════════════════════════
Restored pmOS and tested `clk_ignore_unused pd_ignore_unused`. **It did NOT fix the crash.**
Confirmed active (kernel logged `clk: Not disabling unused clocks` + `PM: genpd: Not
disabling unused power domains`), then `qmicli -d qrtr://0 --dms-set-operating-mode=online`
reproduced the IDENTICAL assert: `rflm_diag_error.cc:368:RFLM@qsf_hl_seq.c:119 Assertion
(rflm_qlnk_ls_retry_cnt < 2) failed`. Keeping every clock/power-domain on makes no
difference → the "mainline disables a WTR clock/PD" hypothesis is DISPROVEN. This
empirically confirms the audit: no AP-side lever reaches the WTR/QLINK bring-up.

**Plan status ("1 → 4"): Option 1 (QMI replicate) disproven; clk_ignore_unused disproven.**
Only Option 4 remains (deep q6zip RE of the RFLM region) — and it only *reads* the failure
reason (timeout vs mis-alignment), it does not fix cellular. Honest bottom line: **working
cellular is not reachable with any available lever** (the sm8150-wide wall, here pinpointed
and proven from DIAG + code audit + live test).

### Operational learnings from the reflash (important — cost us several cycles)
- **After booting MIUI, `fastboot erase dtbo` before flashing pmOS.** MIUI's dtbo overlay
  applied onto pmOS's appended DTB → bootloader `Failed to load/authenticate boot image:
  Load Error` → returns to fastboot. Erasing dtbo fixed it. (pmOS uses `append_dtb`, needs
  no dtbo.) Also re-run `pmbootstrap flasher flash_vbmeta` to restore the disabled vbmeta.
- **ModemManager auto-onlines the modem at boot even with IPA blacklisted** (IPA only gates
  the rmnet DATA port; MM still sets operating-mode online) → RF assert → **userspace/kernel
  hang** on a fresh rootfs. Mask it: `systemd.mask=ModemManager.service` on cmdline (or
  `systemctl mask ModemManager` once booted). The old ipa-blacklist note is insufficient by
  itself on a stand-less image.
- **`deviceinfo_kernel_cmdline` edits don't apply unless the device PACKAGE is rebuilt.**
  `pmbootstrap install`/`flash_kernel` use the cached `device-xiaomi-vayu` apk, so editing
  the source deviceinfo without bumping pkgrel changes nothing. Fast workaround used here:
  edit the cmdline field of the generated boot.img in place (it's plain text at offset 0x40,
  512 B; cmdline is not part of the boot-id hash and AVB is disabled), then `fastboot flash
  boot`. Script: append params, keep the `pmos_boot_uuid`/`pmos_root_uuid`. The staged
  edited image is `~/boot-experiment.img` on the server.
- The `clk_ignore_unused pd_ignore_unused modprobe.blacklist=ipa systemd.mask=ModemManager.service`
  boot is what is currently flashed. Modem crashes only on manual `online` and auto-recovers;
  a fresh image lacks the GPU mitigation (`FD_MESA_DEBUG=sysmem`) so Phosh may freeze the
  screen while the kernel stays up (ping works, ssh may stall after a modem crash).

### To return pmOS to a normal usable state (optional)
Re-flash a stock-cmdline boot (`pmbootstrap flasher flash_kernel` regenerates it without the
experiment params — but keep `systemctl mask ModemManager` or the ipa blacklist to avoid the
boot-online hang), then run `tools/modem/restore-after-reflash.sh` on the phone (rmtfs/stand,
ipa blacklist, `.phoshdebug`). Cellular still won't work — leaving it is fine.

═══════════════════════════════════════════════════════════════════════════════
## 🖥 CONTINUING ON ANOTHER MACHINE (Windows laptop)
═══════════════════════════════════════════════════════════════════════════════
`git pull` carries all the DOCS + tooling in `tools/modem/` and `patches/`. The heavy
assets live on the **build server** (`node1@192.168.1.248`), which the new machine reaches
the same way — so they do NOT need to be in git. To resume seamlessly you must ALSO bring,
outside git (secrets — never commit):
- SSH keys: `~/.ssh/htrex_servers_ed25519` (to the server) and `~/.ssh/id_ed25519` (server→phone).
- `CLAUDE.local.md` (server/phone addresses, paths, the `1234` password) — copy it manually.
- Email rule still applies: commits/patches use
  `7062352+alexandr-mironov@users.noreply.github.com`, never the session `userEmail`.
Everything technical to continue is in this file + `CELLULAR-QLINK-FINDINGS.md` +
`ANDROID-DIAG-RUNBOOK.md`. (Auto-memory under `~/.claude/.../memory/` is machine-local and
will NOT transfer — its essentials are folded into this file.)

═══════════════════════════════════════════════════════════════════════════════
## 📦 SERVER ASSETS staged on node1@192.168.1.248 (2026-08-21)
═══════════════════════════════════════════════════════════════════════════════
- `~/miui-vayu/` — official fastboot ROM (V14.0.3.0.TJUMIXM, 5.58 GB) + extracted
  `boot.img`, `magisk_patched-boot.img`, `dtbo.img`, `vbmeta.img`, `vbmeta_system.img`.
- `~/miui-vayu/cap/` — Android DIAG capture `diag_log_*.qmdl` (66 MB) + **matching-build
  modem qdb** `421e23c4-…​.qdb` (decodes 0x92 terse fully!) + `Diag_full.cfg` (all-F3 mask)
  + `sysfs_regs.txt` (AP regulator map) + `decoded3.txt` (decoded RIL log).
  (The qdb is ALSO copied into the repo working tree as
  `tools/modem/captures/matching-build.qdb` but is NOT committed — Qualcomm-proprietary,
  and the repo mirrors to public GitHub.)
- `~/magisk/` — `qemu-aarch64-static` + Magisk v30.7 unpacked; `boot_patch.sh` pipeline
  VALIDATED (binfmt aarch64 registered; needs `stub.apk` copied into the workdir).
- `~/ksrc/mainline/` — sparse shallow clone of `gitlab.postmarketos.org/soc/qualcomm-sm8150/linux`
  @ `sm8150/7.0-wip` (drivers/remoteproc, drivers/soc/qcom, dts, clk, regulator).
- `~/ksrc/downstream/` — sparse shallow clone of `MiCode/Xiaomi_Kernel_OpenSource` @
  `vayu-r-oss` (same subdirs). Used for the open-code audit.
- `~/diagtools/` — `diagcli-serial.py`, `f3parse.py`.
- Older RE infra still present: `~/modem.mbn`, `~/bin/qemu-hexagon`, `~/llvm-build`,
  `~/ghidra-inst`, `~/cubproj`, `~/qualcomm-q6zip` (see bottom "Staged infra").

═══════════════════════════════════════════════════════════════════════════════
## 2026-08-21 SESSION — Android-DIAG comparison + open-code audit
═══════════════════════════════════════════════════════════════════════════════
Executed the Android-DIAG plan (was the open frontier) and then the open-code AP audit.

**Android-DIAG — three hard results:**
1. Cellular works on the byte-identical modem firmware (MTS RUS, LTE, IN_SERVICE) → 100%
   a mainline AP-side problem, reproduced live.
2. **Success is silent.** Captured working RF/QLINK bring-up with ALL F3 masks on
   (`diag_mdlog -t 0 -f Diag_full.cfg`, streaming mode is mandatory). ZERO
   rflm/sdr855/qlnk/qsf_hl_seq messages — those are ERROR-path only; on mainline we see
   them because it FAILS. ⇒ there is no "working F3 sequence" to diff. DIAG-diff idea CLOSED.
3. AP trigger identical: vendor RIL turns radio on via `RIL_REQUEST_RADIO_POWER` → QMI_DMS
   set_operating_mode(online) = exactly our `qmicli --dms-set-operating-mode=online`. The
   only QMI it adds is standard `NAS system_selection_preference` (mode_pref 28/60, full LTE
   band mask) — already covered by our ModemManager path + RAT-pinning (all → same crash).
   ⇒ **Option 1 (replicate Android's QMI init) has no untested lever; disproven.**

**Correction to the old RESUME:** the "matching qdb is unobtainable" claim (below) is now
OBSOLETE — `diag_mdlog` on the live modem EMITS the matching-build qdb (`421e23c4-…`). It
decodes MIUI 0x92 terse fully (0 unresolved). BUT it does NOT cover the RFLM hashes (RFLM is
a separate q6zip region with its own hash set): decoding our mainline crash with it still
leaves 473 hashes unresolved. So it still can't read timeout-vs-mis-alignment.

**Open-code audit (mainline vs downstream, `~/ksrc`) — the answer to "it's just code, why can't we read it":**
- Modem PIL: mainline `qcom,sm8150-mpss-pas` and downstream `qcom,pil-tz-generic` BOTH
  delegate MSS bring-up to **TrustZone PAS**; equivalent proxy resources (xo, cx, mss);
  mainline additionally holds `aggre2` and sends the AOP load-state (`qmp_send load_state on`
  in `qcom_q6v5.c`). `qcom_pas_handover()` releases proxy px/cx/aggre2/xo/pds on the handover
  IRQ; downstream holds for a fixed `proxy-timeout-ms=10s`. Functionally equivalent (and
  proxy-vote-hold was already tried, 0012, no effect).
- Modem DT node: equivalent (xo, CX/MSS power-domains, mpss_mem, aoss_qmp, smp2p, glink).
- RFFE/QLINK pins: in DT these are only `gpio-line-names` board LABELS (even on the working
  Sony Kumano ref: GPIO61/62=QLINK_REQ/EN, GPIO71-78=RFFE0-3). Actual RFFE/QLINK/WTR pin
  setup is done by **XBL/modem firmware**, not Linux — on mainline AND downstream. Not an
  AP-code diff.
- **Conclusion:** the fixable AP-Linux layer has NO missing RF-init step, because it does not
  bring up the WTR/RF at all. That is XBL + AOP firmware + the modem (all loaded pre-Linux,
  identical on both OSes). Nothing is "non-exportable" — the RF-bringing-up code just isn't in
  the AP layer. So the residual mechanism is mainline AP-Linux **disturbing** a
  firmware-established resource → hence the `clk_ignore_unused pd_ignore_unused` test above.

───────────────────────────────────────────────────────────────────────────────
## (prior sessions below — 2026-08-20 and earlier; historical record)
───────────────────────────────────────────────────────────────────────────────

## Where we are (one line — as of 2026-08-20, superseded by the block above)
The crash mechanism is now **fully decoded from resident firmware strings** — the
q6zip decompression detour turned out to be **unnecessary and is shelved**. The
failure is a **QLINK high-gear (8.5 Gbps) SerDes link-training failure** to the
WTR transceiver (`qsf_hl_seq.c`, assert `rflm_qlnk_ls_retry_cnt < 2`). GNSS at
1.5 Gbps trains fine → GPS works, all cellular RATs crash. Every AP-side resource
is confirmed correct on the phone; the failure is inside the signed, unmodifiable
firmware's WTR SerDes calibration. See README.md section
"The decompression detour was unnecessary" for the full write-up and the exact
strings.

## What this session established (new, decisive)
- `strings -a -t x modem.mbn` reveals the whole ladder: `qsf_hl_seq.c`,
  `Assertion (rflm_qlnk_ls_retry_cnt < 2) failed`, `QSF_HL_SEQ_LS/HS_RETRY_TIMEOUT`,
  `retry attempted with 8kv2 family card`, `Retry not supported for 8kv1.x`.
- WTR-family dependent: enum `RFLM_QLNK_WTR_FAMILY_8KV2`, chips
  `WTR_8K_V1..V1_3/V2`, per-family SerDes-fix scripts
  `rflm_qlnk_wtr_serdes_fix_8KV{1,1_1,1_3,2}_ag.c`. Transceiver identity comes
  from the RFC subsystem (`rf_device_factory.cpp`, `rfc_*.cpp`) via RF NV
  (`/nv/item_files/rfnv/`) in the modem's EFS.
- Cached string dump on host: `~node1/tmp/mstr.txt` (from `strings -a -t x`).

## Ruled out with LIVE evidence on the phone (172.16.42.1)
- `rf_clk1` (38.4 MHz WTR ref from PMIC): **enabled**, claimed by modem as `rf1`.
- CX/MX/MSS rpmhpd: pinned at max (`performance 2147483647`).
- rmtfs `-P -s` + pd-mapper + tqftpserv running; `modemst1/2`, `fsg`, `fsc`
  present → modem has full EFS/RF-NV access.
- Prior in-kernel experiments live: `qcom_q6v5_pas: EXPERIMENT: will hold
  rf1/rf2/rf3`, `keeping proxy votes after handover` → hold-RF-clocks path
  already tried, did not fix cellular.
- ModemManager: `No modems were found` — cellular QMI stack not exposed to
  userspace (no SIM/attach driven; would need bring-up before the crash can even
  be triggered on demand).

## The only remaining piece of DIRECT evidence not yet captured
A live **DIAG F3 trace during a real cellular attach** — to see which WTR family
the modem detects and the exact training step that fails (timeout vs
mis-alignment vs family mismatch). Needs: a SIM, and driving the modem stack far
enough to attempt attach. Tools ready: `diagcli.py` capture + `f3parse.py` with
`qdsp6m.qdb` (QShrink decode). Without a new idea beyond that, cellular is blocked
at the firmware/hardware QLINK layer (PAS auth forbids patching the firmware).

## LIVE-CONFIRMED 2026-08-20 (fresh capture) — reframes the trigger
Drove `qmicli --dms-set-operating-mode=online`; captured full F3 to crash
(`capture-radio.sh online`, saved `~node1/crash.bin`, 1.37 MB). Result:
- dmesg: `watchdog received: rflm_diag_error.cc:368:RFLM@qsf_hl_seq.c:119
  Assertion (rflm_qlnk_ls_retry_cnt < 2) failed` — crash reproduced on demand.
- **The modem reaches LTE RRC CONNECTED first** (`lte_rrc_stm.c`: RLC/PDCP cfg,
  `LTE_RRC_SEND_UL_MSG_REQI`, `-> CONNECTED`), THEN crashes → the trigger is the
  **uplink/TX high-gear (8.5 Gbps) QLINK path**, not bring-up. GNSS is RX-only at
  1.5 Gbps. So the AP-delta to hunt is whatever the **TX/high-gear** path needs.
- Retry reason (timeout vs mis-alignment) NOT readable: `qsf_hl_seq` uses
  ERR_FATAL (dmesg only), and the RF msgs in the F3 stream are all [92] terse.
- **Phone is CRASHED now**; next capture needs a reboot → on-screen LUKS prompt
  (password 1234). Ask the user to reboot+unlock before another one-shot.

## HARDENED 2026-08-20 — two decode/AP-delta hypotheses KILLED (both offline)
1. **Decoding `crash.bin`'s 71 terse [92] hashes is impossible.** The QShrink 4.0
   `<hash>` is a per-build-assigned ID, not a content hash — tested crc32/fnv1/
   fnv1a/djb2/sdbm × 7 string/file/line variants vs 5000 qdb pairs → 0 hits, so it
   is NOT computable from `modem.mbn` strings. The on-hand `qdsp6m.qdb`
   (GUID 421e23c4-…) is a different build: that GUID is absent from `modem.mbn`,
   and one crash hash (4274683767) exceeds the qdb max key (4189073470). qdb files
   are build artifacts, not shipped on the phone → matching qdb unobtainable.
   ⇒ timeout-vs-mis-alignment can never be read from a capture we can take.
2. **No SoC-side QLINK clkref clock exists.** mainline gcc-sm8150 (pmOS 8e126db)
   AND downstream Xiaomi vayu-r-oss gcc-sm8150 both have clkref gates only for
   pcie/ufs/usb3 — none for qlink. RF refs are RPMh `rf_clk1/2/3`+`ln_bb_clk2/3`,
   modem-voted and already force-held by 0013/0014 with no effect. Refuted.

## DT diff DONE 2026-08-20 — modem node fully wired in mainline (NEGATIVE)
Cloned Xiaomi `vayu-r-oss` DTS (`~node1/xiaomi-dts`) and diffed the modem node
against mainline sm8150.dtsi. Every AP-side resource the downstream `pil_modem:
qcom,mss@4080000` provides is present in mainline `remoteproc_mpss:
remoteproc@4080000` (`qcom,sm8150-mpss-pas`):
- xo clock (RPMH_CXO_CLK) — both.
- CX + MSS power (downstream vdd_cx/vdd_mss proxy @TURBO 100 mA ≙ mainline
  rpmhpd SM8150_CX/MSS, already pinned max by the pmOS experiments).
- mpss_mem carveout — both.
- **`qcom,qmp = <&aoss_qmp>`** — the AOP load-state QMP signal IS in mainline
  (downstream `qcom,signal-aop`+`mboxes=<&qmp_aop 0>` "mss-pil"). Hypothesis
  "mainline never tells AOP the modem is up" REFUTED.
- smp2p in/out + glink-edge — both.
The vayu BOARD dts has NO RF PA/LNA/tuner supplies and no WTR/QLINK nodes — the
only RF-adjacent board node is `modem,testing-mode` antenna-ctrl IRQs (tlmm 81,
133; mainline exp 0011 already touched antenna detect). ⇒ No missing AP-side DT
resource for the modem. The failure is inside the signed modem RF/SerDes layer.

## Live re-capture DONE 2026-08-20 — 0x1843 does NOT emit (NEGATIVE)
Two clean on-demand reproductions (`~node1/crash.bin` 1.37MB, `~node1/crash2.bin`
118KB via `capture2.sh` with ver,setall,logall,events). Both crash identically
(qsf_hl_seq.c:119). The RF-scheduler journal LOG 0x1843 is ABSENT in both — the
modem does not emit it in our DIAG config, so the "1-of-10 answers" readout is not
reproducible here (patch 0004's observation came from a different setup). The RF
logs that DO appear (0x192A x91, 0x18A7, 0x18E8, 0x184E, 0x1C6B…) are undocumented
binary with no build-independent parser — eyeballing showed a repeating device
table in 0x192A (`fa/fb/fc..fd` slots) and a band list in 0x18E8, but no reliable
"which device is silent" decode. Live decodable evidence is EXHAUSTED.
Harness lesson: capture-radio.sh's 15s stream gate fires too early; capture2.sh
polls up to 45s and works. diag-router is strictly one-shot per boot
(`/dev/ffs-diag` gone after it exits) → every live capture costs a reboot+LUKS.

## mcfg platform config CHECKED 2026-08-20 — crash is config-INDEPENDENT (NEGATIVE)
Pushed `pdc.py` to phone; queried PDC. Active platform(hw) config id
`00d05894483f4d39074820a4c20bae3122f3e0b4` == sha1 of
`.../mcfg_hw/generic/common/sm8150/la/7+7_mode/sr_dsds/mcfg_hw.mbn` = DUAL-SIM
DSDS 7+7 — i.e. the SAME hw profile Android uses (it lives in device EFS,
untouched). So "mainline doesn't load platform mcfg" is REFUTED: it's present,
active, and identical to Android. Tested the workaround of switching to the
single-SIM profile `la/ss/mcfg_hw.mbn` (`c1073f3a…`): modem boots `running` with
it, but `online` crashes with the IDENTICAL assert (qsf_hl_seq.c:119). ⇒ the
QLINK high-gear crash is INDEPENDENT of the mcfg hw config.
DEVICE STATE LEFT MODIFIED: active platform config is now single-SIM
`c1073f3a…` (persisted in EFS). Reversible when the modem is running:
`pdc.py loadact <la/7+7_mode/sr_dsds/mcfg_hw.mbn> platform` → restores `00d05894`.
Modem is crashed now; revert needs a reboot. `pdc.py` staged at `~poco/pdc.py`.

## Best current answer to "how did it work on Android?"
Not a static resource or config difference — those are all identical/present. The
remaining delta is the BRING-UP SEQUENCE: Android's RIL runs a rich QMI init
(RF calibration triggers, DSDS/thermal coordination, service setup) before/around
going online; our bare `qmicli --dms-set-operating-mode=online` skips it. Modem
reaches RRC CONNECTED (basics work) then fails the high-gear TX QLINK step that
RIL sets up and we don't. Unproven (would require replicating RIL's QMI sequence)
but it's the only surviving explanation.

## IPA/ModemManager path + firmware provenance CHECKED 2026-08-20 (both NEGATIVE)
- Normal pmOS cellular needs ModemManager → needs an rmnet net port → needs the IPA
  driver. IPA (`CONFIG_QCOM_IPA=m`) is BLACKLISTED in `/etc/modprobe.d/ipa.conf`
  (my own prior note: "with IPA up ModemManager brings the modem online at boot, the
  RF assert kills the modem, and the kernel may hang"). Verified: `modprobe ipa` →
  `rmnet_ipa0` → MM restart → "modem successfully created" (2 ports). But driving it
  online (MM or qmicli) hits the IDENTICAL qsf_hl_seq crash. Crash is DRIVING-PATH-
  INDEPENDENT. KEEP ipa blacklisted (else boot hang). Do NOT add modules-load.d/ipa.
- Firmware provenance: `/lib/firmware/.../modem.mbn` and the device `modem` partition
  are the SAME build (`MPSS.HE.1.0.c3-00205-SM8150_GEN_PACK-1`, 2022-01-03) → the
  loaded modem matches the provisioned RFNV/TZ. Not a version mismatch.
- Device state left: dual-SIM cfg `00d05894` PENDING (applies on reboot, restores
  Android baseline + exposes SIM slot 2); ipa blacklisted; modem crashed (needs reboot).

## CPU-PM / electrical-timing experiment 2026-08-20 (NEGATIVE)
Reframe (user's valid logic): same firmware = deterministic; it works on Android and
crashes on mainline, so a differing INPUT on OUR side is the cause — "signed firmware
wall" was wrong framing. Verified ALL discrete inputs identical: firmware build (==
device modem partition, c3-00205), EFS/RFNV (real IMEI, and rmtfs served ZERO blocks
during the crash window → input is boot-loaded & fine), power, clocks, DT, mcfg.
Tested the last AP-controllable knob in the non-discrete (timing/electrical) class:
disabled cpuidle state0+state1 on all 8 CPUs + performance governor, then online →
SAME qsf_hl_seq crash. So the differing input is NOT reachable via any AP resource,
config, PM knob, or driving path we can manipulate. It is real and on our side but
sits below what mainline exposes (vendor RPMh/AOP/RF-init timing). Needs vendor RF
tooling or sm8150-community insight; not solvable with available levers.

## FINAL STATE — no AP resource delta; failure is inside signed RF firmware
Every AP-side lever is now ruled out: power (0004/05/08), clocks incl. clkref
(0013/14 + refuted), pins (0006-10), modem DT node (fully wired, matches
downstream), AOP load-state (present), proxy-vote-hold-after-handover (0013),
EFS/RF-NV (rmtfs serves device-unique partitions). Modem reaches LTE RRC CONNECTED
then fails high-gear (8.5 Gbps) TX QLINK SerDes training to the WTR. Retry reason
(timeout vs mis-alignment) is undecodable (terse-hash decode proven impossible).
Only unfalsified hypothesis: a fine-grained runtime timing/ordering delta, which
cannot be confirmed without the retry reason. Matches the sm8150-wide cellular wall.

## Reaching the phone (Wi-Fi sleeps; USB-net is reliable)
From `node1@192.168.1.248`:
```
IF=$(ls /sys/class/net/ | grep -vE '^(lo|enp1s0|wlo1|docker0|br-|veth)' | head -1)
sudo ip link set $IF up; sudo ip addr add 172.16.42.2/24 dev $IF
ssh -i ~/.ssh/id_ed25519 poco@172.16.42.1   # sudo pw piped: echo 1234 | sudo -S -p '' ...
```

## Staged infra on build host `node1@192.168.1.248` (`sudo` nopasswd)
Kept in case the DIAG-trace path or a future firmware analysis needs it:
- `~node1/bin/qemu-hexagon` (v9.1.0), `~node1/llvm-build/bin/` clang+lld (Hexagon
  target, proven end to end), Ghidra 12.1.3 `~node1/ghidra-inst`, PyGhidra venv
  `~node1/pgvenv`.
- CUB3D project `~node1/cubproj` (name `cub`, QDSP6, relocations applied),
  native project `~node1/ghidra-proj`.
- `~node1/modem.mbn`, `~node1/emu_test.py` (validated PyGhidra EmulatorHelper),
  `~node1/qualcomm-q6zip`, `~node1/ghidra-hexagon-sleigh`.
- `find5.py` (5-arg-call scanner) was **superseded** by the string analysis and
  killed; results not needed.

## Phone / device state (safe to leave)
- Modem firmware stock (`modem.mbn.vayu-orig`); modem `running`.
- rmtfs writable (`-P -s`).
