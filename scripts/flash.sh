#!/bin/sh
# Flash postmarketOS to Xiaomi POCO X3 Pro (vayu). Destroys everything on the
# device. The device must already be in fastboot:
#
#   from Android:          adb reboot bootloader
#   from postmarketOS:     buttons only - hold Power 10-15 s, then
#                          Vol Down + Power. `reboot bootloader` does not work
#                          here, it hangs the device.
set -eu

PMB=${PMB:-pmbootstrap}

echo "==> Devices in fastboot"
fastboot devices
[ -n "$(fastboot devices 2>/dev/null)" ] || { echo "No device in fastboot." >&2; exit 1; }

unlocked=$(fastboot getvar unlocked 2>&1 | sed -n 's/^unlocked: *//p' | head -1)
echo "==> Bootloader unlocked: ${unlocked:-unknown}"
[ "$unlocked" = "yes" ] || {
	echo "Bootloader is locked; refusing to flash." >&2
	echo "Note: on a xiaomi.eu ROM the Android properties lie about this," >&2
	echo "but fastboot does not - and fastboot says no." >&2
	exit 1
}

printf 'This erases all data on the device. Continue? [y/N] '
read -r answer
case "$answer" in y|Y|yes) ;; *) echo "Aborted."; exit 1 ;; esac

$PMB shutdown >/dev/null 2>&1 || true

# Must come first. Without an AVB image that has verification disabled the
# bootloader rejects the unsigned boot image: the device shows the POCO splash
# and returns to fastboot.
echo "==> vbmeta"
$PMB flasher flash_vbmeta

echo "==> kernel"
$PMB flasher flash_kernel

echo "==> rootfs (about 100 s, sent in sparse chunks)"
$PMB flasher flash_rootfs

echo "==> rebooting"
fastboot reboot

cat <<'EOF'

The first boot takes up to 8 minutes. Do not conclude it failed before ten.

To reach the device over USB networking from the host:

    IF=$(ls /sys/class/net/ | grep -vE '^(lo|docker0|br-|veth)' | head -1)
    sudo ip link set "$IF" up
    sudo ip addr add 172.16.42.2/24 dev "$IF"
    ssh poco@172.16.42.1

With full disk encryption, the initramfs listens on telnet port 23 for remote
unlocking before the rootfs is mounted; port 22 only opens afterwards.
EOF
