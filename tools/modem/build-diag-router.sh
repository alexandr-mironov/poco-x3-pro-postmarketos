#!/bin/sh
# Build diag-router (andersson/diag) for aarch64 inside the pmbootstrap
# buildroot and drop the binary into tools/modem/diag-router/.
#
# Run on the build host that has pmbootstrap set up for vayu.
# Applies the two patches from tools/modem/diag-router/: the NULL-range fix
# (upstreamable) and the QRTR debug trace (stand only).
set -eu

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PMB=${PMB:-pmbootstrap}
CHROOT=$($PMB config work 2>/dev/null | tail -1)/chroot_buildroot_aarch64
SRC=/tmp/diag-build

$PMB -y chroot -b aarch64 -- apk add --quiet build-base git qrtr-dev eudev-dev linux-headers
$PMB -y chroot -b aarch64 -- sh -c "rm -rf $SRC && git clone --depth 1 https://github.com/andersson/diag.git $SRC"
# the chroot is owned by root
sudo cp "$HERE"/diag-router/*.patch "$CHROOT$SRC/"
# `set -e` inside the chroot shell: a patch that does not apply must stop the build,
# not leave a silently unpatched binary behind.
$PMB -y chroot -b aarch64 -- sh -ec "cd $SRC && for p in 0001-*.patch 0002-*.patch; do patch -p1 --forward < \$p; done && grep -q 'if (range)' router/peripheral.c && make"
sudo cp "$CHROOT$SRC/diag-router" "$HERE/diag-router/diag-router"
sudo chown "$(id -u):$(id -g)" "$HERE/diag-router/diag-router"
echo "built: $HERE/diag-router/diag-router"
