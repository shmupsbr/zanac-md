# Zanac MD — assets and what you can do on Mega Drive

Practical guide to finish art for **ZANAC MD** mode. Numbers match `inc/mode_md.h` and `res/resources.res` on `main` (after the centered 1:1 scenery fix).

Simulation and **MSX Enhanced** (`MODE_ORIGINAL`) do not change. This file only describes what you can redraw and how Mega Drive hardware limits the pack.

**Pixel grids** (every current graphic, labeled): see [`docs/asset-grids/`](asset-grids/).

| Sheet | Contents |
| --- | --- |
| [`asset-grids/objs_grid.png`](asset-grids/objs_grid.png) | All 61 `FRAME_*` cells from `objs.png` (16×16), labeled |
| [`asset-grids/objs_frames/`](asset-grids/objs_frames/) | Per-frame PNGs `00_SHOT.png` … `60_SMALL_STAR.png` (×4 nearest) |
| [`asset-grids/ship_grid.png`](asset-grids/ship_grid.png) | Ship bank frames |
| [`asset-grids/ship_frames/`](asset-grids/ship_frames/) | Per-frame ship PNGs |
| [`asset-grids/charset_tiles_grid.png`](asset-grids/charset_tiles_grid.png) | `charset_tiles.bin` as 4×256 8×8 1bpp banks |
| [`asset-grids/title_*.png`](asset-grids/) / `hud_zanac_md_x4.png` | Title and HUD sources scaled with nearest neighbor |

Regenerate with `python tools/extract_asset_grids.py`.

Note: many `*_C` frames in the current `objs.png` are **solid black** (opaque black silhouettes / placeholders). On the grid they appear as filled dark tiles so you can see which indices exist.

---

## Goal

- Finish **ZANAC MD** art **without** new level design.
- **Do not touch MSX Enhanced / Original.** Current `res/sprites/` packs keep serving Enhanced.
- Simulation stays in MSX **256×192** space (events, spawns, SAT, 24-column E800, culls). Only **MD drawing** changes: H40 320×224, sprites in the right place, optional tileset later.

Code source of truth: `inc/mode_md.h` (transform + constants), `src/mode.c` (`mode_draw_x` / `mode_draw_y` / `mode_map_dest_cols`), `res/resources.res` (what the ROM loads today).

---

## Screen

| | MSX Enhanced | Zanac MD |
| --- | --- | --- |
| Playfield | 256×192 + right HUD (cols 24–31) + 16px letterbox top/bottom | 320×224 H40 (`MODE_MD_W` × `MODE_MD_H`) |
| Simulation | 256×192 | **same** — `playfield_w/h` stay 256×192 |
| Map NT | 24 playfield cols | 24 cols **1:1** centered (`MODE_MD_X0 = 8`; dest = 8 + MSX col); gutters 0–7 and 32–39 = sky charset **0x28** |
| Plane | H32 (32 wide) | **64-wide** (`MODE_PLANE_COLS`, `VDP_setPlaneSize(64, 32, TRUE)`) — required in H40 |
| `y_off` | 16 (letterbox) | 0 (1:1 with the 8px grid) |
| Window | right HUD | off (`VDP_setWindowOff`) |

A 32-column plane in H40 wraps cols 32–39 onto 0–7: gutter fill paints the left side of the stage and the right 8 columns repeat the left. That is why MD mode uses a 64-wide plane.

Do not duplicate columns 24→30. That stretched the scenery (repeated garbage). Each MSX column occupies **one** H40 column, centered.

---

## Position transform

Collision stays SAT vs SAT. Only **drawing** goes through `mode_draw_x` / `mode_draw_y`.

### X (sprites)

1. Apply **Early Clock** (SAT color bit 7): TMS hardware draws at `SAT_X − 32`.
2. Then scale **×320/256** (×5/4).

Example (ship): SAT `0x78` with EC (`0x8F`) → MSX visual **88** → MD **110**.

```
x_md ≈ x_msx * 320 / 256
MSX SAT X=0x78 EC → 88 → MD 110
```

### Y (sprites and map)

**1:1** with the 8px grid. MD `y_off` = 0.

Do not apply ×224/192 on the map. That plus row duplication split the scenery mid-screen (wrap rows skipped, live cells overwritten). E800 / wrap / peek / VSCROLL stay on the Original 24-row × 8px grid.

---

## Sprite size transform

Current art is still MSX 16×16 placeholders (`SPRITE … 2 2` in `resources.res`). The MD pack should occupy ~the same screen fraction and **snap** to 8×8 cells (SGDK 1–4 tiles). No runtime scale.

