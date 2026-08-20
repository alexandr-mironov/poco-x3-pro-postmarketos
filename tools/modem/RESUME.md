# RESUME — cellular / QLINK reverse (pick-up point)

Last worked: 2026-08-20. Goal unchanged: make cellular work on vayu/pmOS.

## Where we are (one line)
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
