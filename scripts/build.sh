#!/bin/sh
# Build the kernel and the postmarketOS image for Xiaomi POCO X3 Pro (vayu).
#
# Usage:
#   scripts/build.sh          plain image
#   scripts/build.sh --fde    full disk encryption
#
# Run scripts/apply.sh first.
set -eu

PMB=${PMB:-pmbootstrap}
FDE=""
[ "${1:-}" = "--fde" ] && FDE="--fde"

echo "==> Checking configuration"
$PMB status
case "$($PMB config device 2>/dev/null | tail -1)" in
	xiaomi-vayu) ;;
	*) echo "Device is not xiaomi-vayu. Run 'pmbootstrap init'." >&2; exit 1 ;;
esac
case "$($PMB config kernel 2>/dev/null | tail -1)" in
	huaxing|tianma) ;;
	*) echo "Kernel variant must be huaxing or tianma." >&2; exit 1 ;;
esac

# Stale mounts from an earlier run make the next build fail during
# "Zapping buildroots" with 'umount ... exit code 32'.
echo "==> Releasing stale chroots"
$PMB shutdown >/dev/null 2>&1 || true

echo "==> Checksums for the kernel package (downloads ~250 MB on first run)"
$PMB checksum linux-postmarketos-qcom-sm8150

echo "==> Building the kernel (about 45 min cold, about 10 min with warm ccache)"
$PMB build linux-postmarketos-qcom-sm8150 --force

APK=$(ls -t "$($PMB config work 2>/dev/null | tail -1)"/packages/*/aarch64/linux-postmarketos-qcom-sm8150-*.apk 2>/dev/null | head -1)
if [ -n "${APK:-}" ]; then
	echo "==> Verifying the built kernel package"
	for want in panel-huaxing-nt36672.ko panel-tianma-nt36672.ko \
		    sm8150-xiaomi-vayu-huaxing.dtb spi-geni-qcom.ko; do
		if tar tzf "$APK" 2>/dev/null | grep -q "$want"; then
			echo "  ok      $want"
		else
			echo "  MISSING $want" >&2
			echo "  The sm8150.config fragment probably was not merged." >&2
			exit 1
		fi
	done
fi

echo "==> Building the image${FDE:+ (encrypted)}"
# --zap matters: without it pmbootstrap reuses the previous rootfs chroot.
# Switching to --fde on a reused chroot leaves postmarketos-base-nofde in
# place, the initramfs ends up without LUKS support, and the device drops
# into a debug shell with "Detected unsupported 'crypto_LUKS' filesystem".
$PMB install --zap $FDE

echo
echo "Done. Next: put the device in fastboot and run scripts/flash.sh"
