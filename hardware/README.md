# Geedo PCB v4 — repaired (rev 4.2, single-side assembly)

## Rev 4.2: one machine-assembled side

Rev 4.1 had SMD parts on both faces, which forces double-sided assembly -
two setups, two stencils, roughly double the labour charge. Rev 4.2 moves
every SMD part to the **back**, so the board qualifies for the cheap
single-side assembly tier:

- **Back (the machine side):** ESP32 module, USB-C, charger, regulator,
  BOOT + RESET buttons, LED, all passives - 22 parts, one paste-place-reflow
  pass. The USB port opens at the board edge as before, just on the back face.
- **Front (the human side):** only what the outside of Geedo touches - the
  OLED socket, the MAIN button, the battery connector, and the silkscreen
  face. All three parts are through-hole: they insert from the front and get
  soldered on the back, the classic TV-remote build. **Zero SMD passes on
  the front.**
- **SW1 stays the original SMD KSC6** (all three buttons are the same part,
  LCSC C221929). It is the one SMD part on the front, so the fab's
  single-side run does NOT place it - **you hand-solder SW1 yourself**: four
  big pads, an easy first SMD joint. For a production run, either pay for
  the second assembly side or swap SW1 to a 6x6 mm THT switch (that variant
  was built and verified in git history, commit c41971e).
- Everything re-routed from scratch (1000+ segments). The old CC2
  board-edge violations are gone - the new route no longer hugs the edge.
- `hardware/fab/bom.csv` and `hardware/fab/cpl.csv` are the assembly-house
  upload files. The LCSC numbers are suggestions - verify stock at order
  time, and expect the fab's reviewer to nudge some rotations; that is
  normal and they confirm before running.
- To revert the whole relayout:
  `cp hardware/Geedo_PCB_v4_BACKUP_two-sided.kicad_pcb hardware/Geedo_PCB_v4.kicad_pcb`

Verified: clearance 0, board-edge 0, keepout 0, courtyards 0, hole-to-hole 0,
all 17 nets single-piece, netlist 29/29 vs schematic, ground one pour with
every pad connected, and all 13 functional circuits (straps, EN reset, USB,
charger, LED, I2C) checked pad-by-pad. Run KiCad DRC with zones filled as the
final authority before ordering.

# Previous: rev 4.1 notes

The v4 design files had schematic symbols with **made-up pin numbers** that did not
match their real-world footprints, so the netlist landed on the wrong physical pads.
As uploaded, the board could not work at all. This revision repairs the netlists in
both the schematic and the board file. **It still needs re-routing in KiCad before
ordering** — see "What you still need to do" below.

## What was broken in v4

