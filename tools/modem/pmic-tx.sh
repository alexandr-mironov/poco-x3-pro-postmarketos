S() { echo 1234 | sudo -S -p '' "$@"; }
S mount -t debugfs none /sys/kernel/debug 2>/dev/null
[ "$(cat /sys/class/remoteproc/remoteproc0/state)" = running ] || { echo "модем не running"; exit 1; }
rd() { S grep -m1 "^$(printf '%04x' $2):" /sys/kernel/debug/regmap/0-0$1/registers 2>/dev/null | awk '{print $2}'; }
snap() { # все LDO обоих PMIC: STATUS1 (бит7 ready, биты ошибок), компактно
  o=""
  for n in $(seq 1 18); do b=$((0x4000+(n-1)*0x100)); o="$o a$n=$(rd 1 $((b+0x08)))"; done
  for n in $(seq 1 11); do b=$((0x4000+(n-1)*0x100)); o="$o c$n=$(rd 5 $((b+0x08)))"; done
  o="$o s1a=$(rd 1 $((0x1400+0x08))) bob=$(rd 5 $((0xA000+0x08)))"
  echo "$1: $o"
}
S timeout 20 qmicli -d qrtr://0 --nas-set-system-selection-preference=lte >/dev/null 2>&1
snap "до"
S timeout 20 qmicli -d qrtr://0 --dms-set-operating-mode=online >/dev/null 2>&1
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do sleep 0.5; st=$(cat /sys/class/remoteproc/remoteproc0/state); snap "+$((i*5/10)).$((i*5%10))с($st)"; [ "$st" = running ] || break; done
