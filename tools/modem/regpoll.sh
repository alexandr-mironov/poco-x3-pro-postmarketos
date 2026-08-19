S() { echo 1234 | sudo -S -p '' "$@"; }
echo "=== ядро: $(uname -v | cut -c1-30); модем: $(cat /sys/class/remoteproc/remoteproc0/state); аптайм $(cut -d. -f1 /proc/uptime)с ==="
[ "$(cat /sys/class/remoteproc/remoteproc0/state)" = running ] || exit 1
S timeout 20 qmicli -d qrtr://0 --dms-set-operating-mode=online 2>&1 | tail -1
prev=0; for t in 3 6 10 15 20 30 45 60 90; do sleep $((t-prev)); prev=$t
  st=$(cat /sys/class/remoteproc/remoteproc0/state)
  if [ "$st" != running ]; then echo "  +${t}s: модем $st"; S dmesg | grep -iE "rflm|watchdog received" | tail -1; break; fi
  r=$(S timeout 10 qmicli -d qrtr://0 --nas-get-serving-system 2>/dev/null | grep -E "Registration state|MNC:" | head -2 | tr -s ' ' | tr '\n' ' ')
  echo "  +${t}s: running | $r"
done
echo "=== итог: $(cat /sys/class/remoteproc/remoteproc0/state) ==="
