S() { echo 1234 | sudo -S -p '' "$@"; }
MODE=${1:-umts}
[ "$(cat /sys/class/remoteproc/remoteproc0/state)" = running ] || { echo "модем не running"; exit 1; }
echo "=== ограничиваю RAT: $MODE ==="
S timeout 20 qmicli -d qrtr://0 --nas-set-system-selection-preference="$MODE" 2>&1 | tail -1
S timeout 15 qmicli -d qrtr://0 --nas-get-system-selection-preference 2>&1 | grep -E "Mode preference|Acquisition" | head -2
echo "=== online ==="; S timeout 20 qmicli -d qrtr://0 --dms-set-operating-mode=online 2>&1 | tail -1
prev=0; for t in 2 4 6 8 10 15 20 30 45 60 90 120; do sleep $((t-prev)); prev=$t
  st=$(cat /sys/class/remoteproc/remoteproc0/state)
  [ "$st" = running ] || { echo "  +${t}s: $st"; S dmesg | grep -iE "rflm|watchdog received" | tail -1; break; }
  r=$(S timeout 8 qmicli -d qrtr://0 --nas-get-serving-system 2>/dev/null | grep -E "Registration state|Radio interfaces|Selected network|MNC:" | tr -s ' ' | tr '\n' ' ' | sed 's/Registration state//')
  echo "  +${t}s: running | $r"
done
echo "=== итог: $(cat /sys/class/remoteproc/remoteproc0/state) ==="