| # | Problem | Effect |
|---|---------|--------|
| 1 | Custom ESP32-C3 symbol numbered its pins 1–16 (including GPIOs IO12/IO13 that don't exist on a C3) while the footprint uses the real 53-pad module numbering | 3.3 V power landed on a GND pad, USB data on GND/IO1 pads, chip-enable (EN) on a no-connect pad — the module could never power up or boot |
| 2 | Custom USB-C symbol used pin numbers 1–6; the connector footprint's pads are named A1…B12/S1 | Zero matches → the USB connector was connected to **nothing** (no 5 V in, no data, no charging) |
| 3 | Custom MCP73831 charger symbol numbering wrong (real chip: STAT=1, VSS=2, VBAT=3, VDD=4, PROG=5) | 5 V was wired into the STAT status pin and the chip's actual power pin got the PROG resistor — charger dead |
| 4 | BOOT button on IO8 | ESP32-C3 download mode needs the button on **IO9** (IO8 must stay pulled high); a button on IO8 does nothing useful |
| 5 | IO2 strap pin floating | IO2 must be high at every boot and has no internal pull-up → unreliable/failed boots |
| 6 | Charge LED net floating; R7 shorted the STAT pin to GND | LED could never light |
| 7 | PROG resistor 1 k → commands ~1 A charge current | Double the MCP73831's 500 mA max — chip would overheat |

## What changed in rev 4.1

- `Geedo:ESP32C3` symbol renumbered to the real ESP32-C3-MINI-1 pad map
  (3V3→3, EN→8, IO3→6, IO4→18, IO5→19, IO8→22, USB D−→26/IO18, USB D+→27/IO19),
  plus proper GND pads (1, 2, 11, 14, 36–53, thermal 49_x) and new IO2/IO9 pins.
  Pin *positions* untouched, so the drawing and all existing wires are unchanged.
- `Geedo:USBC` symbol renumbered to real pads: VBUS=A4/B4/A9/B9, D+=A6/B6, D−=A7/B7,
  CC1=A5, CC2=B5, GND=A1/B1/A12/B12 + shield S1.
- `Geedo:MCP73831` renumbered to the real chip (STAT=1, VDD=4, PROG=5).
- Board pad nets rewritten to match all of the above (verified pad-by-pad).
- BOOT button moved to IO9 (`SW2`); the 10 k pull-up `R2` stays on IO8 as required.
- **New parts:** `R8` 10 k pull-up IO2→3V3 (required strap), `C5` 4.7 µF cap on VBUS
  at the charger input. Both are auto-placed — nudge them wherever you like.
- Charge LED rewired as a proper chain: 3V3 → D1 → R7 → STAT pin.
- `R6` (PROG) changed 1 k → **4.7 k** ≈ 215 mA charge current (safe for ≥350 mAh LiPo;
  use 10 k for ~100 mA if the battery is small).
- Removed 140 track segments/vias that were routed to the wrong physical pads.
  Power routing in the charger corner and the GND zones were kept.

## Routing status: bare board, ready to autoroute

All old copper was removed (it was routed to the wrong pads), so the board now has
footprints, nets, and GND zones but **zero tracks**. Net classes are preset so an
autorouter picks up sensible widths automatically:

| Class | Nets | Track width |
|-------|------|-------------|
| Power | GND, +3V3, /VBAT, /VBUS | 0.50 mm |
| USB | /USB_DP, /USB_DN | 0.30 mm |
| Default | everything else | 0.25 mm |

### Steps

Routing runs entirely from the terminal — no KiCad window needed:

```bash
./tools/route_pcb.sh          # export DSN -> Freerouting -> import SES -> save board
./tools/route_pcb.sh 500      # more optimisation passes
```

The script uses KiCad's own Python bindings (`ExportSpecctraDSN` /
`ImportSpecctraSES`, both headless-capable in KiCad 8+), so it needs the system
python that ships with KiCad — not a conda/venv python. It auto-skips any
Freerouting jar too new for the installed Java (2.2.x needs Java 25; the 1.9.0
build runs on Java 11+).

Afterwards:

1. **Check the USB pair by hand.** D+ and D− (J1 A6/B6 → U3 pad 27, A7/B7 → pad 26)
   should run short and side-by-side. If the autorouter sent them on separate
   scenic routes, delete those two tracks and drag them manually — the connector
   sits right next to the module, so it's a quick fix.
2. `kicad-cli pcb drc --schematic-parity hardware/Geedo_PCB_v4.kicad_pcb`
3. Open the board, press `B` to refill zones, and commit if DRC is clean.
4. **Schematic → ERC** once: one known warning, U1 pin "TEMP" has no pad — the
   5-pin MCP73831 has no TEMP pin; delete that symbol pin and its stub wire.

### Layout notes

- Front side: USB-C, ESP32 module, the three buttons, OLED header.
  Back side: charger, regulator, battery connector, all passives. Parts that look
  stacked in 2D (U1 under SW3, U2 under SW2) are on opposite faces — that's fine.
- `R8` sits at the top of the back-side pull-up column with R1/R2/R3;
  `C5` sits just below the charger U1. Both were auto-added in rev 4.1 — move them
  if you prefer, they have no mechanical constraint.

### Firmware pin map after this fix

MAIN button = GPIO3, BOOT/recovery = **GPIO9** (was 8 — update the sketch if it
read GPIO8), I2C `Wire.begin(4, 5)` (SDA=4, SCL=5). USB is native, no pin setup.
Flashing over USB now works normally; hold BOOT while pressing RESET only for recovery.

## Regulator: MCP1826S, not AMS1117 (changed in this revision)

`U2` was an AMS1117-3.3, which needs ~1.1 V more on its input than it puts out.
Fed from a LiPo that is the wrong way round:

| battery | AMS1117 output | MCP1826S output |
|---------|----------------|-----------------|
| 4.2 V (full) | 3.3 V | 3.3 V |
| 3.9 V (~70%) | ~3.2 V, sagging | 3.3 V |
| 3.7 V (nominal) | ~3.0 V, at the chip's minimum | 3.3 V |
| 3.5 V (~20%) | ~2.8 V, brownout | 3.3 V |

