# Android-DIAG capture runbook (vayu) — compare working MIUI vs mainline QLINK

Goal: boot the phone's own stock MIUI (Android 13, V14.0.3.0.TJUMIXM) with root,
capture a DIAG F3 trace of the **working** cellular bring-up (the high-gear QLINK
SerDes that crashes on mainline), and diff it against our mainline crash log. Same
modem build on both sides (`c3-00205`), so the same messages / QSR table apply.

pmOS is expendable (user consented) — we wipe /data and restore pmOS afterward via
`pmbootstrap install` + reflash (all packages already built).

## Assets already staged on the build server (192.168.1.248, ~/miui-vayu)
- `boot.img`            — genuine stock MIUI boot (downstream `qcom,pil-tz-generic`)
- `magisk_patched-boot.img` — same boot, Magisk v30.7 root (validated under qemu)
- `dtbo.img`, `vbmeta.img`, `vbmeta_system.img` — MIUI, for a clean boot chain
- Toolchain: `~/magisk/` (qemu-aarch64-static + Magisk, binfmt registered)
- DIAG tools: `~/diagtools/diagcli-serial.py`, `~/diagtools/f3parse.py`
- Super (sda23) is intact stock MIUI; modem partition (sde52) = c3-00205 (matches)

Phone is USB-connected to the server. fastboot/adb live on the server (sudo passwordless).

## Step 1 — user: enter fastboot (only manual hardware step)
Programmatic fastboot is impossible on vayu. Power off (hold Power 10–15 s), then
hold **Vol Down + Power** until the fastboot screen. Leave USB connected to server.

## Step 2 — server: flash MIUI boot chain, wipe /data (pmOS), reboot
```sh
sudo fastboot devices
sudo fastboot getvar unlocked            # expect: unlocked: yes
sudo fastboot --disable-verity --disable-verification flash vbmeta        ~/miui-vayu/vbmeta.img
sudo fastboot flash vbmeta_system  ~/miui-vayu/vbmeta_system.img
sudo fastboot flash dtbo           ~/miui-vayu/dtbo.img
sudo fastboot flash boot           ~/miui-vayu/magisk_patched-boot.img
sudo fastboot -w                          # wipe userdata (destroys pmOS rootfs)
sudo fastboot reboot
```
First boot ~2–5 min (formats+encrypts /data).

## Step 3 — user: pass setup, enable USB debugging
Skip through the MIUI setup wizard (language → skip Wi-Fi/Google/etc). Then
Settings → About → tap MIUI version 7× → Developer options → enable USB debugging.
(SIM stays in; modem attaches on its own during/after boot.)

## Step 4 — server: root adb, enable diag, capture
```sh
adb devices                               # authorize the RSA prompt on the phone
adb shell su -c 'getprop | grep -i usb.config'
# primary: expose the Qualcomm DIAG serial port
adb shell su -c 'setprop sys.usb.config diag,adb'
ls /dev/ttyUSB*                           # a diag port should appear on the server
# capture ~60 s while forcing a fresh high-gear attach (toggle airplane mode):
python3 ~/diagtools/diagcli-serial.py /dev/ttyUSB0 ~/miui-diag.bin 60 ver,ssid,setall,logall &
adb shell su -c 'cmd connectivity airplane-mode enable;  sleep 2; cmd connectivity airplane-mode disable'
```
Fallback if the serial port doesn't appear (on-device logger, root):
```sh
adb shell su -c 'ls /vendor/bin/diag_mdlog /system/bin/diag_mdlog /dev/diag'
adb shell su -c 'diag_mdlog -f /data/local/tmp/mask.cfg -o /data/local/tmp/diag -s 200' &
# ...trigger attach..., then stop and pull:
adb pull /data/local/tmp/diag ~/miui-qmdl
```

## Step 5 — decode & diff
```sh
python3 ~/diagtools/f3parse.py ~/miui-diag.bin -g 'qsf_hl_seq|sdr855|qlnk|rflm|ccs_rfc'
```
Compare the working high-gear QLINK/SerDes sequence (WMSS revision reads, LS/HS
retry, LINK_STATUS_UP) against the mainline crash captures in `captures/`. The
step MIUI does that mainline doesn't = the AP-side delta we've been hunting.

## Step 6 — restore pmOS
`adb reboot bootloader` (works from rooted MIUI) → rebuild+flash pmOS:
`pmbootstrap install` (packages built) then flash boot+rootfs per `scripts/flash.sh`.

## Notes / status
- Static analysis is exhausted: the compiled downstream DTB has NO cellular
  RF/QLINK/transceiver node absent from mainline (only `rf_clk3`→wil6210 WiGig,
  disabled). Modem node functionally identical. The delta is runtime-only.
