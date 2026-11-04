#!/bin/bash
# XCHAIN TV adb link watchdog (pt1854u). Reconnects <LAN-IP>:5555 when not in 'device' state; logs state changes.
T=<LAN-IP>:5555; D=$HOME/xchain/tv-link; L=$D/link.log; S=$D/.last_state
st=$(adb devices | awk -v t=$T '$1==t{print $2}'); st=${st:-absent}
act=""
if [ "$st" != device ]; then
  timeout 10 adb disconnect $T >/dev/null 2>&1
  timeout 15 adb connect $T >/dev/null 2>&1
  st2=$(adb devices | awk -v t=$T '$1==t{print $2}'); act=" -> reconnect -> ${st2:-absent}"; st=${st2:-absent}
fi
prev=$(cat $S 2>/dev/null)
if [ "$st" != "$prev" ] || [ -n "$act" -a "$st" = device ]; then echo "$(date -Is) state=$st (was ${prev:-none})$act" >> $L; fi
echo "$st" > $S
