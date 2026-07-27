# Geedo firmware notes

The sketch itself lives at `~/Arduino/Geedo_Cloud_Prototype` on Callum's
machine and is **not in this repo** (only the built `.bin`s are). Committing it
here is strongly recommended - it is the single copy of Geedo's brain.

## How OTA works (as built)

- `firmware/manifest.json` = `{version, url, notes}`. Each Geedo polls it
  (every ~60 s), compares `version` against its compiled-in
  `FIRMWARE_VERSION`, and when newer downloads the `.bin` over HTTPS and
  flashes itself (ESP32 two-slot OTA; the `min_spiffs` partition scheme in the
  build command is what makes room for both slots).
- Publishing = `tools/build_firmware.sh [display-name]`: bumps the version in
  the sketch, compiles with arduino-cli, copies the bin into `firmware/`,
  rewrites the manifest, commits, pushes. The git push is the deploy.
  **It only runs on Callum's machine** - it needs arduino-cli and the ESP32
  toolchain, so a firmware release cannot be published from anywhere else.
- Versions are ordered by the integer `version`, which is what the device
  compares. The optional `name` field ("13.1.0") is the label owners see on
  screen; semver lives there while the counter underneath ticks by one.
- The manifest is written **after** the .bin is copied, and the script aborts
  if the compile produced no fresh binary. A manifest pointing at a missing
  .bin used to make every Geedo play the update animation and show
  "DO NOT UNPLUG" on each 60 s poll, forever, without ever updating -
  `checkFirmwareUpdate()` now probes the binary (headers only) before it
  commits to any of that UI.
- The manifest poll appends `?t=<millis>` to defeat the GitHub Pages CDN
  cache (max-age 600) - without it a freshly published version can take up
  to ~10 min to reach devices. The `.bin` needs no cache-buster: its
  filename changes every version.

## Animations

- Format (`tools/pack.py`): `GDA1` + `[ver, frame_count, fps, flags]` +
  one duration byte per frame + frames of **1024 bytes each in raw SSD1306
  page order** (8 pages x 128 columns, LSB = top row of the page).
  flags: bit0 = loop, bit1 = ping-pong.
- `animations/manifest.json` lists every published animation (id, file, size,
  sha-8, category, visibility). Devices sync from it.
- Community pipeline: opening a GitHub issue with a `.geedo.json` attachment
  and the `publish-animation` label triggers the Action, which validates,
  packs, updates the manifest and commits. `animations/codes.json` maps unlock
  codes to files, including date-locked drops.

## The MAIN button and recovery

`GUIDE.md` is the owner-facing version of this. Mechanically: SW1 shorts the
pin to GND, so it idles high via `INPUT_PULLUP` and reads LOW when pressed.

- **Tap** (< 700 ms) - `petGeedo()`: mood up, immediate reaction face.
- **Hold 5 s** - `serviceButtonHold()` draws a per-second countdown, then calls
  `WiFiManager::resetSettings()` and reboots. Releasing early cancels, so it
  cannot fire from a pocket press.

## Mood

One `uint8_t`, `MOOD_FLOOR`(40)..`MOOD_MAX`(100), persisted to `/mood` in
LittleFS and restored on boot. Petting adds `MOOD_PET_BOOST`; `decayMood()`
subtracts 1 per 15 minutes and **stops at the floor**, so Geedo ranges from
delighted to plain content and never below - the owner-facing promise in
`GUIDE.md` is "he never sulks at you", and `moodCategory()` only ever returns
love/happy/cool/animal/robot.

Pets within `PET_STREAK_MS` stack: three in a row reads as `love`, five or
more as `surprised` (overstimulated, which is funnier than endless bliss).
`reacting` guards re-entrancy - without it the button poll inside
`idleDelay()` would re-trigger `petGeedo()` from inside its own reaction face.

Writes are throttled to `MOOD_SAVE_MS` for flash wear, with `saveMood(true)`
forced before both reboot paths (OTA and WiFi erase) so neither loses it.
Out-of-range or missing stored values fall back to the default rather than
being trusted.

