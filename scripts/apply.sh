#!/bin/sh
# Copy the modified package definitions into a pmbootstrap pmaports checkout.
#
# Only the files this project actually changes are shipped; everything else
# comes from upstream pmaports, so nothing goes stale.
set -eu

REPO_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PMAPORTS=${PMAPORTS:-$HOME/.local/var/pmbootstrap/cache_git/pmaports}

if [ ! -d "$PMAPORTS/device/testing" ]; then
	echo "pmaports checkout not found at: $PMAPORTS" >&2
	echo "Run 'pmbootstrap init' first, or set PMAPORTS to the right path." >&2
	exit 1
fi

echo "pmaports: $PMAPORTS"
echo "commit:   $(git -C "$PMAPORTS" rev-parse --short HEAD 2>/dev/null || echo unknown)"

for f in device-xiaomi-vayu/APKBUILD \
	 device-xiaomi-vayu/deviceinfo \
	 device-xiaomi-vayu/modules-initfs.huaxing \
	 device-xiaomi-vayu/modules-initfs.tianma \
	 linux-postmarketos-qcom-sm8150/APKBUILD \
	 firmware-xiaomi-vayu/APKBUILD
do
	src="$REPO_DIR/pmaports/device/testing/$f"
	dst="$PMAPORTS/device/testing/$f"
	[ -f "$dst" ] && [ ! -f "$dst.orig" ] && cp "$dst" "$dst.orig"
	cp "$src" "$dst"
	echo "  installed $f"
done

# The kernel APKBUILD builds the IPA device-tree change from this patch. It
# lives under patches/upstreamable/ because it targets the kernel tree, not
# pmaports, so put it where abuild expects to find it.
for kp in 0005-arm64-dts-qcom-sm8150-xiaomi-vayu-enable-ipa.patch; do
	cp "$REPO_DIR/patches/upstreamable/$kp" \
		"$PMAPORTS/device/testing/linux-postmarketos-qcom-sm8150/$kp"
	echo "  installed linux-postmarketos-qcom-sm8150/$kp"
done

# Experiment for the modem radio (tracker #6): hold the PM8150L RF LDOs on.
# Lives in patches/local/ because it is not upstream material.
for exp in 0009-vayu-qlink-pins-8mA-pullup-EXPERIMENT.patch; do
	cp "$REPO_DIR/patches/local/$exp" \
		"$PMAPORTS/device/testing/linux-postmarketos-qcom-sm8150/$exp"
	echo "  installed linux-postmarketos-qcom-sm8150/$exp (experiment)"
done

# The kernel APKBUILD no longer references these; upstream still ships them.
for p in 0001-lid-switch-fix.patch 0002-enable-ufs.patch 0003-fix-llvm-build.patch; do
	f="$PMAPORTS/device/testing/linux-postmarketos-qcom-sm8150/$p"
	[ -f "$f" ] && { rm -f "$f"; echo "  removed $p"; }
done

echo
echo "Done. Backups of replaced files are next to them as *.orig."
echo "Next: scripts/build.sh"
