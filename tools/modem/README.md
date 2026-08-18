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
| `captures/` | — | DIAG captures from 2026-08-18: radio with SIM, radio with SIM slot powered off |

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

## Typical run

    # on the phone, over USB, as root, right after boot
    capture-radio.sh /home/poco/modem-captures online

Then pull `/home/poco/modem-captures/<stamp>-online.{bin,log}` and reboot.