Host-tested against the sketch's own source: floor after a week of neglect,
no sad/angry/dead category ever selected, clamp at max, streak build and
reset, guard cleared, save throttle/force/round-trip, corrupt-file rejection.

Every `delay()` in the playback path is now `idleDelay()`, which polls the
button every 5 ms. Host-tested in the scratchpad harness (tap / cancel /
threshold / just-under-threshold / no-press) against the sketch's own source.

Before this, the header comment advertised "hold BOOT on power-up to erase
WiFi" and a screen told users to "tap BOOT to setup", but **no button was read
anywhere in the firmware** - a customer who changed their WiFi password had no
way back in short of a reflash.

## Pin map: C3 vs devkit

The shipping board is an ESP32-C3 (SDA 4, SCL 5, MAIN GPIO3, BOOT GPIO9);
bring-up happens on a classic ESP32 devkit (SDA 21, SCL 22). The sketch picks
between them with `#if CONFIG_IDF_TARGET_ESP32C3`, so one source builds for
both. It previously hard-coded the devkit pins only, and would not have talked
to the OLED on real hardware.

## Known gaps (not yet fixed)

- **Animations are RAM-resident.** `parseAnimBin()` mallocs `frames x 1024`
  per animation. The current library is 242 KB across 242 frames, against
  roughly 160-200 KB free on a C3 after WiFi and TLS. Past that, `malloc`
  fails, `parseAnimBin` returns false and the animation is silently skipped -
  no user-visible error. `MAX_ANIMS` (40) caps it independently, with 32 in
  the manifest today. Fixing this properly means streaming frames from
  LittleFS at playback instead of holding whole animations in RAM.
- **No battery or charger sense.** Traced on the board: `/VBAT` reaches only
  J2, and the charger's `/STAT` pin reaches only R7 and the LED - neither gets
  to a GPIO, and `/VBUS` does not either. So `animations_boot_low_battery` and
  `..._charging` cannot be triggered at all, and Geedo cannot tell you he is
  charging or nearly flat. **`/IO2` and `/IO8` are free** (each sits on a lone
  pull resistor), so rev 5 wants `/STAT` on one and a VBAT divider on an ADC
  pin - that is the whole fix.
- **`visibility` is ignored.** `loadManifestAndAnims()` downloads every entry
  in the manifest regardless of the field, so unlock codes gate the website
  only, not the device.
- **OTA is unsigned.** HTTPS with `setInsecure()`, no signature check.

## Power-on animation (`tools/gen_boot_anim.py`)

Regenerate with `python3 tools/gen_boot_anim.py --png`; it writes both
`firmware/sketch/boot_anim_progmem.h` (PROGMEM, played the instant he powers
up, before WiFi) and `animations/bin/animations_boot_boot_animation.bin`.

98 frames, 20 fps, 98 KB of flash, 5.8 s, in twelve acts: a dying flicker,
mains lightning arcing over, copper traces taking the charge, a plasma surge
with the panel shaking, a rush down a tunnel, hyperspace, a wireframe sphere
tumbling out of the depth and detonating, the GEEDO wordmark with a negative
flash and VHS tearing, a strobe into whiteout, shockwave rings, and shards
flying in from off-screen to assemble his eyes.

What makes it hold up at 128x64:

- **No brightness exists on a 1-bit panel.** An ordered Bayer dither fakes it,
  and every shaded effect (plasma, tunnel, ring falloff) is a value field
  thresholded through that matrix.
- **Line work over shading.** Bresenham strokes, a perspective starfield,
  midpoint-displacement lightning and a projected wireframe sphere stay crisp
  where filled art turns to mud at this size.
- **A sphere reads richer than a cube** for the same handful of lines -
  latitude rings plus longitude arcs give real form.

### Photosensitivity

The first cut of this sequence ran a four-beat strobe: **twelve full-screen
black/white flashes inside one second**, squarely in the band that triggers
photosensitive seizures. WCAG 2.3.1 allows at most three large-area luminance
flashes per second.

