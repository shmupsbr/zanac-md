# Zanac MD

This Mega Drive port is based on the MSX reverse-engineering in [zanac-re](https://github.com/mgmalheiros/zanac-re) by Marcelo Malheiros. The original project is not ours; this repository is a derivative port.

Mega Drive port of Zanac (MSX). Simulation stays in MSX space; render is a
skin with two modes:

- **Original** — 256px H32, identical playfield width to the MSX game
- **Zanac MD** — 320px H40, room for a later art pack

This tree does **not** contain the Zanac ROM or a dump of `zanac.asm`. Map
scripts and tile-column bytes are extracted from the RE tree's `zanac.asm`
DB lines by `tools/extract_map_scripts.py
tools/extract_sound.py   event table + tracks from zanac.asm
res/sound_blob.bin      music/SFX 0x5234-0x5A10 (generated)
src/sound.c             27-event PSG interpreter`.

## Requirements

- SGDK 2.11 at `C:\Users\Filipe\SGDK`
- Java 8+ on PATH (rescomp). OpenJDK 21 is installed.
- User env vars (already set):
  - `GDK` = `C:/Users/Filipe/SGDK` (forward slashes)
  - `GDK_WIN` = `C:\Users\Filipe\SGDK`

## Build

Re-extract scripts (needs the RE tree's `source/zanac.asm`):

```powershell
python tools\extract_map_scripts.py
python tools\extract_logo.py
```

Then, from this directory:

```powershell
& $env:GDK_WIN\bin\make -f $env:GDK_WIN\makefile.gen
```

Output: `out/rom.bin`.

## Controls

| Screen | Input | Action |
|--------|--------|--------|
| Title  | D-Pad up/down | Select Original / Zanac MD |
| Title  | START | Start game in that mode (round 1) |
| Title  | C + START | Continue from last round reached |
| Game   | D-Pad | Fly the ship (8-dir) |
| Game   | A | Primary shot (20-frame period) + secondary fire-weapon (type 3). Spends fire ammo. |
| Game   | B | Primary shot only. Does **not** spawn type 3 or spend fire ammo. |
| Game   | C | Secondary fire-weapon only (the depleting special). Spends fire ammo. Fire 2 Field stays auto. |
| Game   | START | Pause toggle (MSX STOP). Mutes via E200; PAUSE at nametable 0x396A |
| Game over | A / B / C / START | Skip wait, return to title |

On start the map-script interpreter runs the **real round-1** stream
(`0xA751`, 57 commands). Cmd 8 at row 30 draws `ROUND 1` from E701. Cmd 9
jumps by MSX address into the loaded blob (round 1 → 2 → … → 7 loops). HUD
shows last command name, row, round, PC, lives, shot level, and fire number. Plane B
scrolls a charset-tiled strip built from `tile_tables` plus cmd 2/5 column
pointers. Cmd 5 / cmd B inner streams run `place_tile_group` (type 70/71/82
idols and fire-boxes) and stamp their tile-runs onto the scrolling nametable.
Cmd 1 `place_tiles` stamps type-69 ground entities.

Round 1 is shootable: A fires type-2 shots and the type-3 fire-weapon (default fire 0 All-Range); B is shots only; C is the fire-weapon only. Airborne enemies
(duster / teruzo / luster / sig / umber / veybar / swoopers) and proto-box pickups spawn from the
`spawn_table` type list; map-script cmd 0/C feed spawn_ctrl / pace. Shot vs
enemy kills (boxes take 5 hits; type-4 drops 3 type-38 bullets; type-6 drops a power chip that raises
`shot_level`). Enemy vs ship is a player-hit: 3 lives, 64-frame i-frames,
respawn; last life → GAME OVER → title. Type 83 (if spawned) is a touch pickup that calls fire_select. Each shot feeds ALC (E13F cadence into E12E/F/E131) so spawn pace ramps with fire. Type 44 ground structures spawn from the table (3 hp, fall); type 64 proto-structure converts via spawn_type_list. Types 46–55 are ground-guns (fall, fire type 38/21). Types 7–9 umber, 11/69 base-spawner, 22–25 veybar, 26–29 edge swoopers, 30/32 ground swooper, 34 stealth (8084/8087 type-38 fan), 36 flashing (16 hp), and 57–58 paired descenders spawn from the table. Types 65/66 stealth (4/7 hp; 65=type20, 66=5x59+ev21) and 67 med_circle (5 hp) spawn from the table. Type 61 large descender is ported. Round-1/2 bases are type 73–79 nametable-locked segments (HP from base_segment_table; R1 is type-75 groups at 10 hp). Segments run base_attack_patterns (0x93AB / interp 0x8BF5); type 75 fires type-38 pairs. Type 70/71 sit on the scroll (shot HP → type-72 orb: yellow = kill-all, black = warp). Type 82 fire-box (4 hp) drops type 83. Score HUD uses score_award_table (kills add points). Fire 0-7 are ported REAL (0 All-Range, 1 Straight, 2 Field, 3 Circular, 4 Vibrator, 5 Rewinder, 6 Plasma no-entity, 7 High Speed). `fire_life_timer` ticks E14C/E14D and expires to fire 0. Original-mode audio is a PSG track interpreter (MSX AY commands -> SGDK PSG): title ev3, round-start ev7 (or ev2 if round\equiv0 mod 8) chaining to ev1, shot ev13, explosion ev18, game-over ev4, stop_all_sound on title return.

## Layout

```
src/main.c              ROM entry, TITLE <-> GAME
src/game.c              state machine, start/update, game-over
src/title.c             title screen
src/mode.c              MODE_ORIGINAL / MODE_ZANAC_MD + ModeAssets
src/player.c            16x16 MSX ship, 8-dir, lives/i-frames/death
src/entity.c            shots + fire-weapon + airborne + boxes/chips/sig + ground 44/70/71/72/82 + type 83
src/map_script.c        13-command jump table (MSX 0x94EB), real scripts
src/data/map_scripts.c  pointer table + lengths (generated)
src/data/spawn_table.c  spawn_table entity list @0xBECC (generated)
src/boot/rom_head.c     game name "ZANAC MD"
res/resources.res
res/map_blob.bin        level data MSX 0x9B64-0xBE26 (generated)
res/charset_tiles.bin   256 SCREEN2 tiles as MD 4bpp (generated)
res/charset_ct.bin      SCREEN2 CT bank, gfx_charset_colors 0x64D3 / 0x5CCF
res/sprites/ship.png    MSX pattern 14 (player ship)
res/sprites/objs.png    MSX pats + type39 compl (+veybar/spinner/sart/loga18+compl/plane16+compl/bolt13/light_bar6/sig26+27/med_circle8)
inc/*.h
tools/extract_map_scripts.py
tools/extract_sound.py   event table + tracks from zanac.asm
res/sound_blob.bin      music/SFX 0x5234-0x5A10 (generated)
src/sound.c             27-event PSG interpreter
```
