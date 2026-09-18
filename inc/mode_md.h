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
 *   MD  playfield  C×D = MODE_MD_W  × MODE_MD_H  = 320×224  (H40 full)
 *
 * Coordinate transform (same relative place on screen):
 *
 *   x_md ≈ x_msx * C/A = x_msx * 320/256 = x_msx * 5/4
 *   y_md ≈ y_msx * D/B = y_msx * 224/192 = y_msx * 7/6
 *
 * TMS Early Clock (SAT colour bit7) is applied *before* the X scale so
 * a ship at SAT 0x78 / colour 0x8F still sits at 88/256 of the width:
 *
 *   MSX (0,0)           → MD (0,0)
 *   MSX (256,192)       → MD (320,224)
 *   MSX SAT X=0x78 EC   → visual 88 → MD 110
 *   MSX SAT Y=0xA0      → MD 186
 *
 * Nametable: 24 MSX playfield cols → 30 H40 cols (24 * 5/4). The leftover
 * 10 cols (80px) are the scaled HUD strip; MD has no WINDOW HUD there.
 * 24 MSX rows → 28 visible rows (24 * 7/6) via a duplicate after every
 * 6 source rows. Map logic / E800 stay 24×24.
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
