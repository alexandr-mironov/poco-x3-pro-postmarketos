# Cellular on mainline sm8150 (Xiaomi POCO X3 Pro / vayu): the QLINK high-gear wall

**Status:** unresolved. Modem boots, EFS/RF-NV load, the stack reaches **LTE RRC
CONNECTED**, then the modem dies the moment it brings up the high-speed QLINK link
to the RF transceiver. This is a specific, reproducible manifestation of the
sm8150-wide "cellular is non-functional, blamed on firmware" situation — but the
firmware is *not* the cause (see §6), and this device gets **further than the
typical sm8150 case** (it reaches RRC CONNECTED), so it is worth a closer look.

This document records exactly what was tried and ruled out, so nobody repeats it
and so someone with QLINK/RFLM/WTR knowledge can supply the one missing piece.

- Device: Xiaomi POCO X3 Pro, `vayu_global` (M2102J20SG), SM8150 (SD860).
- Kernel: pmOS `soc/qualcomm-sm8150` fork, branch `sm8150/7.0-wip`.
- Modem FW: `MPSS.HE.1.0.c3-00205-SM8150_GEN_PACK-1` (2022-01-03), byte-identical
  to the device's own `modem` partition. **This exact firmware works on Android.**
- Userspace: rmtfs `-P -s` + pd-mapper + tqftpserv; qmicli 1.39; ModemManager 1.25.95.


## 1. The crash

Bringing the radio online:

```
qmicli -d qrtr://0 --dms-set-operating-mode=online
```

kills the modem within ~1 s, every time:

```
qcom_q6v5_pas 4080000.remoteproc: watchdog received:
  rflm_diag_error.cc:368:RFLM@qsf_hl_seq.c:119
  Assertion (rflm_qlnk_ls_retry_cnt < 2) failed
remoteproc remoteproc0: crash detected in modem: type watchdog
```

RFLM = RF Link Manager. QLINK is the high-speed SerDes bus between the modem and
the WTR transceiver. `qsf_hl_seq.c` is the QLINK high/low-speed sequencer;
`rflm_qlnk_ls_retry_cnt < 2` is link-setup (LS) retry exhaustion.


## 2. Key observation — it reaches RRC CONNECTED first (the trigger is TX/high-gear)

A full DIAG F3 capture to the crash shows the LTE RRC state machine reaching
CONNECTED *before* the assert:

```
lte_rrc_stm.c (RRC   -> ...) (INITIAL/LTE_RRC_SEND_UL_MSG_REQI) -> INITIAL
lte_rrc_stm.c (RLCUL -> ...) (WAIT_FOR_RLC_CFG_CNF/LTE_RLCUL_CFG_CNF) -> WAIT_FOR_PDCP_CFG_CNF
lte_rrc_stm.c (CPHY  -> ...) (WAIT_FOR_CONNECTED_CONFIG_CNF/LTE_CPHY_CONN_MEAS_CFG_CNF) -> CONNECTED
```

So the modem finds the cell, does RACH, configures RLC/PDCP and reaches CONNECTED,
**then** crashes when the uplink/high-throughput path activates the high-gear
QLINK. QLINK gears (from resident strings): 8.5 Gbps (cellular default), 3 Gbps,
1.5 Gbps (GNSS). GNSS runs RX-only at 1.5 Gbps and works fine → **GPS works,
every cellular RAT crashes.** The failure is the 8.5 Gbps SerDes training, not
initial bring-up.

Confirmed **RAT-independent**: pinning GSM-only (2G, minimal bandwidth) still
crashes identically — the full transceiver/high-gear QLINK is set up on `online`
regardless of the selected RAT.

