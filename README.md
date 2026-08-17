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
| Full disk encryption | works, unlocked on-screen |
| Cellular (calls / SMS / data) | untested |
| Camera, GPS | untested |

Full disk encryption is usable as a daily setup, not just as a build artifact: the panel
and the touchscreen both come up inside the initramfs, so `unl0kr` draws the passphrase
prompt and accepts touch input. `lsblk` on the running device shows the root filesystem on
a `crypt` device.

On idle, with Wi-Fi associated and nothing running, a 60 second `tcpdump` of outgoing
traffic captured **zero packets**.

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
./scripts/apply.sh        # install the changed packages into pmaports
./scripts/build.sh        # kernel + image; add --fde for encryption
# put the device in fastboot, then:
./scripts/flash.sh
```

Or by hand:

```sh
pmbootstrap status        # verify device, kernel variant and UI
pmbootstrap checksum linux-postmarketos-qcom-sm8150   # downloads ~250 MB
pmbootstrap build linux-postmarketos-qcom-sm8150 --force
pmbootstrap install --zap # add --fde for full disk encryption

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

**You cannot get back into fastboot from postmarketOS without the buttons.** Every software
route hangs the device rather than rebooting it: `reboot bootloader` and `systemctl reboot`
from the running system, `reboot -f` from the initramfs debug shell, and writing
`bootonce-bootloader` into the `misc` partition — the write lands correctly (verified with
`hexdump`), the bootloader simply ignores it. Recover by holding Power for 10–15 seconds,
then Vol Down + Power. From Android, `adb reboot bootloader` works fine.

**The USB network interface is not called `usb0`.** systemd renames it to something like
`enp4s0f4u1`. Match by exclusion, not by an `usb*` pattern. The host side needs a manual
address:

```sh
sudo ip addr add 172.16.42.2/24 dev "$IF"
ssh poco@172.16.42.1
```

**On a fresh install the clock is decades off, which silently breaks DNS.** Straight after
flashing, this device came up believing it was **4 July 2073**. Every DNSSEC signature is
expired as far as it is concerned, so `systemd-resolved` refuses every answer:

```
resolvectl query github.com
  → resolve call failed: DNSSEC validation failed: signature-expired
ping github.com
  → bad address 'github.com'
```

Direct queries to the router still work, which makes it look like a resolver bug rather
than a clock problem. And it cannot fix itself: NTP needs DNS, DNS needs the right time.
Set the clock once by hand, then let timesyncd take over:

```sh
sudo date -u -s "$(date -u '+%Y-%m-%d %H:%M:%S')"   # from a machine with correct time
sudo systemctl restart systemd-resolved
sudo timedatectl set-ntp true
```

**Wi-Fi has to be configured as root over SSH.** polkit denies a non-interactive session:
`Error: Failed to add/activate new connection: Not authorized to control networking`. Run
`nmcli` under `sudo`. Note that SSIDs are case-sensitive — `AX50` is not `ax50`.

**`pmbootstrap install` prints a false firewall warning.** "Firewall is enabled, but will
not work (no support in kernel config for nftables)" comes from a function that only logs;
it configures nothing. Check reality with `nft list ruleset` on the device instead.

**If a build fails at `Zapping buildroots` with `umount ... exit code 32`**, run
`pmbootstrap shutdown` and retry. Worth doing before every run.

## Full disk encryption

`pmbootstrap install --fde` works, with two caveats that are easy to hit.

**Always pass `--zap` when switching to `--fde`.** Without it pmbootstrap reuses the
rootfs chroot from a previous non-encrypted build, `postmarketos-base-nofde` stays
installed, and the initramfs ends up with no LUKS support at all. The device then boots
into the initramfs debug shell with:

```
ERROR: Detected unsupported 'crypto_LUKS' filesystem (/dev/loop0p2).
Entering debug shell
```

No passphrase prompt appears, because nothing in that initramfs can ask for one. With
`--zap` the correct unlocker (`unl0kr`) is pulled in instead.

