#!/usr/bin/env bash
# Autoroute the Geedo PCB with Freerouting, headless.
#
# KiCad has no CLI for Specctra DSN, so this script is the middle step:
#   1. KiCad PCB Editor: File > Export > Specctra DSN  ->  hardware/Geedo_PCB_v4.dsn
#   2. ./tools/route_pcb.sh
#   3. KiCad PCB Editor: File > Import > Specctra Session  ->  hardware/Geedo_PCB_v4.ses
#
# Usage: ./tools/route_pcb.sh [passes]     (default 100)
set -euo pipefail

DSN="${DSN:-hardware/Geedo_PCB_v4.dsn}"
SES="${DSN%.dsn}.ses"
PASSES="${1:-100}"

command -v java >/dev/null || { echo "java not found. Install a JRE (e.g. sudo apt install default-jre)"; exit 1; }

if [ ! -f "$DSN" ]; then
  echo "No DSN file at $DSN"
  echo "Export it first: KiCad PCB Editor > File > Export > Specctra DSN"
  exit 1
fi

JAR="${FREEROUTING_JAR:-}"
if [ -z "$JAR" ]; then
  JAR=$(find ~/.local/share/kicad ~/Documents/KiCad ~/.local/share/freerouting \
             ~/Downloads /opt /usr/share -name 'freerouting*.jar' 2>/dev/null \
        | sort -V | tail -1)
fi
[ -n "$JAR" ] || { echo "No freerouting jar found. Set FREEROUTING_JAR=/path/to/freerouting.jar"; exit 1; }
echo "Using $JAR"

java -jar "$JAR" \
  --gui.enabled=false \
  -de "$DSN" -do "$SES" \
  -mp "$PASSES" \
  --router.max_passes="$PASSES" \
  --router.allowed_via_types=true \
  -ll 3

if [ -s "$SES" ]; then
  echo
  echo "Routed: $SES"
  echo "Now import it: KiCad PCB Editor > File > Import > Specctra Session"
  echo "Then press B to refill zones and run DRC."
else
  echo "Freerouting produced no session file - check the log above." >&2
  exit 1
fi
