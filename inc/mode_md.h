/* Guard must not be MODE_MD_H: that name is the 224-px height constant. */
#ifndef MODE_MD_H_INCLUDED
#define MODE_MD_H_INCLUDED

/*
 * ZANAC MD remaster de/para (display only).
 *
 * Simulation stays in MSX SCREEN2 space — same events, spawns, SAT,
 * map-script rows, and 24-col E800. MODE_ORIGINAL is untouched
 * (256×192 letterbox + right HUD). This header is the MD skin.
 *
 *   MSX playfield  A×B = MODE_MSX_W × MODE_MSX_H = 256×192
 *   MD  screen     C×D = MODE_MD_W  × MODE_MD_H  = 320×224  (H40)
 *
 * X transform (same relative column on the 320-wide screen):
 *
 *   x_md ≈ x_msx * C/A = x_msx * 320/256 = x_msx * 5/4
 *
 * TMS Early Clock (SAT colour bit7) is applied *before* the X scale so
 * a ship at SAT 0x78 / colour 0x8F still sits at 88/256 of the width:
 *
 *   MSX (0,0)           → MD (0,0)
 *   MSX SAT X=0x78 EC   → visual 88 → MD 110
 *   MSX SAT Y=0xA0      → MD 160 (1:1; not *224/192)
 *
 * Y stays 1:1 with the 8px nametable. *224/192 plus a duplicate after
 * every 6th source row looked like mid-screen doubled/broken tiles:
 * wrap NT from a 7/6 camera skips plane rows, wrap-1 overwrites live
 * cells, and stamps still bind tile_wrap + Y/8. E800 / wrap / peek /
 * VSCROLL stay the Original 24-row 8px grid (y_off = 0, no letterbox).
 *
 * Nametable X: 24 MSX playfield cols → 30 H40 cols (24 * 5/4). The
 * leftover 10 cols (80px) are a cleared strip (MD has no WINDOW HUD).
 * Row DMA and cell stamps share mode_map_dest_cols so a wreck sits
 * on the same dest cells the stretched row wrote.
 *
 * Sprite size (occupies ~the same screen fraction; snap to 8×8 / SGDK
 * 1–4 tiles). Art is still the 16×16 MSX placeholders — Filipe redraws
 * later. Do not VDP_allocateTiles for a runtime scale.
 *
 *   MSX E×F     exact G×H (C/A , D/B)   snapped (tiles)
 *   16×16       20 × 18.67              24×16 (3×2)  [24×24 3×3 OK]
 *   16×8        20 × 9.33               24×8  (3×1)
 *   8×8         10 × 9.33               16×8  (2×1) or 8×8 (1×1)
 *   8×16        10 × 18.67              16×16 (2×2)
 */

#define MODE_MSX_W          256
#define MODE_MSX_H          192
#define MODE_MD_W           320
#define MODE_MD_H           224

#define MODE_MSX_PF_COLS    24      /* nametable playfield; HUD 24-31 */
#define MODE_MD_PF_COLS     30      /* 24 * 320/256 = 30 */
#define MODE_H40_COLS       40

#define MODE_MSX_SPR_W      16
#define MODE_MSX_SPR_H      16
/* exact 16 * 320/256 = 20, 16 * 224/192 ≈ 18.67 */
#define MODE_MD_SPR_W_EXACT 20
#define MODE_MD_SPR_H_EXACT 18
/* SGDK-friendly placeholders until the art pack lands. */
#define MODE_MD_SPR_W_SNAP  24
#define MODE_MD_SPR_H_SNAP  16

#endif
