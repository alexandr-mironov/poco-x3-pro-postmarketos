#!/bin/sh
# Put the modem test stand onto a running postmarketOS rootfs on vayu.
#
# Run ON THE PHONE as root, from a checkout of this repository copied over
# (scp -r tools/modem poco@<ip>:/tmp/ && ssh poco@<ip> sudo sh /tmp/modem/install-stand.sh).
#
# What it does, and why (issue #1, #2):
#   - keeps the modem radio off at every boot: the RF assert kills the modem
#     within a second of going online, the "online" mode persists in NV, and
#     the WCN3990 Wi-Fi firmware dies with the modem because it lives on the
#     same DSP;
#   - disables remoteproc recovery for the modem: with recovery on, the kernel
#     hangs (RCU stall) when the modem crashes; with it off, the system usually
#     survives with the modem in "crashed";
#   - blacklists the ipa module: with IPA up ModemManager brings the modem
#     online on its own at boot, which is exactly what we must not do yet;
#   - installs the DIAG tooling: patched diag-router and the small DM client.
#
# It does not touch the modem firmware. It is idempotent.
set -eu

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
grep -q 'xiaomi-vayu' /etc/hostname 2>/dev/null || echo "warning: hostname is not xiaomi-vayu, continuing anyway" >&2

install -Dm644 "$HERE/90-mpss-no-recovery.rules" /etc/udev/rules.d/90-mpss-no-recovery.rules
install -Dm755 "$HERE/modem-lowpower.sh"        /usr/bin/modem-lowpower.sh
install -Dm644 "$HERE/modem-lowpower.service"   /etc/systemd/system/modem-lowpower.service
install -Dm644 "$HERE/ipa-blacklist.conf"       /etc/modprobe.d/ipa.conf
install -Dm755 "$HERE/diagcli.py"               /usr/local/bin/diagcli.py
install -Dm755 "$HERE/capture-radio.sh"         /usr/local/bin/capture-radio.sh

if [ -x "$HERE/diag-router/diag-router" ]; then
	install -Dm755 "$HERE/diag-router/diag-router" /usr/local/bin/diag-router
else
	echo "note: tools/modem/diag-router/diag-router binary not present; build it with build-diag-router.sh on the build host" >&2
fi

apk add --quiet qrtr libqmi qmi-utils python3 2>/dev/null || true

systemctl daemon-reload
systemctl enable modem-lowpower.service >/dev/null
udevadm control --reload
# apply the recovery setting to the already-running instance too
[ -w /sys/class/remoteproc/remoteproc0/recovery ] && echo disabled > /sys/class/remoteproc/remoteproc0/recovery || true

echo "stand installed:"
echo "  recovery: $(cat /sys/class/remoteproc/remoteproc0/recovery 2>/dev/null || echo '?')"
echo "  modem-lowpower.service: $(systemctl is-enabled modem-lowpower.service)"
echo "  ipa blacklisted: $(grep -c '^blacklist ipa' /etc/modprobe.d/ipa.conf)"
echo "Reboot once so the modem starts in persistent-low-power."