| MSX E×F | Exact (C/A , D/B) | Suggested snap (8×8 tiles) |
| --- | --- | --- |
| 16×16 | 20×18.67 | **24×16** (3×2) or **24×24** (3×3) |
| 16×8 | 20×9.33 | **24×8** (3×1) |
| 8×8 | 10×9.33 | **16×8** (2×1) or **8×8** (1×1) |
| 8×16 | 10×18.67 | **16×16** (2×2) |

Constants: `MODE_MD_SPR_W_EXACT 20`, `MODE_MD_SPR_H_EXACT 18`, placeholder snap `24×16`.

### Ship bank

Today `res/sprites/ship.png` is **32×16**: two 16×16 frames (pat 14 white + pat 15 black). Enhanced draws both (black at same X, Y+2).

MD pack: **32×32** (4×4) or the table snap (24×16 / 24×24). Old frame plan: **neutral + 2 tilt right**; on MD use **horizontal flip** for left. You do not need 2 tilt-left frames on the sheet.

---

## Mega Drive limits (what you can use)

- **80 sprites/frame** hardware; **~20 per scanline** in H40 (16 in H32). Watch bullet rain / discs: the 21st sprite on a line drops.
- Sprites in **8×8** cells up to **4×4 tiles (32×32)**. SGDK `SpriteDefinition` (`SPRITE name "…" W H` in tiles 1–4).
- **4 palettes × 16 colors** (CRAM). Index **0 is transparent** on sprites. One sprite = one palette.
- Planes **A/B + window**; scroll **per pixel** (already used: map VSCROLL + HSCROLL). MD turns the window off; Enhanced uses it for the HUD.
- **VRAM ~64KB** shared by tiles, maps, and sprites. Large MD packs need banking / do not load everything at once.
- **No `VDP_allocateTiles` for runtime scale** — this project's SGDK 2.11 does not expose that. Art is **pre-sized** in the PNG; the ROM only uploads.

MSX complements (`_C`, second black SAT) in Enhanced are a second sprite. In the MD pack you can **bake** black into the same 4bpp (saves SAT and scanline) — RetroDev wires that; until then redraw the pair on the same sheet.

---

## Current files (edit these / MD clones)

`resources.res` today points **both modes** at the same `spr_ship` / `spr_objs` (16×16 cells). The MD pack enters via **new** paths (see Workflow); Enhanced keeps these.

| File | Now | Role | MD action |
| --- | --- | --- | --- |
| `res/sprites/objs.png` | **976×16** (61 frames × 16×16). `SPRITE spr_objs … 2 2` | enemies / shots / FX | Redraw MD pack at table snap. **Do not overwrite** this Original pack if MD is a separate clone |
| `res/sprites/ship.png` | **32×16** (2 frames × 16×16). `SPRITE spr_ship … 2 2` | ship (pat 14 + compl 15) | MD pack 32×32 or table snap |
| `res/charset_tiles.bin` + `charset_ct.bin` | MSX charset (256 4bpp tiles + CT) | scenery tiles | MD tileset **optional later**; scenery today is **1:1 centered MSX tiles** |
| `res/map_blob.bin` | map / scripts | level | **Do not redesign the level** — only a new tileset, if any |
| `res/hud_zanac_md.png` | **48×16** (preview; not in `.res`) | MD HUD logo (`tools/build_hud_logo.py` → `hud_logo.c`) | Safe to retouch |
| `res/title_*.png` | several (below) | title | Retouch OK |
| `res/sound_blob.bin` | 27 AY events | sound | Later (XGM/PCM); Enhanced stays on the PSG interpreter |

Title on disk (retouch OK):

| File | Size | In `resources.res`? |
| --- | --- | --- |
| `res/title_zanac.png` | 224×56 | yes — `IMAGE title_zanac` |
| `res/title_mdmark.png` | 72×40 | yes — `IMAGE title_mdmark` |
| `res/title_logo.png` | 144×40 | source / preview |
| `res/title_md_logo.png` | 224×80 | logo source |
| `res/title_md_source.png` / `title_md_source_old.png` | sources | do not wire directly |

`logo_tiles.bin` and `bg_late.bin` are MSX charset overlays (title / late stages). They are not the map. Do not redesign `map_blob.bin`.

---

## Frames in objs (main `FRAME_*` list)

