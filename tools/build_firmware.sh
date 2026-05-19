#!/bin/bash
# Build & publish Geedo firmware.
# Usage: ./tools/build_firmware.sh
# Reads current version from firmware/manifest.json, bumps it, compiles,
# copies .bin to firmware/, updates manifest, commits + pushes.
set -e
cd "$(dirname "$0")/.."
HUB="$(pwd)"
SKETCH="/home/callum/Arduino/Geedo_Cloud_Prototype"

# read current version from sketch
CUR_VER=$(grep -oP 'FIRMWARE_VERSION\s*=\s*\K[0-9]+' "$SKETCH/Geedo_Cloud_Prototype.ino" | head -1)
NEW_VER=$((CUR_VER + 1))
echo "Bumping firmware $CUR_VER -> $NEW_VER"

# bump sketch
sed -i "s/const uint32_t FIRMWARE_VERSION = $CUR_VER;/const uint32_t FIRMWARE_VERSION = $NEW_VER;/" "$SKETCH/Geedo_Cloud_Prototype.ino"

# compile
cd "$SKETCH"
/home/callum/bin/arduino-cli compile --fqbn "esp32:esp32:esp32:PartitionScheme=min_spiffs" . | tail -3
BIN=$(find /home/callum/.cache/arduino/sketches -name "Geedo_Cloud_Prototype.ino.bin" | head -1)

# copy + manifest
cp "$BIN" "$HUB/firmware/geedo_v${NEW_VER}.bin"
cat > "$HUB/firmware/manifest.json" <<EOF
{
  "version": $NEW_VER,
  "url": "firmware/geedo_v${NEW_VER}.bin",
  "notes": "Auto-built $(date +%Y-%m-%d)"
}
EOF

# commit + push
cd "$HUB"
git add firmware/
git commit -m "firmware v$NEW_VER"
git push
echo "✓ Firmware v$NEW_VER published. Geedos will auto-update within 60s."
