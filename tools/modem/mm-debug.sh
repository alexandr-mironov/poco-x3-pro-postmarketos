# Заход "ModemManager в debug под IPA": запускать ПОСЛЕ загрузки ядра r15/r16 (с IPA в DT) с уже снятым blacklist.
S() { echo 1234 | sudo -S -p '' "$@"; }
R=/sys/class/remoteproc/remoteproc0
echo "=== ядро $(uname -v | cut -c1-30) | модем $(cat $R/state) | recovery $(cat $R/recovery) | аптайм $(cut -d. -f1 /proc/uptime)с ==="
echo "=== ipa/rmnet ==="; lsmod | grep -E "^ipa " | awk '{print $1}'; ip -br link | grep -E "rmnet" || echo "rmnet_ipa нет"
S systemctl stop ModemManager 2>/dev/null; sleep 1
S rm -f /var/log/mm-debug.log
S setsid nohup sh -c 'ModemManager --debug > /var/log/mm-debug.log 2>&1' >/dev/null 2>&1 </dev/null &
for i in 1 2 3 4 5 6; do sleep 3; mmcli -L 2>/dev/null | grep -q Modem && break; done
echo "=== MM: $(mmcli -L 2>&1 | tail -1) ==="
echo "=== enable (MM сам включит радио) ==="; S timeout 40 mmcli -m any --enable 2>&1 | tail -1
i=0; while [ $i -lt 80 ]; do sleep 0.5; i=$((i+1)); st=$(cat $R/state); [ "$st" = running ] || { echo "  +$((i/2)).$((i%2*5))с: модем $st"; break; }; done
sleep 3
echo "=== события MM перед падением (без шума) ==="
S grep -vE "sleep-monitor|QMI request|QMI response|keep-alive|\[qmi-device\]|received indication|emitting|dispose" /var/log/mm-debug.log | grep -E "state changed|registration|packet service|access tech|operating mode|\[modem0\]|port .* released|reprob|error|crash|Failed|couldn't" | tail -50
S cp /var/log/mm-debug.log /home/poco/mm-debug-$(date +%H%M%S).log; S chown poco /home/poco/mm-debug-*.log
