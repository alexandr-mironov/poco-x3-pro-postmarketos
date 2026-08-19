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

## Typical run

    # on the phone, over USB, as root, right after boot
    capture-radio.sh /home/poco/modem-captures online

Then pull `/home/poco/modem-captures/<stamp>-online.{bin,log}` and reboot.
