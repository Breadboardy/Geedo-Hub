# Hand-routing worksheet — Geedo PCB v4.1

Board is 89.5–119.0 mm x 75.0–126.5 mm, 2 layers. `F` = front, `B` = back.
Coordinates are pad centres in mm, matching KiCad's cursor readout.

Net class widths are preset, so KiCad picks the right width automatically once
you start a track on a net: Power 0.50 mm, USB 0.30 mm, everything else 0.25 mm.

| # | Net | What it is | Pads to connect | Notes |
|---|-----|-----------|-----------------|-------|
| 1 | `/USB_DP` | USB data + | **J1**.A6 (103.2,118.0)F · **J1**.B6 (104.2,118.0)F · **U3**.27 (103.1,110.3)F | 0.30 mm - route as a pair with USB_DN, short, side-by-side, same layer, no stubs |
| 2 | `/USB_DN` | USB data - | **J1**.A7 (103.8,118.0)F · **J1**.B7 (102.8,118.0)F · **U3**.26 (103.1,111.1)F | 0.30 mm - pair partner of USB_DP |
| 3 | `/VBUS` | 5 V from USB | **C5**.1 (93.0,124.8)B · **J1**.A4 (101.0,118.0)F · **J1**.A9 (106.0,118.0)F · **J1**.B4 (106.0,118.0)F · **J1**.B9 (101.0,118.0)F · **U1**.4 (92.5,122.5)B | 0.50 mm - J1 -> C5 -> charger U1 pad 4 |
| 4 | `/VBAT` | battery rail | **C1**.1 (118.0,114.0)B · **J2**.1 (95.5,81.5)B · **U1**.3 (94.8,122.5)B · **U2**.3 (111.5,118.7)B | 0.50 mm - charger out, battery, C1, regulator in |
| 5 | `+3V3` | 3.3 V rail | **C2**.1 (118.0,112.0)B · **C3**.1 (118.0,110.0)B · **C4**.1 (118.0,108.0)B · **D1**.2 (109.5,118.0)B · **J3**.2 (104.0,77.0)F · **R1**.1 (118.0,89.0)B · **R2**.1 (118.0,91.0)B · **R3**.1 (118.0,93.0)B · **R8**.1 (118.0,87.1)B · **U2**.2 (111.5,121.0)B · **U3**.3 (91.3,105.5)F | 0.50 mm - regulator out to ESP32 pad 3, caps, OLED, pull-ups |
| 6 | `Net-(J1-CC1)` | USB-C CC1 | **J1**.A5 (102.2,118.0)F · **R4**.1 (118.0,95.0)B | 5.1k to GND - required or a USB-C host sends no power |
| 7 | `Net-(J1-CC2)` | USB-C CC2 | **J1**.B5 (105.2,118.0)F · **R5**.1 (118.0,97.0)B | 5.1k to GND - same |
| 8 | `Net-(U1-PROG)` | charge current set | **R6**.2 (117.0,99.0)B · **U1**.5 (92.5,120.6)B | to R6 4.7k -> GND |
| 9 | `Net-(U1-STAT)` | charger status | **R7**.1 (118.0,101.0)B · **U1**.1 (94.8,120.6)B | to R7 -> D1 -> 3V3 |
| 10 | `/STAT` | LED cathode side | **D1**.1 (109.5,119.0)B · **R7**.2 (117.0,101.0)B | D1 to R7 |
| 11 | `/EN_NET` | chip enable / reset | **R3**.2 (117.0,93.0)B · **SW3**.1 (91.5,124.4)F · **U3**.8 (91.3,109.5)F | U3 pad 8, R3 pull-up, SW3 to GND |
| 12 | `/IO3` | MAIN button | **R1**.2 (117.0,89.0)B · **SW1**.1 (113.9,106.5)F · **U3**.6 (91.3,107.9)F | U3 pad 6, R1 pull-up, SW1 to GND |
| 13 | `/IO9` | BOOT button | **SW2**.1 (113.0,124.3)F · **U3**.23 (101.2,112.8)F | U3 pad 23, SW2 to GND - download-mode strap |
| 14 | `/IO8` | strap pull-up only | **R2**.2 (117.0,91.0)B · **U3**.22 (100.4,112.8)F | U3 pad 22 to R2 - no button, must stay high |
| 15 | `/IO2` | strap pull-up only | **R8**.2 (117.0,87.1)B · **U3**.5 (91.3,107.1)F | U3 pad 5 to R8 - must be high at boot |
| 16 | `/SDA` | I2C data | **J3**.4 (109.0,77.0)F · **U3**.18 (97.2,112.8)F | U3 pad 18 to OLED header pin 4 |
| 17 | `/SCL` | I2C clock | **J3**.3 (106.5,77.0)F · **U3**.19 (98.0,112.8)F | U3 pad 19 to OLED header pin 3 |
| 18 | `GND` | ground | 50 pads (zone-fed) | mostly handled by the 3 zones - add stitching vias between F.Cu and B.Cu near U3 and J1 |

## KiCad keys you need

| Key | Action |
|-----|--------|
| `X` | start routing a track from the pad under the cursor |
| click | place a corner; double-click ends the track |
| `V` | drop a via mid-track and switch to the other layer |
| `Esc` | finish / cancel the current track |
| `D` | drag an existing segment |
| `Del` | delete the selected track |
| `B` | fill all zones (do this at the end) |
| `Ctrl+Z` | undo |
| PgUp / PgDn | make F.Cu / B.Cu the active layer |

Thin lines are the ratsnest — every one is a connection still owed. They vanish
as you route, so the board is finished when none are left.

## Suggested order

1. **USB pair first** (rows 1–2) while there is empty space — they are the only
   timing-sensitive traces. Both connector pads of each pair are already joined
   inside the footprint, so one trace per pair is enough.
2. **CC resistors** (rows 6–7) — tiny, right next to the connector.
3. **Power** (rows 3–5) — fat traces, get them in before the board fills up.
4. **Everything else** — buttons, straps, I2C, charger.
5. **GND last:** most pads are fed by the zones, so mainly drop a few stitching
   vias (`V`) between front and back near U3 and J1, then press `B`.

## Checking your work

```bash
kicad-cli pcb drc --schematic-parity hardware/Geedo_PCB_v4.kicad_pcb
```

"Unconnected items" = ratsnest lines still owed. Clearance violations mean two
things are too close — drag one aside. Silkscreen warnings are cosmetic.

## If you want the autorouter's version back as a starting point

The last routed session is still on disk. Re-import it without re-routing:

```bash
/usr/bin/python3 -c "
import pcbnew
b = pcbnew.LoadBoard('hardware/Geedo_PCB_v4.kicad_pcb')
pcbnew.ImportSpecctraSES(b, 'hardware/Geedo_PCB_v4.ses')
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard('hardware/Geedo_PCB_v4.kicad_pcb', b)"
```

Then delete the traces you dislike and redo just those by hand.