On a mono panel the lit fraction *is* the luminance, so a flash is a
frame-to-frame swing of more than a quarter of the screen. `fade()` spreads
every big level change over dithered steps small enough that none of them
counts, which keeps the bloom and the whiteout looking the same while removing
the flashing. Where possible the effect carries its own ramp - the tunnel now
enters bright and dims, rather than cutting from white to black and relighting.

**The generator asserts this on every run** and refuses to emit a sequence with
more than three flashes in any second. It has already caught one 16-per-second
strobe, so it stays.

Generation also asserts the PROGMEM bytes equal the `.bin`, that no run of
near-empty frames exceeds two (so a gap can never look like a hang), and that
**the final frame is pixel-identical to `eyes_render(0,0,100)`** - the boot
cannot drift out of step with the idle face it hands over to.

## Idle face: wandering eyes (`firmware/sketch/eyes.h`)

Geedo's resting state. Two filled rounded rectangles, **38 x 48, corner radius
8, 22 px of black between them**, drawn procedurally into the usual 1024-byte
page buffer.

Why generated rather than drawn: a wandering idle needs dozens of gaze
positions and every stored one costs 1 KB of RAM, which is the exact resource
already over budget. `eyes.h` is ~30 bytes of state and never repeats.

The motion rules, which matter more than the shape:

- **Gaze snaps, never tweens.** Smooth interpolation is what makes robot eyes
  look sedated; real gaze jumps in ~30 ms then holds. `eyes_next()` only ever
  teleports.
- **Hold 0.3-2.6 s**, randomised, shorter when mood is high - a happy Geedo
  darts about, a content one drifts.
- **Centre bias**: the target averages two random draws, so small hops are
  common and a look to the corner is an event.
- **1 px tremor** during the hold, so he is never perfectly still.
- **Blink every 3-6 s** by squashing to 45/12/45 percent over 3 frames of
  45 ms - no eyelid drawn. This is the same trick the hand-drawn
  `blink_eyes` animation uses.
- **Both eyes always move together.** Split gaze reads as broken.

Verification: `eyes_render()` is byte-identical to an independent Python
implementation across all 4940 combinations of gaze offset and squash. A
6.4-hour simulated run confirms the eyes never clip off screen, gaze stays
inside the wander envelope, blinks always play every frame once started, and
the blink rate lands at ~1 per 4.6 s. The rounded-corner test must be a true
three-way max; testing the two terms in sequence silently returns 0 when a
squashed eye inverts the inset rect, which fattened every blink frame until
the cross-check caught it.

## Kaomoji pack (`firmware/sketch/kamoji.h`)

Generated by `tools/kaomoji_gen.py` - do not hand-edit; add faces or glyphs in
the generator and re-run. 191 faces across 11 categories, every glyph
hand-drawn 14 px pixel art (kaomoji need katakana/Greek/box-drawing characters
that no stock embedded font has). Preview of every face:
`assets/kaomoji_preview.png`.

Key property: `kaomoji_render()` outputs a **1024-byte SSD1306 page buffer -
the exact GDA1 frame format** - so a kaomoji goes through the same blit path
the animation player already uses. No display-driver coupling.

```c
#include "kamoji.h"

uint8_t frame[1024];
kaomoji_show(random(KAOMOJI_COUNT), frame);   // render face #i, centred
// now push `frame` to the display exactly like a GDA1 animation frame

const char* f = kaomoji_face(i);              // the UTF-8 string (PROGMEM)
uint8_t cat   = kaomoji_category(i);          // index into KAOMOJI_CATEGORY_NAMES
int w = kaomoji_render("(o^^)o", frame);      // any string of known glyphs
```

Verified: the C renderer was host-compiled and produced byte-identical frames
to the generator's reference renderer for all 191 faces. Unknown characters
are skipped, never crash.

Categories: happy, love, sad, angry, surprised, confused, sleepy, cool,
action, animal, robot, dead - see `KAOMOJI_FACE_CATEGORY`.
