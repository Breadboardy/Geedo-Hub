# Geedo PCB v4 — repaired (rev 4.1)

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

## Known caveats to fix in rev 5 (not addressed here)

- The 3.3 V rail is generated from the **battery** through an AMS1117 (~1.1 V dropout):
  below ~4.3 V of battery the rail sags under 3.3 V, and the board does **not** power
  up from USB with no battery attached. It works, but is brownout-prone — swap in a
  true low-dropout 500 mA LDO (e.g. HT7833) and/or feed the regulator from VBUS too.
- No ESD protection on the USB data lines (add a USBLC6-2SC6 next to J1).
