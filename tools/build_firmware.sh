#!/bin/bash
# Build & publish Geedo firmware.
#
# Usage: ./tools/build_firmware.sh [display-name]
#   ./tools/build_firmware.sh            -> next integer, shown as "v13"
#   ./tools/build_firmware.sh 13.1.0     -> next integer, shown as "13.1.0"
#
# The device orders releases by the integer `version` - that is what OTA
# compares - while `name` is only what the owner sees on screen. Semver lives
# in `name`; the counter underneath keeps ticking up by one.
set -e
cd "$(dirname "$0")/.."
HUB="$(pwd)"
SKETCH="/home/callum/Arduino/Geedo_Cloud_Prototype"
VER_NAME="$1"

# refuse to publish from a branch the Geedos do not poll
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
  echo "You are on '$BRANCH'. Geedos poll the Hub built from main." >&2
  echo "Switch with: git checkout main && git merge $BRANCH" >&2
  exit 1
fi

# What is actually PUBLISHED is the manifest, not the sketch. The sketch is a
# working copy that gets copied around between the repo and ~/Arduino, so
# trusting it can silently rewind the counter and republish a version the
# Geedos already have (they compare `latest <= FIRMWARE_VERSION` and ignore
# it). Take whichever is higher so the number can only ever go up.
MANIFEST_VER=$(grep -oP '"version"\s*:\s*\K[0-9]+' "$HUB/firmware/manifest.json" | head -1)
SKETCH_VER=$(grep -oP 'FIRMWARE_VERSION\s*=\s*\K[0-9]+' "$SKETCH/Geedo_Cloud_Prototype.ino" | head -1)
CUR_VER=$MANIFEST_VER
[ "$SKETCH_VER" -gt "$CUR_VER" ] && CUR_VER=$SKETCH_VER
NEW_VER=$((CUR_VER + 1))
[ -n "$VER_NAME" ] || VER_NAME="v$NEW_VER"

if [ -e "$HUB/firmware/geedo_v${NEW_VER}.bin" ]; then
  echo "firmware/geedo_v${NEW_VER}.bin already exists - refusing to overwrite" >&2
  echo "a published version must never change meaning under devices" >&2
  exit 1
fi
echo "Building firmware $CUR_VER -> $NEW_VER  (shown to owners as $VER_NAME)"

# Bump BOTH copies of the sketch: the build copy and the one tracked in the
# repo. Otherwise they drift and the next build rewinds again.
for f in "$SKETCH/Geedo_Cloud_Prototype.ino" "$HUB/firmware/sketch/Geedo_Cloud_Prototype.ino"; do
  [ -f "$f" ] && sed -i -E "s/const uint32_t FIRMWARE_VERSION = [0-9]+;/const uint32_t FIRMWARE_VERSION = $NEW_VER;/" "$f"
done

# compile
cd "$SKETCH"
/home/callum/bin/arduino-cli compile --clean --fqbn "esp32:esp32:esp32:PartitionScheme=min_spiffs" . | tail -3
BIN=$(find /home/callum/.cache/arduino/sketches -name "Geedo_Cloud_Prototype.ino.bin" -newermt '-10 minutes' | head -1)
if [ -z "$BIN" ] || [ ! -s "$BIN" ]; then
  echo "No fresh .bin produced - compile failed. Nothing published." >&2
  exit 1
fi

# copy the binary FIRST, and only then write the manifest that points at it.
# A manifest naming a .bin that is not there yet makes every Geedo show
# "UPDATING / DO NOT UNPLUG" on each poll without ever updating.
cp "$BIN" "$HUB/firmware/geedo_v${NEW_VER}.bin"
cat > "$HUB/firmware/manifest.json" <<EOF
{
  "version": $NEW_VER,
  "name": "$VER_NAME",
  "url": "firmware/geedo_v${NEW_VER}.bin",
  "notes": "Auto-built $(date +%Y-%m-%d)"
}
EOF

# commit + push
cd "$HUB"
git add firmware/ tools/
git commit -m "firmware $VER_NAME (build $NEW_VER)"
git push
echo "✓ Firmware $VER_NAME published. Geedos will auto-update within 60s."
echo "  (GitHub Pages takes ~1 min to redeploy before they can see it.)"
