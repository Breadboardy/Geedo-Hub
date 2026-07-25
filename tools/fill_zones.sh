#!/usr/bin/env bash
# Re-pour the copper zones and save. Needed after any track edit, because a
# stale or missing fill makes every zone-fed pad look unconnected to DRC.
set -euo pipefail
BOARD="${BOARD:-hardware/Geedo_PCB_v4.kicad_pcb}"

KIPY="${KIPY:-}"
if [ -z "$KIPY" ]; then
  for c in /usr/bin/python3 /usr/lib/kicad/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import pcbnew' 2>/dev/null; then KIPY="$c"; break; fi
  done
fi
[ -n "$KIPY" ] || { echo "No python with the 'pcbnew' module (conda's python does not have it)."; exit 1; }

"$KIPY" - "$BOARD" <<'PY'
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
z = b.Zones()
pcbnew.ZONE_FILLER(b).Fill(z)
b.BuildConnectivity()
pcbnew.SaveBoard(sys.argv[1], b)
tr = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
vi = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
print(f"filled {len(z)} zone(s); board has {len(tr)} tracks, {len(vi)} vias")
PY

echo "now: kicad-cli pcb drc --schematic-parity $BOARD"
