#!/usr/bin/env bash
# Fully headless autoroute of the Geedo PCB: export DSN -> Freerouting -> import SES.
# No KiCad window, no menu clicks.
#
#   ./tools/route_pcb.sh [passes]        # default 100 passes
#
# Env overrides:
#   BOARD=hardware/other.kicad_pcb   FREEROUTING_JAR=/path/to.jar   KIPY=/usr/bin/python3
#
# The board is saved in place, so commit the result when DRC is clean.
set -euo pipefail

BOARD="${BOARD:-hardware/Geedo_PCB_v4.kicad_pcb}"
PASSES="${1:-100}"
DSN="${BOARD%.kicad_pcb}.dsn"
SES="${BOARD%.kicad_pcb}.ses"

[ -f "$BOARD" ] || { echo "No board at $BOARD"; exit 1; }

# --- python that can import pcbnew (NOT conda's python; KiCad installs into system python)
KIPY="${KIPY:-}"
if [ -z "$KIPY" ]; then
  for c in /usr/bin/python3 /usr/lib/kicad/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import pcbnew' 2>/dev/null; then KIPY="$c"; break; fi
  done
fi
[ -n "$KIPY" ] || { echo "No python with the 'pcbnew' module found (KiCad's python bindings).
Try: sudo apt install kicad  — or set KIPY=/path/to/python3"; exit 1; }
echo "python:  $KIPY  (KiCad $("$KIPY" -c 'import pcbnew;print(pcbnew.GetBuildVersion())'))"

# --- freerouting jar that this JVM can actually run
JAVA_MAJOR=$(java -version 2>&1 | grep -o 'version "[0-9]*' | head -1 | grep -o '[0-9]*$' || echo '?')
echo "java:    $JAVA_MAJOR"
JARS="${FREEROUTING_JAR:-}"
if [ -z "$JARS" ]; then
  JARS=$(find ~/.local/share/kicad ~/Documents/KiCad ~/Downloads ~/freerouting \
              /opt /usr/share -name 'freerouting*.jar' 2>/dev/null || true)
fi
[ -n "$JARS" ] || { echo "No freerouting jar found. Set FREEROUTING_JAR=/path/to/freerouting.jar"; exit 1; }

JAR=""
for j in $JARS; do
  if java -jar "$j" -help 2>&1 | grep -q UnsupportedClassVersionError; then
    echo "skip:    $j (needs a newer Java than $JAVA_MAJOR)"
  else
    JAR="$j"; break
  fi
done
if [ -z "$JAR" ]; then
  echo "Every jar found needs a newer Java runtime than yours ($JAVA_MAJOR)." >&2
  echo "Either install a newer JRE, or grab the Java-11 build:" >&2
  echo "  curl -LO https://github.com/freerouting/freerouting/releases/download/v1.9.0/freerouting-1.9.0.jar" >&2
  echo "  FREEROUTING_JAR=./freerouting-1.9.0.jar ./tools/route_pcb.sh" >&2
  exit 1
fi
echo "router:  $JAR"

# --- 1. export Specctra DSN  (FRESH=1 strips existing copper first, so the
#        router starts from a blank board instead of tidying its own last run)
"$KIPY" - "$BOARD" "$DSN" "${FRESH:-0}" <<'PY'
import sys, pcbnew
board = pcbnew.LoadBoard(sys.argv[1])
if sys.argv[3] == "1":
    old = [t for t in board.GetTracks()]
    for t in old:
        board.Remove(t)
    board.BuildConnectivity()
    pcbnew.SaveBoard(sys.argv[1], board)
    print(f"fresh start: removed {len(old)} existing tracks/vias")
if not pcbnew.ExportSpecctraDSN(board, sys.argv[2]):
    sys.exit("DSN export failed")
print(f"exported {sys.argv[2]}")
PY

# --- 2. route (headless; falls back to a virtual display for older jars that need one)
FR_ARGS=(-de "$DSN" -do "$SES" -mp "$PASSES")
set +e
java -jar "$JAR" --gui.enabled=false "${FR_ARGS[@]}" 2>&1 | grep -vi 'JAVA_TOOL_OPTIONS' | tail -20
STATUS=${PIPESTATUS[0]}
set -e
if [ ! -s "$SES" ] && command -v xvfb-run >/dev/null 2>&1; then
  echo "retrying under a virtual display (older Freerouting needs one)..."
  xvfb-run -a java -jar "$JAR" "${FR_ARGS[@]}" 2>&1 | tail -20 || true
fi
[ -s "$SES" ] || { echo "Freerouting produced no session file (exit $STATUS)." >&2; exit 1; }

# --- 3. import the routed session back into the board
"$KIPY" - "$BOARD" "$SES" <<'PY'
import sys, pcbnew
board = pcbnew.LoadBoard(sys.argv[1])
if not pcbnew.ImportSpecctraSES(board, sys.argv[2]):
    sys.exit("SES import failed")

# refill copper zones, otherwise every zone-fed pad reports as unconnected in DRC
zones = board.Zones()
if len(zones):
    pcbnew.ZONE_FILLER(board).Fill(zones)
    print(f"filled {len(zones)} zone(s)")

board.BuildConnectivity()
pcbnew.SaveBoard(sys.argv[1], board)
tr = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
vi = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
print(f"imported: {len(tr)} tracks, {len(vi)} vias -> saved {sys.argv[1]}")
PY

echo
echo "Done (zones already filled). Next:"
echo "  kicad-cli pcb drc --schematic-parity $BOARD"
echo "  FRESH=1 ./tools/route_pcb.sh 500     # blank-slate re-route if items are unconnected"
