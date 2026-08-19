#!/bin/sh
# Install a kernel apk on the phone, reboot, and report whether the modem
# registers on the network and whether it survives. The fast loop for
# bisecting device-tree experiments (tracker #6). Run on the BUILD HOST.
#
#   tools/modem/try-kernel.sh <path-to-linux-...apk> [label]
#
# Needs: USB networking to the phone at 172.16.42.1, the stand installed
# (modem starts in persistent-low-power, recovery disabled), no FDE.
set -eu
APK=$1; LABEL=${2:-$(basename "$APK" .apk)}
PHONE=${PHONE:-poco@172.16.42.1}
SSH="ssh -i $HOME/.ssh/id_ed25519 -o ConnectTimeout=8 -o BatchMode=yes -o StrictHostKeyChecking=no"
S='echo 1234 | sudo -S -p ""'

echo "==> [$LABEL] install"
scp -q -i "$HOME/.ssh/id_ed25519" "$APK" "$PHONE:/tmp/k.apk"
$SSH "$PHONE" "$S apk add --allow-untrusted /tmp/k.apk >/dev/null 2>&1; SZ=\$(stat -c %s /boot/boot.img); $S dd if=/boot/boot.img of=/dev/disk/by-partlabel/boot bs=1M conv=fsync 2>/dev/null; $S sync; echo written \$SZ"
$SSH "$PHONE" "$S systemctl reboot" >/dev/null 2>&1 || true

echo "==> [$LABEL] waiting for modem"
for i in $(seq 1 30); do
	sleep 5
	IF=$(ls /sys/class/net/ | grep -vE '^(lo|enp1s0|wlo1|docker0|br-|veth)' | head -1)
	[ -n "$IF" ] && { sudo -n ip link set "$IF" up 2>/dev/null; sudo -n ip addr add 172.16.42.2/24 dev "$IF" 2>/dev/null; }
	st=$($SSH "$PHONE" "cat /sys/class/remoteproc/remoteproc0/state" 2>/dev/null || true)
	[ "$st" = running ] && break
done
[ "${st:-}" = running ] || { echo "==> [$LABEL] modem never came up ($st)"; exit 1; }
sleep 10
$SSH "$PHONE" "uname -v | cut -c1-30"

echo "==> [$LABEL] radio online, polling registration"
$SSH "$PHONE" "$S timeout 20 qmicli -d qrtr://0 --dms-set-operating-mode=online 2>&1 | tail -1"
REG=no; CRASH=no
for t in 3 6 10 15 20 30 45 60 90 120; do
	sleep $(( t - ${prev:-0} )); prev=$t
	st=$($SSH "$PHONE" "cat /sys/class/remoteproc/remoteproc0/state" 2>/dev/null || echo unreachable)
	if [ "$st" != running ]; then CRASH="yes at +${t}s"; echo "  +${t}s: modem $st"; break; fi
	r=$($SSH "$PHONE" "$S timeout 10 qmicli -d qrtr://0 --nas-get-serving-system 2>/dev/null | grep -E 'Registration state|MNC:' | head -2 | tr -s ' ' | tr '\n' ' '" 2>/dev/null || true)
	case "$r" in *registered*) REG=yes;; esac
	echo "  +${t}s: running | $r"
done
echo "==> [$LABEL] RESULT: registered=$REG crashed=$CRASH"