WiFi makes it worse exactly when it matters: an ESP32-C3 pulls 300-400 mA in
transmit bursts, which widens the dropout. The board would have run fine after
a charge and then reset during WiFi activity at half battery, losing most of
the pack's usable capacity.

The MCP1826S-3302 drops only 0.25 V, holds 3.3 V down to about 3.55 V of
battery, and keeps the same SOT-223 footprint. It is **not** pin-compatible -
AMS1117 is GND/Vout/Vin with the tab on Vout, MCP1826S is Vin/GND/Vout with the
tab on GND - so U2's pads were remapped and the three nets re-routed. The
schematic symbol was renumbered rather than redrawn, so the existing wiring is
unchanged. Tab-to-ground is also better thermally, since it bonds to the pour.

`C6` (1 uF, back side) was added as a local output capacitor for regulator
stability; C2's 10 uF is 9 mm away on the same net. It sits at (110.30, 115.80),
3 mm from U2's output pin, with 3.3 V routed to U2.3 in four segments that jog
around the VBAT via. It was originally placed 2 mm from the output pin on the
*wrong side* of it, which put it underneath U2's SOT-223 body - not assemblable,
and KiCad was right to flag the courtyard overlap.

`C7` (1 uF, back side, directly under the module's EN pad) was added between EN
and ground. Espressif's guidelines call for this RC with the 10 k pull-up: it
holds reset low while the rail rises, so the chip starts cleanly on a slow
power-up. Without it a board usually boots but can occasionally hang until
reset is pressed.

## Powering the board

The 3.3 V rail is generated from the **battery**. USB 5 V reaches only the
charger, so with no cell installed the MCP73831 has to act as the supply:
it is current-limited to 215 mA and can cycle when the load is light.

- **Flashing with a battery connected:** reliable. Native USB, no serial chip.
- **Flashing with no battery:** usually works (download mode draws well under
  the limit) but the rail is unregulated-ish and a brownout mid-write is
  possible. Nothing is damaged; just retry.
- **Running WiFi with no battery:** will brown out on transmit bursts.

Feeding the regulator from USB *or* battery would fix this properly and is the
main remaining item for rev 5.

## Ground plane: SW2's ground was floating

The copper pour on the front side is split by the CC2 track that runs down
the right-hand side of the board. The strip east of it (roughly x 114-118.5,
y 105-126) carries **SW2's two ground pads** and had no via anywhere on it,
so the BOOT button's ground return was connected to nothing. Two stitching
vias at (118.0, 120.9) and (118.0, 117.4) tie that strip down to the back-side
plane. Ground now resolves to a single 2042 mm2 piece across both layers.

This is what the long-standing "Zone [GND] on F.Cu / Zone [GND] on B.Cu -
unconnected" DRC item was pointing at. It went unexplained for a while because
the offline checking scripts modelled SW2's pads with their width and height
swapped, which painted false copper straight across the gap.

## The antenna keepout was thrown off the board by the flip

Spotted by eye in KiCad: the ESP32's antenna keepout rectangle was drawn far
off to the left of the board, nowhere near the module.

`ESP32-C3-MINI-1` carries three keepout zones nested inside its footprint,
covering the antenna end of the module. **Zones nested in a footprint store
absolute board coordinates**, unlike pads, lines and polygons, which are
footprint-local. The rev-4.2 flip negated every local x, so it turned the
keepout's `x 90.575..103.775` into `-103.775..-90.575` — mirrored about x=0
instead of about the footprint origin, landing ~190 mm off the board.

Nothing flagged it. KiCad's DRC has no rule for "antenna is missing its
keepout", and the board is saved unfilled, so the damage only appears at
**Edit → Fill Zones** — the step right before Gerber export. Simulating the
pour on the pre-fix file shows the ground plane flooding the antenna window
almost completely: 71.2 mm2 on F.Cu and 70.5 mm2 on B.Cu, out of 71.3 mm2.
Solid copper on both sides of a printed antenna detunes it and shorts out its
near field, so the radio would have been crippled on every board in the order.

The fix restores `x 90.575..103.775`. The rectangle is centred on U3's origin
(x = 97.175), so mirroring maps it onto itself — a flipped module needs the
exact same absolute keepout as an unflipped one. After the fix the pour is
kept out entirely (0.65 mm2 residual per layer, which is one 0.05 mm grid row
at the window edge — a rasteriser artifact, not copper).

`tools/flip_footprint.py` carried the same latent bug and would have repeated
it on any future flip. It now holds nested zones out of the local-coordinate
rewrite and mirrors them about the footprint origin with exact decimal
arithmetic, guarded by a new self-test **T5** (zone vertices must land at
`2*fx - x`, alongside T2 for pads). Cross-check: re-flipping U3 from the
two-sided backup with the repaired tool reproduces the corrected coordinates
exactly.

## The 3.3 V rail was in two halves

Caught by KiCad's DRC, not by me. `+3V3` was split into two electrically
separate islands with nothing joining them:

| island | what was on it |
|--------|----------------|
| A | U3.3 (ESP32 3.3 V), U2.3 (regulator output), C6.1, D1.2 |
| B | **J3.2 (OLED 3.3 V)**, R1.1, R2.1, R3.1, R8.1, C2.1, C3.1, C4.1 |

So the regulator's output never reached the OLED header or **any** of the
pull-ups - including the IO2 and IO8 strapping resistors the ESP32-C3 needs
held high to boot, and the IO9 pull-up. The board would not have started.

The routing had got within 1.2 mm of finishing and stopped: a front-side stub
dead-ended at (103.15, 77.85) and a back-side track dead-ended at
(103.96, 77.00), on opposite layers with no via between them. Fixed with a via
at the front-side tip and a 0.5 mm back-side track joining the two.

KiCad reported this as a single "unconnected items" entry, which badly
undersells it - one missing connection was the whole upper half of the rail.
Every net is now checked island-by-island, not just pad-to-pad; see
`tools/drc_offline.py`.

## The logo, and why it never printed

The face logo was a KiCad **reference image** - an `(image ...)` element with a
1254x1254 PNG embedded as base64. Reference images are editor-only: they exist
to trace over and line things up, and KiCad **never plots them to Gerbers**. The
fab had never seen it, on any board.

It was also far too small to print. The PNG is 96% whitespace padding, so at the
stored scale the actual face came out 2.3 mm wide with 0.18 mm strokes - right at
the silkscreen minimum, patchy at best even if it had plotted.

It is now real artwork: the bitmap is traced into outlines and stored as a
footprint, `Geedo:Logo`, of `fp_poly` shapes on **F.SilkS**, which does plot.
Sits at (115.5, 77.5), sized so the face is 6 mm wide with 0.47 mm strokes,
0.90 mm inside the top edge and 1.16 mm from the nearest pad. The mouth's enclosed hole is preserved by fracturing - the hole
is joined to its outer contour by a zero-width slit, which is exactly what
KiCad's own bitmap converter does.

The reference image was removed: it plotted nothing, it sat directly on top of
the new artwork in the editor, and it was 912 kB of base64 in a 1.1 MB board
file (now 205 kB). The source bitmap is kept as `hardware/geedo-logo.png`.

To move or resize it, drag the `LOGO1` footprint in KiCad like any other. To put
it in **copper** instead of silkscreen - bare copper reads gold on ENIG and looks
sharper than white ink - change the `fp_poly` layers to `F.Cu`; it would then
need clearance from the ground pour, so re-run `tools/drc_offline.py` after.

The `Geedo` copper text on the back has been **deleted**. It had been moved once,
from (118.5, 81) to (112.55, 87.3), because a 3.3 V track ran straight through the
lettering - KiCad flagged that as a 0.000 mm clearance violation - but the board
carries its name in the silkscreen logo now, so the copper lettering is gone. That
also means there is no unconnected copper island sitting in the ground pour.

## Check your OLED module's pin order before plugging it in

The header `J3` is wired, physically, as:

| pin | net |
|-----|-----|
| 1 (square pad) | GND |
| 2 | 3V3 |
| 3 | SCL |
| 4 | SDA |

**Checked: the module in use is GND-first, so it matches and plugs straight in.**

Worth knowing if you ever swap displays: some SSD1306 breakouts are ordered
VCC, GND, SCL, SDA instead. Plugging one of those straight in puts 3.3 V on its
ground pin and ground on its supply, which destroys it. Compare the silkscreen
on any new module against the table above first; if it does not match, swap the
two power wires. The board is not wrong, both module variants simply exist.

The schematic used to disagree with this. Its `Conn4` symbol named the pins
VCC, GND, SDA, SCL - both pairs the wrong way round from how the wires actually
run. The wiring and the board were always self-consistent; only the names on the
symbol were wrong, so anyone reading the schematic would have got it backwards.
The pin names now match reality.

Ten other pin labels were stale in the same way, left behind when the symbols
were renumbered. `U2` was still carrying **AMS1117** pin names (`VI`, `VO`,
`GND_Adj`) although it is an MCP1826S, and `U1`'s labels were one position out.
All nets were correct throughout - these were names only - but they are now
corrected so the board reads truthfully in KiCad.

## Not done, if you want them later

- **No reference designators are printed.** 25 of the 26 are hidden, so the
  board gets component outlines and polarity marks but no `R1`/`C2`/`U3` text.
  With four different values across eight identical-looking 0402 resistors,
  hand-populating this means counting positions off the layout. Un-hiding them
  is possible but not automatic: several sit 15-36 mm from their own part, so
  they would need repositioning, and four would land on pads.
- **No pull-ups on SDA/SCL.** I2C needs them. Most SSD1306 modules have their
  own on board, in which case this is fine; if yours does not, the bus will not
  work at all. Two 0402 resistors, 4.7 k, from SDA and SCL to 3V3 would settle it.

## Remaining DRC items

After the last pass KiCad reports **0 unconnected pads**. What is left:

| item | severity | why it stays |
|------|----------|--------------|
| 3x `copper_edge_clearance` on the CC2 trace, 0.348 mm vs 0.5 mm | error | Genuinely unfixable in this layout - see the rev 5 note below. Fabs build 0.35 mm to the outline routinely. |
| `lib_footprint_mismatch` on U3 | warning | The ESP32 module footprint is custom and edited, so it will always differ from the library copy. No effect on fabrication. |

The logo footprint lives in `hardware/Geedo.pretty/`, registered by
`hardware/fp-lib-table`, so `Geedo:Logo` resolves instead of reporting a
missing library.

C5 and C7 previously reported `lib_footprint_mismatch` too. They sat at
rotation 0 while their pads carried an absolute angle of 180, which KiCad reads
as differing from the library. The pads are symmetric roundrects so the two are
the same shape - normalising the angle is bookkeeping, not a geometry change.

## Checking the board without opening KiCad

Two scripts check the board straight from the `.kicad_pcb` file, so they work
on a machine with no KiCad installed and they do not care whether the zones
happen to be filled. Run both from the repo root:

```bash
python3 tools/drc_offline.py    # clearance, board edge, keepout
python3 tools/pour_sim.py       # re-derives the pour, checks GND is one net
```

`pour_sim.py` needs numpy and scipy. It does not read the stored
`filled_polygon` blocks - those go stale the moment anything is re-routed.
It rebuilds the fill from the zone rules instead (clearance, min thickness,
keepouts, edge clearance, island removal), then merges the two layers at
through-hole pads and vias and flood-fills. That is what caught SW2's
floating ground island.

Expected output as of this revision: 0 clearance, 0 keepout, 4 board-edge
(the CC2 trace described below), and ground resolving to a single group with
every ground pad on poured copper. Courtyard overlaps: 0. Nets split across
islands: 0.

These are a second opinion, not a replacement for KiCad's DRC - they do not
model solder-mask bridging, starved thermals or footprint-library parity.
Run `kicad-cli pcb drc --schematic-parity hardware/Geedo_PCB_v4.kicad_pcb`
before ordering, with the zones filled.

## Known caveats to fix in rev 5

- No ESD protection on the USB data lines (add a USBLC6-2SC6 next to J1).
- The CC2 trace runs 0.35 mm from the bottom board edge where the setup asks
  0.5 mm. This one cannot be fixed by moving the trace: it threads the gap
  between SW2's lower pad and the board outline, which is 0.8 mm wide, and
  clearing the pad by 0.2 mm plus the edge by 0.5 mm needs 0.95 mm. Lifting it
  just trades an edge violation for a 0.025 mm pad clearance, which is far
  worse. Fixing it properly means nudging SW2 up a millimetre in rev 5. Most
  fabs build 0.35 mm to the outline without comment.
