S() { echo 1234 | sudo -S -p '' "$@"; }
echo "=== ядро: $(uname -v | cut -c1-30); модем: $(cat /sys/class/remoteproc/remoteproc0/state); аптайм $(cut -d. -f1 /proc/uptime)с ==="
[ "$(cat /sys/class/remoteproc/remoteproc0/state)" = running ] || exit 1
S timeout 20 qmicli -d qrtr://0 --dms-set-operating-mode=online 2>&1 | tail -1
i=0; while [ $i -lt 40 ]; do sleep 0.5; i=$((i+1))
  st=$(cat /sys/class/remoteproc/remoteproc0/state)
  [ "$st" = running ] || { echo "  +$((i/2)).$((i%2*5))с: $st"; S dmesg | grep -iE "rflm|watchdog received" | tail -1; break; }
  reg=$(S timeout 3 qmicli -d qrtr://0 --nas-get-serving-system 2>/dev/null | grep -oE "'(registered|not-registered[a-z-]*|searching)'" | head -1)
  tx=$(S timeout 3 qmicli -d qrtr://0 --nas-get-tx-rx-info=lte 2>/dev/null | grep -E "TX|Tuned|RSSI|Band|Channel" | tr -s ' ' | tr '\n' ' ' | cut -c1-120)
  echo "  +$((i/2)).$((i%2*5))с: $reg | $tx"
done
echo "=== итог: $(cat /sys/class/remoteproc/remoteproc0/state) ==="
