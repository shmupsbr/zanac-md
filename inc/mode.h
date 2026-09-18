#ifndef MODE_H
#define MODE_H

#include <genesis.h>
#include "mode_md.h"

typedef enum {
    MODE_ORIGINAL = 0,
    MODE_ZANAC_MD = 1
} GameMode;

/*
 * Asset pack for the active mode. Simulation stays in MSX space;
 * this struct is the render skin. Swap the pointers later to drop
 * in a 320-wide art pack without touching game logic.
 *
 * Original: MSX SCREEN2 256x192 letterboxed in MD H32 256x224
 * (16px top + 16px bottom). Right status bar is 8 tiles / 64px
 * (nametable cols 24-31) overlaid on the 256 map — sprites stay 0-255 X.
 *
 * Zanac MD: H40 320×224. playfield_w/h stay 256×192 (sim / culls /
 * spawns). Display positions go through mode_draw_x/y (see mode_md.h).
 */
typedef struct {
    const SpriteDefinition *ship;
    u16 screen_width;
    u16 playfield_w;    /* sim space: always MODE_MSX_W (256) */
    u16 playfield_h;    /* sim space: always MODE_MSX_H (192) */
    u16 y_off;          /* Original: screen Y = sim Y + 16. MD: unused */
    const char *name;
} ModeAssets;

#define MODE_BAR_COL    24
#define MODE_BAR_W      8
#define MODE_H32_COLS   32              /* H32 nametable width */
#define MODE_SCREEN_H   224
#define MODE_BAR_PX     (MODE_BAR_COL * 8)  /* HUD starts at x=192 */
#define MODE_SPR_W      16                  /* MSX 16x16 SAT; occupancy clip */
/* MSX SAT X clamp 0x28..0xC8 (player_ship_update 0x765C). Colour 0x8F EC
 * draws at SAT−32, so visual 8..168 and the 16px sprite stays left of 192. */
#define MODE_SHIP_MIN_X 0x28
#define MODE_SHIP_MAX_X 0xC8

void mode_init(void);
void mode_set(GameMode mode);
GameMode mode_get(void);
const ModeAssets *mode_assets(void);
void mode_apply_video(void);

/* Sim Y -> sprite/plane screen Y. Original +16 letterbox. Zanac MD:
 * y * 224/192. Collision stays on sim Y. */
s16  mode_draw_y(s16 y);
/* Sim X -> sprite screen X. SAT colour bit7 (TMS EC) is X-32, then
 * Zanac MD scales * 320/256. Draw only — 4560 uses stored SAT X. */
s16  mode_draw_x(s16 x, u8 sat_col);
u16  mode_y_off(void);
u16  mode_text_row(u16 msx_row);

/* BG_B VSRAM low-8: Original scroll_px+16, Zanac MD scroll_px*224/192. */
u16  mode_camera_off(u16 scroll_px);
/* Screen Y of SAT 0 / playfield top. Original 16, Zanac MD 0. */
u16  mode_playfield_top(void);
/* Visible map columns written to BG_B. Original 24, Zanac MD 30. */
u16  mode_map_cols(void);
/* MSX playfield col 0..23 → H40 dest [x0, x0+n). n is 1 or 2. */
void mode_map_dest_cols(u8 msx_col, u8 *x0, u8 *n);
/* 1 if this MSX map-row index occupies two NT rows (24*7/6 = 28). */
int  mode_map_dup_row(u16 msx_row);

/* PAL0 priority black tile used by BG_A letterbox and BG_B unused wrap rows. */
u16  mode_letter_attr(void);
/* 1 if [draw_x, draw_x+width) intersects WINDOW cols 24-31 (x>=192). */
int  mode_hud_overlap(s16 draw_x, u16 width);

/* Black letterbox rows 0-1 / 26-27, full H32 width (Original only).
 * WINDOW covers rows 0-1 full width plus the right HUD (cols 24-31). */
void mode_draw_letterbox(void);

/* explode_enemies 0x8A26 / 90fe: WRTVDP R7=0x0F then R7=0x01.
 * MD: backdrop index 15 plus PAL0[1] (letterbox / HUD backing). */
void mode_backdrop_flash(int on);

#endif