**The touchscreen needs its bus controller in the initramfs.** `CONFIG_TOUCHSCREEN_NT36672_SPI`
is built in, but `CONFIG_SPI_QCOM_GENI=m` is a module. Without it `/sys/bus/spi/devices/` is
empty in the initramfs, so the panel lights up and the on-screen keyboard draws, but
nothing responds to touch and the passphrase cannot be typed. Both modules are therefore
listed in `modules-initfs.*`:

```
panel_huaxing_nt36672
spi_geni_qcom
```

If you do get locked out at that prompt, you are not stuck: the initramfs brings up USB
networking and listens on **telnet port 23** for remote unlocking. Port 22 only opens once
the rootfs is mounted, so the open port tells you which stage the device is at.

## The compositor crash

Out of the box the session dies every so often and drops you back to the greeter — which
is easy to mistake for a lock screen, except the greeter has no user locale, so the
language changes too. It is `phoc` segfaulting, and it takes the session with it:

```
#0 wlr_render_pass_add_texture    wlroots-0.20.x/render/pass.c:23
#1 view_render_to_buffer_iterator src/render.c:430
#4 thumbnail_frame_handle_copy    src/phosh-private.c:450
```

`view_render_to_buffer_iterator()` checks that a surface has a buffer but not that a
texture could be obtained from it; `wlr_surface_get_texture()` can still return NULL, and
`wlr_render_pass_add_texture()` dereferences it immediately. The path is reached whenever
the shell asks for window thumbnails, which is to say every time you open the overview.

`patches/upstreamable/0003-*.patch` adds the missing NULL check. It applies to phoc
itself, not to pmaports; build it with a local port and install with
`apk add --allow-untrusted`, then `systemctl restart greetd` to pick it up.

**That patch is a seatbelt, not a cure.** It stops the compositor from dying, but the
reason a surface has no texture is further down: the GPU is faulting and being reset.

```
*** gpu fault: iova=0x10b560000 dir=READ type=TRANSLATION source=CCU (0,0,0,1)
adreno 2c00000.gpu: [drm:a6xx_irq] *ERROR* gpu fault ring 0 fence 144fe status 00800005
msm_dpu ae01000.display-controller: [drm:recover_worker] *ERROR* hangcheck recover!
                                     offending task: phoc
phoc: [render/gles2/pass.c:315] GPU reset (guilty)
phoc: Re-creating renderer after GPU reset
```

The Color Cache Unit reads an address that is not mapped in the GPU's page tables, the
hangcheck fires, the kernel resets the GPU, and every texture dies with it. phoc rebuilds
its renderer but client surfaces are left without textures — which is what the NULL check
above then survives. `offending task: phoc` names the submitter, not the culprit; the bug
is in Mesa/freedreno or in the msm kernel driver.

With the patch the session stays alive, but the display is visibly wrong afterwards:
the wallpaper disappears, and another window's contents can end up drawn as the
background until that window is closed. Environment at the time of writing: Mesa 26.1.6,
Adreno 640 (FD640), kernel 7.0.0-sm8150.

## Repository layout

```
README.md                     this file
TZ-pmos-vayu.md               full walkthrough, in Russian
pmaports/                     the changed package definitions, ready to copy in
scripts/apply.sh              install them into your pmaports checkout
scripts/build.sh              build kernel and image, with sanity checks
scripts/flash.sh              vbmeta, kernel, rootfs, in the right order
patches/pmaports-full.diff    the same changes as a diff
patches/upstreamable/         two clean patches suitable for pmaports as-is
patches/local/                the kernel pin to a WIP branch snapshot; not upstreamable
```

Only the files this project actually changes are vendored under `pmaports/`. Everything
else comes from upstream pmaports, so nothing here goes stale behind your checkout.

The two patches under `patches/upstreamable/` do not depend on the WIP kernel branch and
are useful on their own. The kernel change pins a commit from a work-in-progress branch,
which is fine locally but is not something pmaports would carry — that has to wait for a
stable 7.0 tag.

## Credits

The vayu port is the work of its postmarketOS maintainers; MR !17 in the sm8150 kernel
tree is what makes any of this possible. This repository only documents how to assemble
the pieces as they stand today.