The RF scheduler journal (patch author's earlier note) showed "of ten RF devices
brought up over QLINK, exactly one answers and nine never return a result" — i.e.
the QLINK link comes marginally up (one endpoint) but nine time out, then LS retry
trips.


## 3. The mechanism is readable from plain firmware strings (no q6zip needed)

`strings -a modem.mbn` exposes the whole ladder without decompressing anything:

- `qsf_hl_seq.c`, `Assertion (rflm_qlnk_ls_retry_cnt < 2) failed`
- `QSF_HL_SEQ_LS/HS_RETRY_TIMEOUT`
- `retry attempted with 8kv2 family card`, `Retry not supported for 8kv1.x`
- WTR-family enum `RFLM_QLNK_WTR_FAMILY_8KV2`; per-family SerDes-fix scripts
  `rflm_qlnk_wtr_serdes_fix_8KV{1,1_1,1_3,2}_ag.c`. Transceiver identity comes
  from the RFC subsystem (`rf_device_factory.cpp`, `rfc_*.cpp`) via RF-NV
  (`/nv/item_files/rfnv/`) in the modem EFS.

The retry is WTR-family dependent — but which family is detected, and whether the
LS retry fails on **timeout** (WTR not responding → power/reset) vs
**mis-alignment** (SerDes deskew/clock), could **not** be read (see §7).


## 4. What works / how far we got

- Modem PIL boot, EFS via rmtfs (real IMEI reads back), RRC CONNECTED — all fine.
- **ModemManager can fully manage the modem** once the IPA driver is loaded:
  `modprobe ipa` creates `rmnet_ipa0`, and MM then reports
  `modem for device 'qcom-soc' successfully created` (2 ports). (IPA ships
  blacklisted here because MM auto-onlines at boot → the crash → kernel may hang.)
- SIM is detected in the modem's slot 2 under the dual-SIM platform mcfg.

So the *only* blocker is the online → high-gear QLINK crash. Everything downstream
(MM, SIM, data path) is in place.


## 5. Corrected framing — the differing input is on the AP/environment side

The modem firmware is a deterministic program and is **identical** on Android and
mainline (same signed binary in the `modem` partition). It succeeds on Android and
crashes on mainline, therefore **some input to it differs**, and that input is on
our (AP/environment) side. "Signed/unpatchable firmware" only means we cannot work
around a bad input by editing firmware — it does not make the firmware the cause.


## 6. Ruled out — with evidence (please don't repeat these)

| Candidate input / lever | Result |
|---|---|
| RF supplies always-on (PM8150 ldo3/ldo18, PM8150L) | no effect |
| rpmhpd CX/MX/MSS pinned max (`performance 2147483647`) | no effect |
| RPMh RF reference clocks `rf_clk1/2/3` force-held (kernel + DT) | no effect |
| GCC "qlink clkref" | **does not exist** in mainline *or* downstream gcc-sm8150 (only pcie/ufs/usb3 clkref). RF refs are RPMh `rf_clk1/2/3`, modem-voted |
| QLINK pin mux / drive-strength / pull experiments | no effect |
| Modem DT node vs downstream | **identical**: xo, CX+MSS, mpss_mem, `qcom,qmp=<&aoss_qmp>` (AOP load-state present), smp2p, glink |
| Platform mcfg (hw config) | active config == Android's (`la/7+7_mode/sr_dsds`, dual-SIM DSDS). Switching to single-SIM `la/ss` → **identical crash**. Config-independent |
| Firmware provenance | loaded `modem.mbn` == device `modem` partition build (`c3-00205`); matches provisioned RF-NV/TZ |
| EFS/RF-NV delivery | rmtfs serves **zero** blocks during the crash window → input is boot-loaded and correct; no failed serve |
| CPU-PM / electrical timing | cpuidle state0+state1 disabled on all 8 CPUs + performance governor → **identical crash** |
| Driving path | crash is identical via bare `qmicli` and via ModemManager; RAT-independent (GSM-only crashes too) |

Every discrete input equals Android's; every AP-controllable lever is negative.


## 7. What could NOT be determined (and why)

The exact LS-retry reason lives only in DIAG **QShrink terse** messages (type 0x92)
and in the ERR_FATAL path (dmesg only). The terse messages carry a build-assigned
hash, not a computable content hash (tested crc32/fnv1/fnv1a/djb2/sdbm × file/line
variants against 5000 qdb pairs → 0 matches), and the on-hand `qdsp6m.qdb` is a
**different build** (its GUID is absent from `modem.mbn`; one capture hash exceeds
the qdb's max key). The matching-build qdb is a build artifact, not shipped on the
phone. So `timeout` vs `mis-alignment` for the failing SerDes training is **not
recoverable** from any capture we can take, and log 0x1843 (RF scheduler journal)
is not emitted in our DIAG config.


## 8. Conclusion / what would actually help

The differing input sits **below what mainline exposes** — in the vendor RF-init
timing/electrical layer (RPMh/AOP/QLINK bring-up sequencing) that no mainline
resource, clock, regulator, config, PM knob, or driving path reaches. This matches
the sm8150-wide status where cellular is non-functional and attributed to firmware,
except here we can pinpoint the exact failing step.

The single most useful thing anyone can contribute:
1. The **matching-build `qdsp6m.qdb`** for `MPSS.HE.1.0.c3-00205` (or a way to
   compute QShrink-4.0 hashes), to read whether the LS retry fails on timeout vs
   mis-alignment — that discriminates power/reset from clock/deskew.
2. Any Qualcomm/BSP knowledge of what the RIL/BSP does around modem-online that
   mainline does not (an ordered QMI sequence, an RF calibration trigger, a
   thermal/DSDS coordination, or an RPMh/AOP handshake) before the transceiver
   trains at 8.5 Gbps.

If you have gotten cellular past RF bring-up on *any* sm8150 device on mainline,
your firmware version + rmtfs/pd-mapper setup + kernel branch would settle this.


## 9. Reproduce / tooling

- `capture-radio.sh` / `capture2.sh` — one-shot DIAG F3 capture around the crash
  (diag-router registers once per boot; poll for the stream, then `--dms-set-operating-mode=online`).
- `diagcli.py` (DIAG-over-TCP client), `f3parse.py` (decode 0x79 + 0x92-via-qdb).
- `pdc.py` — QMI PDC client to inspect/switch platform (hw) and software (sw) mcfg.
- `modprobe ipa` → `rmnet_ipa0` → ModemManager manages the modem (then it crashes on online).

Full running log of the investigation: `RESUME.md` and `README.md` in this directory.


## 10. Update (2026-08-21) — booted stock MIUI with root and compared

Executed the plan in §8: booted the phone's own stock MIUI (V14.0.3.0.TJUMIXM,
Android 13, Magisk root) and captured the **working** RF bring-up with DIAG
(`/vendor/bin/diag_mdlog -t 0 -f Diag_full.cfg`, all F3 masks on). See
`ANDROID-DIAG-RUNBOOK.md` for the exact procedure.

- Cellular works on the byte-identical modem firmware → confirms, live, that this
  is 100% a mainline AP-side problem (not firmware).
- **Success is silent**: the working high-gear QLINK/SerDes bring-up emits *zero*
  `rflm`/`sdr855`/`qlnk`/`qsf_hl_seq` F3 messages. Those are error-path only. So a
  direct "diff the working DIAG trace against the crash" is impossible — there is
  nothing on the success side to diff.
- AP trigger is identical: the vendor RIL goes online via `RIL_REQUEST_RADIO_POWER`
  → `QMI_DMS set_operating_mode(online)`, plus standard `NAS
  system_selection_preference` — all already exercised by our ModemManager/RAT tests
  with the identical crash. No secret pre-online QMI.
- Obtained the **matching-build modem qdb** (`421e23c4-…`, emitted by `diag_mdlog`),
  which §7 had called unobtainable. It fully decodes MIUI 0x92 terse messages, but
  does **not** contain the RFLM hash set (RFLM is a separate q6zip region), so the
  mainline crash's terse RFLM hashes are still unresolved — timeout-vs-mis-alignment
  remains unreadable.

## 11. Open-code audit (2026-08-21) and the next experiment

Audited the actual AP driver code, mainline vs downstream (`MiCode` `vayu-r-oss`):
- Both delegate MSS bring-up to **TrustZone PAS**; equivalent proxy resources; mainline
  sends the AOP load-state (`qmp_send`). Modem DT nodes are equivalent.
- RFFE/QLINK/WTR pins are set up by **XBL/modem firmware, not Linux** (DT only carries
  board `gpio-line-names` labels, on the working Sony Kumano reference too).
- Therefore the fixable AP-Linux layer has **no missing RF-init step** — it does not
  bring up the WTR/RF at all; that is done pre-Linux by XBL + AOP + the modem, identical
  on Android and mainline. Nothing here is "non-exportable"; the RF code simply isn't in
  the AP layer.

The remaining mechanism is therefore mainline AP-Linux **disturbing** a
firmware-established resource. Cheapest untried test: boot with
**`clk_ignore_unused pd_ignore_unused`** on the kernel cmdline, so Linux does not
disable any boot-enabled clock/power-domain the WTR may depend on but that no mainline
driver claims. (Forcing rf_clk1/2/3 had no effect, but those are modem-RSC-voted; this
is a blanket catch for an AP-side clock we may have missed.)

**Tested 2026-08-21 — NEGATIVE.** Booted pmOS with `clk_ignore_unused pd_ignore_unused`
confirmed active (kernel: "Not disabling unused clocks" / "Not disabling unused power
domains"), drove `qmicli --dms-set-operating-mode=online` → the IDENTICAL
`qsf_hl_seq.c:119 Assertion (rflm_qlnk_ls_retry_cnt < 2)` crash. Keeping all clocks/PDs on
does not help. This is the last AP-side lever; with it disproven, working cellular is not
reachable from the AP layer — the differing input is below what Linux touches (XBL/AOP/
modem-internal). Only remaining track is reading the exact failure reason via deep RFLM
firmware RE, which does not itself produce a fix. See `RESUME.md` for the operational
reflash learnings (dtbo erase, ModemManager mask, boot.img cmdline editing).
