#!/bin/sh
# Bring a freshly flashed vayu rootfs back to the modem-debugging state.
#
# Run ON THE PHONE as root with the following already copied to /tmp:
#   /tmp/modem/                 this directory (tools/modem)
#   /tmp/home-poco.tgz          tar of /home/poco (Telegram sessions etc.), optional
#   /tmp/modem-stock.mbn        stock MPSS image squashed from the modem partition, optional
#   /tmp/authorized_keys        SSH key of the build host, optional
set -eu
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

echo "==> stand"
sh /tmp/modem/install-stand.sh

if [ -f /tmp/home-poco.tgz ]; then
	echo "==> home"
	# the tarball has a top-level poco/
	tar xzf /tmp/home-poco.tgz -C /home
	chown -R poco:poco /home/poco
fi

if [ -f /tmp/authorized_keys ]; then
	echo "==> ssh key"
	install -d -m 700 -o poco -g poco /home/poco/.ssh
	install -m 600 -o poco -g poco /tmp/authorized_keys /home/poco/.ssh/authorized_keys
fi

FW=/lib/firmware/qcom/sm8150/Xiaomi/vayu
if [ -f /tmp/modem-stock.mbn ]; then
	echo "==> stock modem firmware (keeping the packaged one next to it)"
	[ -f $FW/modem.mbn.pkg-00161 ] || cp $FW/modem.mbn $FW/modem.mbn.pkg-00161
	install -m 644 /tmp/modem-stock.mbn $FW/modem.mbn
fi

# GPU reset mitigation, see README
[ -f /home/poco/.phoshdebug ] || { printf 'FD_MESA_DEBUG=sysmem\n' > /home/poco/.phoshdebug; chown poco:poco /home/poco/.phoshdebug; }

echo "==> done; reboot so the modem starts in persistent-low-power"
