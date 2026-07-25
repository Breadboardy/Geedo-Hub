#!/usr/bin/env bash
# Keep autorouting until every connection is made (or until it stops improving).
#
#   ./tools/route_until_done.sh            # 200 passes per round, up to 12 rounds
#   ./tools/route_until_done.sh 500 20     # 500 passes per round, up to 20 rounds
#
# Each round re-exports the board (existing copper included), lets Freerouting
# rip up and retry, then counts what DRC still says is unconnected. Rounds keep
# running while that number falls. If it stalls, one blank-slate attempt with
# double the passes is tried before giving up, since a different starting point
# sometimes finds a way through.
set -uo pipefail

BOARD="${BOARD:-hardware/Geedo_PCB_v4.kicad_pcb}"
PASSES="${1:-200}"
ROUNDS="${2:-12}"
HERE="$(cd "$(dirname "$0")" && pwd)"
RPT="${TMPDIR:-/tmp}/geedo-drc.rpt"

unconnected() {
  kicad-cli pcb drc -o "$RPT" "$BOARD" 2>/dev/null \
    | grep -oE 'Found [0-9]+ unconnected' | grep -oE '[0-9]+' | head -1
}

start=$(unconnected); start=${start:-?}
echo "starting point: $start unconnected"
best=999999
stall=0

for r in $(seq 1 "$ROUNDS"); do
  echo
  echo "=== round $r/$ROUNDS ($PASSES passes) ==="
  if [ "$stall" -ge 2 ]; then
    echo "(stalled — trying one blank-slate run at $((PASSES * 2)) passes)"
    FRESH=1 "$HERE/route_pcb.sh" $((PASSES * 2)) >/dev/null 2>&1
  else
    "$HERE/route_pcb.sh" "$PASSES" >/dev/null 2>&1
  fi

  u=$(unconnected)
  if [ -z "$u" ]; then echo "could not read DRC output — run route_pcb.sh directly to see the error"; exit 1; fi
  echo "round $r result: $u unconnected"

  if [ "$u" -eq 0 ]; then
    echo
    echo "FULLY ROUTED after $r round(s)."
    kicad-cli pcb drc --schematic-parity -o "$RPT" "$BOARD" 2>/dev/null | tail -4
    echo "report: $RPT"
    exit 0
  fi

  if [ "$u" -lt "$best" ]; then best="$u"; stall=0; else stall=$((stall + 1)); fi
  if [ "$stall" -ge 3 ]; then
    echo
    echo "Stopped: $u connections left that the autorouter cannot place ($best was its best)."
    echo "Those need routing by hand — see hardware/ROUTING.md for the pad list."
    echo "Unconnected items in the report:"
    grep -A2 -i 'unconnected' "$RPT" | head -30
    exit 0
  fi
done

echo
echo "Ran out of rounds with $best unconnected at best. Raise the round count or"
echo "finish the rest by hand — see hardware/ROUTING.md."
