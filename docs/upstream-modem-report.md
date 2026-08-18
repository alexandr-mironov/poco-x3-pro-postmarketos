# vayu (POCO X3 Pro): modem crashes in RFLM the moment the radio goes online

Draft for an issue in https://gitlab.postmarketos.org/soc/qualcomm-sm8150/linux
(and a pointer from MR !17). Written 2026-08-18; see the project tracker
issue #1 for the full history.

## Setup

- Xiaomi POCO X3 Pro, `vayu_global`, M2102J20SG, Huaxing panel
- postmarketOS edge, systemd, Phosh
- kernel `sm8150/7.0-wip` @ 8e126dbc (`linux-postmarketos-qcom-sm8150` 7.0.0),
  plus two local DT changes described below
- modem firmware: tried both `firmware-xiaomi-vayu` (MPSS.HE.1.0.c3-00161)
  and the stock image from the device's `modem` partition
  (MPSS.HE.1.0.c3-00205, squashed from modem.mdt/.bNN); identical result

## What works

remoteproc brings the modem up, rmtfs and pd-mapper run, QMI over QRTR
answers, IMEI is readable, the SIM is seen (note: the modem's slot numbers
are the reverse of the tray on this device). With IPA enabled in the DT and
`ipa_fws.mbn` installed, ModemManager creates the modem, enables it and moves
it to `searching`.

## What breaks

Setting the operating mode to `online` - via ModemManager, `qmicli
--dms-set-operating-mode=online`, or automatically at boot once `online` has
been persisted in NV - kills the modem firmware within about a second:

    qcom_q6v5_pas 4080000.remoteproc: watchdog received:
      rflm_diag_error.cc:368:RFLM@qsf_hl_seq.c:119
      Assertion (rflm_qlnk_ls_retry_cnt < 2) failed
    remoteproc remoteproc0: crash detected in modem: type watchdog

The kernel then usually hangs (RCU stall) in the recovery path; with
`remoteproc0/recovery=disabled` the system generally survives with the modem
in `crashed`. Wi-Fi (WCN3990 firmware on the same DSP) dies with it.

Reproducible on every attempt, with the SIM slot powered off as well.

## Ruled out by experiment

| hypothesis | test | result |
|---|---|---|
| IPA is involved | radio on with the `ipa` module not loaded | same crash |
| modem firmware vs calibration mismatch | stock MPSS 00205 from the device | same crash |
| `rmtfs -r` blocks EFS writes | `rmtfs -P -s` (writable) + verbose log | same crash; the modem does not touch EFS when the radio comes up |
| kernel gates unused clocks/PDs | `clk_ignore_unused pd_ignore_unused` | same crash |
| TX / network registration | SIM slot powered off (`--uim-sim-power-off`) | same crash |
| AOSS: keep CX/DDR from collapsing | `qcom_aoss` debugfs knobs | the sm8150 AOSS firmware NAKs `cx_mol`/`ddr_mol`/`aoss_slp`; QMP itself works |

## What the modem itself says (DIAG)

We built `diag-router` (andersson/diag) for aarch64 over QRTR (it needs a
one-line fix for a NULL deref on SET_ALL_MSG_MASK; patch available) and
captured F3 messages and logs around the crash.

Log 0x1843 is the RF scheduler journal: 28-byte records
`id(2) flags(2) a(4) b(4) c(4) ts(4) pad(8)`, the high byte of `id` being the
RF device number. Across three snapshots before the assert:

    device | records | with a result (b/c != 0)
       3   |   125   |   82
    1,4,6,7,8,9,10,11,12 | 108 | 0

One RF device answers; nine never return a result to any command
(`op 0x07/0x12/0x14/0x15/0x28/0x29`), and the same command sequence is
re-issued to devices 1/4/9/10 in lockstep about a second later - the retry
the assert counts.

Meanwhile other subsystems get surprisingly far while the SIM is active:
RF tune, cell found, SIB1 decoded (MCC 250 MNC 20), LTE ML1/RRC state
machines running, APN/IMS profiles - so the logic is fine; the RF front end
behind QLINK is what does not respond.

## Where we ended up

On the AP side the QLINK supplies are ldo5/PM8150 (`vdda_qlink_lv`,
`vdda_qlink_lv_ck`) and ldo3/PM8150L (`vdda_qlink_hv_ck`) - the vayu board
file already labels them so. ldo5 stays on because the USB PHY consumes it;
ldo3 had no consumer and RPMh reported it disabled. The vendor tree also
defines pm8150_l18 (880-912 mV, RF), missing from the mainline board file.

We held both on (`regulator-always-on`; confirmed `enabled` by the regulator
framework, ldo3 at 1.2 V, ldo18 at 0.88 V) and brought the radio up again:
**same assert, same journal** - one RF device answers, the rest never do.
So the QLINK rails as the AP sees them are not what keeps the front end
silent.

Everything the kernel controls that could feed the front end has now been
compared with the vendor tree or tested: modem PIL node (pas-id 4, ssctl
0x12, smem 421, xo/cx/mss, signal-aop - identical), regulators (all
RPMH_REGULATOR_SET_ALL, none always-on in the vendor tree either), RF clocks
(the kernel touches none of them on either side), pinctrl (no RF/GRFC pins
on either side). What is left is what goes from the modem to the hardware
without the AP: RFFE/GRFC and the modem's own RPMh votes.

Questions for people who know the sm8150 RPMh/AOSS side:

1. Does anyone have a working cellular radio on mainline sm8150 (any board)?
   Which modem firmware, and are RF rails held by the AP or left to the modem?
2. On this board the modem's RF front end does not answer over QLINK/RFFE even
   with the AP-visible QLINK rails forced on. Is there anything the AP has to
   set up for RFFE/GRFC on sm8150 (TCSR, TLMM, PDC) that mainline may be
   missing, or anything in RSC/cmd-db that would keep the modem's own votes
   from reaching the PMIC?
3. The kernel hang on modem crash (RCU stall in the recovery path) looks like
   a separate bug worth its own report - is it known?

Logs, captures and the DIAG tooling are in the project repository under
`tools/modem/`.
