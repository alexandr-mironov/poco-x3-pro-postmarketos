S() { echo 1234 | sudo -S -p '' "$@"; }
R=/sys/class/remoteproc/remoteproc0
[ "$(cat $R/state)" = running ] || { echo "модем не running"; exit 1; }
S systemctl stop ModemManager 2>/dev/null
echo "=== текущие предпочтения ==="; S timeout 15 qmicli -d qrtr://0 --nas-get-system-selection-preference 2>&1 | grep -E "Mode|LTE band|Acquisition" | head -4
# Из DSD: сота на LTE. Из первого F3: Band 120/126? (это внутренние номера) — MTS RUS обычно B3 (1800), B7 (2600), B20 (800). CA требует ≥2 бэндов.
# Ограничиваю одним бэндом: B7 (eutran-7), затем при неудаче B3.
for band in eutran-7 eutran-3 eutran-20; do
  echo "=== LTE только $band ==="
  S timeout 20 qmicli -d qrtr://0 --nas-set-system-selection-preference="lte,${band}" 2>&1 | tail -1
  S timeout 15 qmicli -d qrtr://0 --nas-get-system-selection-preference 2>&1 | grep -iE "LTE band" | head -1
  S timeout 20 qmicli -d qrtr://0 --dms-set-operating-mode=online 2>&1 | tail -1
  i=0; reg=""; while [ $i -lt 40 ]; do sleep 0.5; i=$((i+1)); st=$(cat $R/state); [ "$st" = running ] || { echo "  +$((i/2)).$((i%2*5))с: модем $st"; break; }
    r=$(S timeout 3 qmicli -d qrtr://0 --nas-get-serving-system 2>/dev/null | grep -oE "'(registered|not-registered[a-z-]*|searching)'" | head -1); [ $((i%4)) = 0 ] && echo "  +$((i/2))с: $r"; done
  [ "$(cat $R/state)" = running ] && { echo "=== ВЫЖИЛ на $band ==="; S timeout 10 qmicli -d qrtr://0 --nas-get-serving-system 2>/dev/null | grep -E "Registration|MNC|Radio" | tr -s ' '; break; }
  echo "упал на $band — следующий заход требует ребута"; break
done
