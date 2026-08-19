S() { echo 1234 | sudo -S -p '' "$@"; }
S mount -t debugfs none /sys/kernel/debug 2>/dev/null
rd() { # sid addr -> байт
  S grep -m1 "^$(printf '%04x' $2):" /sys/kernel/debug/regmap/0-0$1/registers 2>/dev/null | awk '{print $2}'
}
dump() { # sid label base
  sid=$1; label=$2; base=$3
  type=$(rd $sid $((base+0x04))); sub=$(rd $sid $((base+0x05))); st=$(rd $sid $((base+0x08))); en=$(rd $sid $((base+0x46))); vl=$(rd $sid $((base+0x40))); vh=$(rd $sid $((base+0x41))); mode=$(rd $sid $((base+0x45)))
  [ -z "$type" ] && { echo "  $label: нет"; return; }
  ready=$(( 0x$st & 0x80 )); enb=$(( 0x$en & 0x80 ))
  mv=$(( (0x$vh<<8 | 0x$vl) ))
  printf "  %-6s type=%s/%s STATUS1=%s EN=%s%s VSET=%dmV MODE=%s %s\n" "$label" "$type" "$sub" "$st" "$en" "$([ $enb -ne 0 ] && echo '(ON)' || echo '(off)')" "$mv" "$mode" "$([ $ready -ne 0 ] && echo READY || echo '-')"
}
echo "=== PM8150 (sid 1): SMPS ==="; for n in 1 2 3 4 5 6 7 8 9 10; do dump 1 s$n $((0x1400 + (n-1)*0x300)); done
echo "=== PM8150 (sid 1): LDO ==="; for n in $(seq 1 18); do dump 1 l$n $((0x4000 + (n-1)*0x100)); done
echo "=== PM8150L (sid 5): SMPS ==="; for n in 1 2 3 4 5 6 7 8; do dump 5 s$n $((0x1400 + (n-1)*0x300)); done
echo "=== PM8150L (sid 5): LDO ==="; for n in $(seq 1 11); do dump 5 l$n $((0x4000 + (n-1)*0x100)); done
echo "=== PM8150L (sid 5): BOB ==="; dump 5 bob 0xA000
