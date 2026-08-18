#!/bin/sh
# Capture the modem's own DIAG log around the RF assert. One shot per boot.
#
# Run ON THE PHONE as root, over the USB network (Wi-Fi dies with the modem):
#     capture-radio.sh [outdir] [action]
#   outdir  where to put the capture (default /home/poco/modem-captures)
#   action  what to do once the F3 stream is flowing:
#             online   -> set operating mode online (default)
#             nosim    -> power off the SIM slot that holds the card, then online
#             none     -> just capture for a while and stop
#
# Facts this script is built around (issue #1, #2):
#   - the modem registers with DIAG once per boot; a second diag-router in the
#     same boot gets nothing but DEL_CLIENT notices. If diag-router has already
#     run, refuse and ask for a reboot;
#   - diag-router connects OUT to a DM client and exits when that connection
#     closes; so the client must be up first and must outlive the experiment;
#   - a modem in "crashed" must not be talked to (QMI or DIAG) - it hangs the
#     system; refuse if the state is not "running";
#   - the F3 stream only starts after SET_ALL_MSG_MASK; check that data packets
#     actually flow before spending the boot on the experiment.
set -eu

OUT=${1:-/home/poco/modem-captures}
ACTION=${2:-online}
STAMP=$(date +%Y%m%d-%H%M%S)
RPROC=/sys/class/remoteproc/remoteproc0
LOG=/var/log/diag-router.log

die() { echo "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run as root"
[ "$(cat $RPROC/state)" = "running" ] || die "modem is $(cat $RPROC/state), not running - reboot first"
pgrep -x diag-router >/dev/null && die "diag-router already ran in this boot - the modem will not re-register; reboot first"
command -v diag-router >/dev/null || die "diag-router not installed"
command -v qmicli >/dev/null || die "qmicli not installed"

mkdir -p "$OUT"
BIN=$OUT/$STAMP-$ACTION.bin
TXT=$OUT/$STAMP-$ACTION.log
rm -f "$LOG"

echo "==> DM client on 127.0.0.1:2500, capture -> $BIN"
setsid nohup sh -c "python3 /usr/local/bin/diagcli.py 127.0.0.1 2500 '$BIN' 900 ver,setall,logall > '$TXT' 2>&1" >/dev/null 2>&1 </dev/null &
sleep 2
echo "==> diag-router"
setsid nohup sh -c "diag-router -s 127.0.0.1:2500 > '$LOG' 2>&1" >/dev/null 2>&1 </dev/null &
sleep 15

# busybox grep -c prints "0" and exits 1 on no match, so no `|| echo 0` here
N=$(grep -c '\[DBG\] modem data: qrtr type 1' "$LOG" 2>/dev/null); N=${N:-0}
echo "==> F3 packets from modem so far: $N"
[ "$N" -gt 10 ] || die "modem is not streaming (got $N data packets) - this boot is spent, reboot and retry"

case "$ACTION" in
	none)
		echo "==> capturing for 60 s, no radio"
		sleep 60
		;;
	nosim|online)
		if [ "$ACTION" = nosim ]; then
			# The modem numbers slots the other way round from the tray on
			# vayu: the card in physical slot 1 is the modem's slot 2.
			SLOT=$(qmicli -d qrtr://0 --uim-get-card-status 2>/dev/null | awk '/Slot \[/{s=$2} /Card state:.*present/{gsub(/[^0-9]/,"",s); print s; exit}')
			SLOT=${SLOT:-2}
			echo "==> powering off SIM slot $SLOT"
			qmicli -d qrtr://0 --uim-sim-power-off="$SLOT" || die "could not power off SIM"
			sleep 5
		fi
		echo "=== MARK: $ACTION $(date -Iseconds) ===" >> "$TXT"
		echo "==> operating mode online"
		qmicli -d qrtr://0 --dms-set-operating-mode=online || true
		sleep 60
		;;
	*) die "unknown action $ACTION" ;;
esac

echo "==> modem state: $(cat $RPROC/state)"
dmesg | grep -iE 'rflm|watchdog received' | tail -2 || true
echo "==> capture: $(stat -c %s "$BIN") bytes -> $BIN"
echo "    text log -> $TXT"
[ "$(cat $RPROC/state)" = "crashed" ] && echo "Modem crashed. Do not talk to it now; reboot before the next run." || true
