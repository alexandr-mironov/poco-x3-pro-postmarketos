# Downstream-kernel pmOS port for vayu — the path to WORKING cellular

## Why (decision, 2026-08-21)
Mainline cellular is unsolvable at the AP layer: the modem reaches LTE RRC CONNECTED then
crashes training the **8.5 Gbps high-gear QLINK SerDes to the SDR855** (`qsf_hl_seq.c:119
Assertion rflm_qlnk_ls_retry_cnt < 2`, WMSS revision reads 0x0). Verified from every angle —
DIAG (success is silent), open-code audit (AP-Linux doesn't bring up the WTR; XBL/AOP/modem
do, identically to Android), a live `clk_ignore_unused` test (same crash), and comparison to
every reference: downstream vayu DT, the working-reference sm8150-mainline device realme-x3
(minimal modem node, same carveouts — and its own cellular is NOT in its "Works" list),
sdm845 (prev gen, modem works on mainline but shares the SAME driver/resource data and simply
lacks the high-gear QLINK step), and every sm8150 kernel branch (no modem/qlink/rf commits).
**No public mainline fix exists for sm8150 cellular on any device.**

So: stop chasing a mainline fix. Run the **vendor (downstream msm-4.14) kernel** — which drives
the WTR/QLINK correctly — under pmOS userspace. This is the proven route.

## Feasibility — VALIDATED
- Downstream vayu kernel (MiCode `vayu-r-oss`, msm-4.14.180) exposes the modem over **QRTR +
  GLINK** (`CONFIG_QRTR=y`, `QCOM_QMI_RMNET`, `RPMSG_QCOM_GLINK`) — the same transport mainline
  uses, so **pmOS ModemManager + rmtfs can talk to it** (not Android-rild-only).
- **Droidian's vayu port proves it**: Debian + this downstream kernel + **ModemManager** =
  working cellular. Their adaptation (`github.com/droidian-vayu/adaptation-xiaomi-vayu`) uses
  ModemManager (`ModemManager.service.d/11-ofono-wait.conf`), not rild. pmOS uses the same
  userspace → should work the same.

## Build base (de-risked)
Use Droidian's proven-booting kernel, not a from-scratch msm-4.14:
- Kernel: `github.com/droidian-vayu/linux-halium-xiaomi-vayu` branch `droidian` (cloned to
  server `~/ksrc/dkernel`). msm-4.14.
- Defconfig: **`vayu_lastworking_defconfig`** + fragment **`droidian/common_fragments/droidian.config`**
  (disables `ANDROID_PARANOID_NETWORK` → qrtr/Linux sockets; enables `USB_CONFIGFS_RNDIS` →
  USB-net for ssh; USER_NS, etc. — exactly the "downstream → Linux userspace" gap pmOS needs).
- Toolchain Droidian uses: **clang-r383902** (Android clang ~12) + `aarch64-linux-android-4.9`
  GCC assembler, `CROSS_COMPILE=aarch64-linux-androidkernel-`. Building with the server's
  clang-21 + LLVM_IAS fails (msm-4.14 predates it) — get the real r383902.

## Progress / gotchas found so far
- Config applies: `make O=out vayu_lastworking_defconfig` + `merge_config.sh droidian.config`.
- First build error (server clang): `CROSS_COMPILE_ARM32 not defined` → disable
  `CONFIG_COMPAT_VDSO` (done in out/.config). Expect more compat fixes with a modern clang;
  the r383902 toolchain avoids most.

## Immediate next steps
1. **Get clang-r383902** (gitiles `+archive` is too small for ~1.5 GB — use
   `git clone --depth 1 https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86`
   then checkout the `clang-r383902` dir, or a GitHub mirror) + `aarch64-linux-android-4.9`
   prebuilts. Stage under `~/atc/`.
2. Build `Image.gz` + dtbs with r383902 (`CC=clang CROSS_COMPILE=aarch64-linux-androidkernel-
   CLANG_TRIPLE=aarch64-linux-gnu-`, GCC-4.9 in PATH for the assembler). Iterate compat errors.
3. Package as a pmbootstrap kernel (`linux-xiaomi-vayu-downstream`) — new APKBUILD; source the
   Droidian kernel, apply the config, `deviceinfo_append_dtb`/dtbo per vayu. Consider a new
   device pkg `device-xiaomi-vayu-downstream`, or reuse with the downstream kernel dependency.
4. Userspace: keep rmtfs/pd-mapper/tqftpserv (already in pmOS base), ModemManager, add the
   qrtr/modem udev bits (crib from Droidian `adaptation-xiaomi-vayu/sparse/etc/udev/rules.d/
   70-vayu.rules`). NO ipa blacklist / NO MM mask this time — we WANT MM to bring the modem up.
5. Flash (dtbo matters — downstream uses overlay DT; may need the MIUI/downstream dtbo, unlike
   mainline where we ERASED dtbo), boot, then test: does the modem attach + high-gear QLINK
   succeed (no qsf_hl_seq) under the vendor kernel?

## Fallback if pmOS+ModemManager still won't online the modem
Droidian (or Ubuntu Touch) itself — same kernel, Halium HAL — gives working cellular today.
That's the guaranteed path if the pure-pmOS userspace turns out to need Halium bits.

## Server assets for this
`~/ksrc/dkernel` (Droidian kernel), `~/ksrc/downstream` (MiCode vayu-r-oss full src),
`~/ksrc/mainline` + `~/ksrc/sm8150ml` (mainline trees for reference), `~/ksrc/droidian-adapt`
(Droidian adaptation — modem/udev config to crib), `~/atc/` (toolchain, to be filled).