Defined in `src/entity.c`. `FRAME_N = 61`. Strip is horizontal: frame *i* = pixels `[i*16 .. i*16+16) × 16`.

| Idx | `FRAME_*` | Notes |
| ---: | --- | --- |
| 0 | `SHOT` | shot level 0–1 |
| 1 | `DUSTER` | + `DUSTER_C` (26) |
| 2 | `TERUZO` | + `TERUZO_C` (27) |
| 3 | `LUSTER` | Luster B; + `LUSTER_C` (29) |
| 4 | `BOX` | + `BOX_C` (28) |
| 5 | `CHIP` | power chip / type 83 |
| 6 | `LEAD` | small disc / bolinha |
| 7 | `SIG` | |
| 8 | `SHOT_D` | double shot |
| 9 | `SHOT_T` | triple shot |
| 10 | `FIRE` | fire-0 target |
| 11 | `CIRCLE` | large circle |
| 12 | `COMET` | |
| 13–15 | `DEGID_L` / `DEGID_R` / `DEGID` | |
| 16–20 | `VEYBAR_0` .. `VEYBAR_4` | + `VEYBAR_C0` .. `C4` (21–25) |
| 26 | `DUSTER_C` | |
| 27 | `TERUZO_C` | |
| 28 | `BOX_C` | |
| 29 | `LUSTER_C` | |
| 30 | `UMBER` | + `UMBER_C` (31) |
| 32 | `STEALTH` | + `STEALTH_C` (33) |
| 34–37 | `SPINNER_0` .. `SPINNER_3` | + `SPINNER_C0` .. `C3` (38–41) |
| 42 | `SART` | + `SART_C` (43) |
| 44 | `LOGA` | + `LOGA_C` (45), `LOGA_B` (57), `LOGA_D` (58) |
| 46 | `PLANE` | + `PLANE_C` (47) |
| 48 | `BOLT` | |
| 49 | `LIGHT_BAR` | |
| 50 | `SIG_TRIPLE` | |
| 51 | `SIG_DOUBLE` | |
| 52 | `MED_CIRCLE` | |
| 53 | `LUSTER_A` | + `LUSTER_A_C` (54) |
| 55 | `UMBER_B` | + `UMBER_B_C` (56) |
| 59 | `SNOW` | fire 3/4 |
| 60 | `SMALL_STAR` | |
| 61 | `FRAME_N` | count only, not art |

Short list: `SHOT`, `DUSTER(+C)`, `TERUZO(+C)`, `LUSTER(+C)`, `BOX(+C)`, `CHIP`, `LEAD`, `SIG`, `SHOT_D/T`, `FIRE`, `CIRCLE`, `COMET`, `DEGID_L/R/DEGID`, `VEYBAR_0..4` + `C0..`, `UMBER(+C)`, `STEALTH(+C)`, `SPINNER_0..3` + `C`, `SART(+C)`, `PLANE(+C)`, `LOGA(+C/B/D)`, `BOLT`, `LIGHT_BAR`, `SIG_TRIPLE/DOUBLE`, `MED_CIRCLE`, `LUSTER_A(+C)`, `UMBER_B(+C)`, `SNOW`, `SMALL_STAR`. **`FRAME_N = 61`.**

Many flyers = **color + black** pair (`_C`). Redraw **both** (even if MD later bakes them into one 4bpp sprite).

---

## Workflow

1. Copy/create `res/sprites/md/` (or an MD sheet) **without breaking** Original paths (`res/sprites/ship.png`, `res/sprites/objs.png`).
2. Draw on the **8×8 grid**, indexed PNG, **palette index 0 = transparent**.
3. Tell RetroDev to wire the pack **only** in `MODE_ZANAC_MD` (`ModeAssets` / `mode_init`). New lines in `resources.res` (`SPRITE spr_md_ship` / `spr_md_objs`, `W H` in tiles).
4. Enhanced keeps current `objs` / `ship`.

When the MD PNG exists, the SGDK lines look like:

```
SPRITE spr_md_ship "sprites/md/ship.png" 3 2 NONE 0
SPRITE spr_md_objs "sprites/md/objs.png" 3 2 NONE 0
```

(`3 2` = 24×16 if you take the 16×16→24×16 snap. Adjust W H to the real size.)

---

## Out of scope for now

- **Aleste 2**
- Changing **MSX Enhanced** (logic, sprites, charset, map)
- **New level design** (`map_blob.bin` / round scripts)

An MD scenery tileset can come later; until then MD mode shows MSX tiles 1:1, centered, with sky 0x28 in the gutters.
