# postmarketOS on Xiaomi POCO X3 Pro (`vayu`)

A working recipe for installing postmarketOS (Phosh) on the Xiaomi POCO X3 Pro,
including the pmaports changes needed to get there.

As of **2026-08-17**, picking `vayu` in `pmbootstrap init` and following the normal
installation flow does **not** produce a bootable system. This repository documents why,
and what to change.

## Status

Verified on real hardware: Xiaomi POCO X3 Pro, `vayu_global`, model M2102J20SG,
**Huaxing** panel, kernel `7.0.0-sm8150`, postmarketOS edge with systemd.

| | |
|---|---|
| Display (1080×2400) | works |
| Touchscreen | works |
| GPU (Adreno 640) | works |
| Battery / charging | works |
| Wi-Fi adapter | detected |
| Bluetooth | detected |
| USB networking + SSH | works |
| nftables firewall | works |
| Phosh on Wayland | works |
| Full disk encryption | image builds, LUKS confirmed |
| Cellular (calls / SMS / data) | untested |
| Camera, GPS | untested |

The only failing systemd unit is `qbootctl.service`, which manages A/B boot slots. `vayu`
is not an A/B device, so this is expected.

## The three problems

### 1. The kernel package cannot build the device tree the device package asks for

`device-xiaomi-vayu` requires `qcom/sm8150-xiaomi-vayu-huaxing.dtb`. Its declared kernel,
`linux-postmarketos-qcom-sm8150` 6.17.0, is built from a tarball of
`gitlab.com/sm8150-mainline/linux` — a repository that contains **no vayu device tree in
any tag or branch**.

Support lives only in `gitlab.postmarketos.org/soc/qualcomm-sm8150/linux`, branch
**`sm8150/7.0-wip`** (MR !17, "Reintroduce Xiaomi POCO X3 Pro (vayu)", merged 2026-06-27,
commit `8e126dbc`). An equivalent MR against the stable `sm8150/6.18` branch was closed.

Symptom:

```
ERROR: Unable to find qcom/sm8150-xiaomi-vayu-huaxing.dtb in the following locations:
    - /boot/dtbs*
    - /usr/share/dtb/
```

See `patches/local/0003-kernel-build-from-sm8150-7.0-wip.patch`.

### 2. The kernel config silently disables the panel and touchscreen drivers

This is the one that costs the most time, because **it produces no error message at all**.

The `sm8150/7.0-wip` branch introduces config symbols that did not exist before:

```
CONFIG_DRM_PANEL_HUAXING_NT36672=m
CONFIG_DRM_PANEL_TIANMA_NT36672=m
CONFIG_TOUCHSCREEN_NT36672_SPI=y
```

Building with the pmaports config (written for 6.17) means `make olddefconfig` sets all
three to their default, which is off. The fix is to merge the in-tree fragment
`arch/arm64/configs/sm8150.config` on top of the pmaports config.

Why it is silent: `drm/msm` is assembled through the component framework. Without a panel
driver, the `dsi@ae94000` node never completes, so the master never binds, no DRM card is
created, and nothing is logged. `/sys/kernel/debug/devices_deferred` is empty too.

What you see instead:

- `/sys/class/drm/` contains only `version` — no `card0`
- `/sys/class/graphics/fb0/name` is `simple` — that is the framebuffer the bootloader left
  behind, not a driver of yours
- backlight is on (`bl_power = 0`), so the screen glows black rather than staying dark

Note that `merge_config.sh` cannot be used inside the Alpine build chroot: it needs GNU
`readlink -m`, and busybox does not have it.

### 3. Flashing without `vbmeta` leaves the device in fastboot

AVB rejects the unsigned boot image. The device shows the POCO splash and returns to
fastboot. `pmbootstrap flasher flash_vbmeta` writes an AVB image with the
verification-disabled flag, but deviceinfo does not name the partition, so the command
refuses to run. See `patches/upstreamable/0001-*.patch`.

Erasing `dtbo` is **not** required — tested, it makes no difference.

## Recipe

```sh
pmbootstrap init          # xiaomi / vayu / huaxing / phosh
pmbootstrap status        # verify device, kernel variant and UI

# apply the patches from patches/ to your pmaports checkout, then:
pmbootstrap checksum linux-postmarketos-qcom-sm8150   # downloads ~250 MB
pmbootstrap build linux-postmarketos-qcom-sm8150 --force
pmbootstrap install       # add --fde for full disk encryption

# device in fastboot:
fastboot getvar unlocked                  # must be yes
pmbootstrap flasher flash_vbmeta          # required, do this first
pmbootstrap flasher flash_kernel
pmbootstrap flasher flash_rootfs
fastboot reboot
```

Kernel build time: about 45 minutes cold, about 10 minutes with a warm ccache
(16 threads, `pmb:cross-native`, no emulation).

## Things worth knowing

**The first boot takes up to 8 minutes.** Do not conclude it failed before ten. It is easy
to mistake a live system for a dead one.

**Identify your panel from postmarketOS itself**, no root and no bug report needed:

```sh
sudo dmesg | grep -o 'msm_drm.dsi_display0=[^ ]*'
# dsi_j20s_42_02_0b_video_display  -> Huaxing
# dsi_j20s_36_02_0a_video_display  -> Tianma
```

**On a xiaomi.eu ROM the Android bootloader properties lie.** `ro.boot.flash.locked=1` and
`ro.boot.verifiedbootstate=green` are spoofed to pass SafetyNet, so an unlocked device
looks locked. Only `fastboot getvar unlocked` tells the truth. Mistaking this for a locked
bootloader costs a week of Mi Unlock waiting for nothing.

**`reboot bootloader` does not work from postmarketOS.** The system halts without passing
the command to the bootloader and the device hangs. Recover by holding Power for 10–15
seconds, then Vol Down + Power. From Android, `adb reboot bootloader` works fine.

**The USB network interface is not called `usb0`.** systemd renames it to something like
`enp4s0f4u1`. Match by exclusion, not by an `usb*` pattern. The host side needs a manual
address:

```sh
sudo ip addr add 172.16.42.2/24 dev "$IF"
ssh poco@172.16.42.1
```

**`pmbootstrap install` prints a false firewall warning.** "Firewall is enabled, but will
not work (no support in kernel config for nftables)" comes from a function that only logs;
it configures nothing. Check reality with `nft list ruleset` on the device instead.

**If a build fails at `Zapping buildroots` with `umount ... exit code 32`**, run
`pmbootstrap shutdown` and retry. Worth doing before every run.

## Repository layout

```
README.md                     this file
TZ-pmos-vayu.md               full walkthrough, in Russian
patches/pmaports-full.diff    everything, as applied
patches/upstreamable/         two clean patches suitable for pmaports as-is
patches/local/                the kernel pin to a WIP branch snapshot; not upstreamable
```

The two patches under `patches/upstreamable/` do not depend on the WIP kernel branch and
are useful on their own. The kernel change pins a commit from a work-in-progress branch,
which is fine locally but is not something pmaports would carry — that has to wait for a
stable 7.0 tag.

## Credits

The vayu port is the work of its postmarketOS maintainers; MR !17 in the sm8150 kernel
tree is what makes any of this possible. This repository only documents how to assemble
the pieces as they stand today.
