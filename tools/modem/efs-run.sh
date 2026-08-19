S() { echo 1234 | sudo -S -p '' "$@"; }
ACT=${1:-hello}; P=${2:-}
S pkill -x diag-router 2>/dev/null; S pkill -f efsprobe 2>/dev/null; sleep 1
S rm -f /tmp/efs.log
S setsid nohup sh -c "python3 /tmp/efsprobe.py 127.0.0.1 2500 $ACT '$P' > /tmp/efs.log 2>&1" >/dev/null 2>&1 </dev/null &
sleep 2
S setsid nohup sh -c 'diag-router -s 127.0.0.1:2500 >/var/log/diag-router.log 2>&1' >/dev/null 2>&1 </dev/null &
sleep 25
pgrep -x diag-router >/dev/null && echo "роутер жив" || echo "роутер МЁРТВ"
grep -vE "^  <- \[00\]" /tmp/efs.log
