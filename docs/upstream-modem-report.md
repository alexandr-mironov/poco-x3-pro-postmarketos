# vayu (POCO X3 Pro): modem registers once the QLINK pins are muxed, then dies before its first TX

Draft for an issue in https://gitlab.postmarketos.org/soc/qualcomm-sm8150/linux
(with a pointer from MR !17). State as of 2026-08-19; full history in the
project tracker (issue #1 and children) and in `tools/modem/` of
https://github.com/alexandr-mironov/poco-x3-pro-postmarketos.

## Setup

- Xiaomi POCO X3 Pro, `vayu_global`, M2102J20SG, Huaxing panel
- postmarketOS edge, systemd, Phosh; kernel `sm8150/7.0-wip` @ 8e126dbc
  plus the DT changes below
- modem firmware: `firmware-xiaomi-vayu` (MPSS.HE.1.0.c3-00161); the stock
  image from the device (00205) behaves the same

## 1. What was wrong, and the fix

Bringing the radio online killed the modem firmware within a second:

    qcom_q6v5_pas 4080000.remoteproc: watchdog received:
      rflm_diag_error.cc:368:RFLM@qsf_hl_seq.c:119
      Assertion (rflm_qlnk_ls_retry_cnt < 2) failed

RFLM = RF link manager, QLINK = the bus to the RF transceiver. The modem's
DIAG log (RF scheduler journal, log 0x1843) showed one RF device answering
and nine never answering.

The cause: gpio61/gpio62 (`qlink_request`/`qlink_enable` in
pinctrl-sm8150) are left in GPIO function. Neither the vendor DT nor the
vendor kernel claims them (the vendor pinctrl table is identical to
mainline's), so on the vendor side the bootloader or TZ must set the mux;
on this device with mainline it is not set. Claiming them through a
pinctrl state on `remoteproc_mpss`:

    &tlmm {
        mss_rf_pins: mss-rf-pins-state {
            qlink-request-pins { pins = "gpio61"; function = "qlink_request"; };
            qlink-enable-pins  { pins = "gpio62"; function = "qlink_enable"; };
        };
    };
    &remoteproc_mpss {
        pinctrl-names = "default";
        pinctrl-0 = <&mss_rf_pins>;
    };

makes the modem bring the RF front end up and **register on the network
(MTS, LTE, MCC 250 MNC 01) within ~3 s of going online** - reproduced on
every kernel carrying the change. `wmss_reset`/`pa_indicator`/`mss_lte`
make no difference. Drive strength and bias: 2 mA / no bias and
function-only behave the same; 8 mA + pull-up makes it never register, so
the line is electrically sensitive.

Question for the list: is anyone else on sm8150 (raphael? OnePlus 7?)
seeing the modem assert in RFLM on radio-on, and would the same pinctrl
state fix it? On sdm845 the same two functions exist and mainline boards
do not claim them, presumably because their bootloaders do.

## 2. What is still wrong

With the pins muxed the modem registers and then asserts again, same
`rflm_qlnk_ls_retry_cnt`, 1-3 s after `registered` (UMTS-only: it searches
happily for ~30 s and dies when it finds a cell). `--nas-get-tx-rx-info`
stays empty until the crash: it dies **before its first TX**, while
reconfiguring the transceiver for the serving cell. Not deterministic
(+1...+10 s, occasionally no registration at all).

Ruled out, one kernel or one run each, all with the pins muxed:

| what | result |
|---|---|
| PM8150L l1/l7/l8/l9 always-on (PA/tuner rails) | no change |
| pm8150 l17 always-on (the one PM8150 LDO the modem does not raise itself) | no change |
| antenna-detect inputs (gpio81/133) pulled up as in the vendor DT | no change |
| PAS keeps cx/mx/mss/xo proxy votes after handover (held at max) | no change |
| PAS holds rf_clk1/2/3 from rpmhcc | no change |
| rmtfs writable (`-P -s`, no `-r`); rmtfs log shows only reads | no change |
| RAT restricted to UMTS | dies when it finds a cell |
| ath10k unloaded before radio-on | worse (dies at +1 s) |
| QLINK pins 8 mA + pull-up | worse (never registers) |

Reading both PMICs over SPMI every 0.5 s around radio-on: the modem raises
pm8150 l3/l6/l10/l11/l15/l16 itself within 0.5 s (so its RPMh votes reach
the PMIC), and nothing drops before the assert. DIAG cannot see the second
crash: the modem does not flush RF logs in those seconds. `DEV_COREDUMP`
is not in the pmOS kernel config, so no remoteproc coredump yet.

Everything the AP can vote for, mux, or hold has been tried. What is left
is on the modem's side of the bus: whatever the second QLINK transaction
talks to (PA/tuner modules on RFFE/GRFC, which on sm8150 are not in TLMM).

Questions: (1) does anyone have a working radio on mainline sm8150, and
if so with which DT? (2) is there anything the AP must set up for
RFFE/GRFC on sm8150 (TCSR, pad control) that mainline may be missing?
(3) the kernel hang on modem crash (RCU stall in the recovery path) is a
separate issue; with `remoteproc0/recovery=disabled` the system survives.
