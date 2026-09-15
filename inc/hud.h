#ifndef HUD_H
#define HUD_H

#include <genesis.h>

/*
 * Original-mode right panel. MSX nametable cols 24-31 (WINDOW here).
 * Glyphs are SCREEN2 charset tiles (0x30+digit, 0x20 space), not the
 * SGDK system font. Colors are the 8-byte-per-tile CT at gfx_charset_colors
 * 0x64D3 (decompress_block 0x5CCF; PAL3 TMS). Layout from draw_hud_labels
 * 0x4BD4 inline strings after CALL 0x5C28 / 0x5C25.
 */
#define HUD_TILE_BASE   (TILE_USER_INDEX + 32)

/*
 * Bottom column is playfield-tall (MSX 0-23 / screen 2-25). Do not put
 * TIME or the gray closing hbar in the letterbox (MSX 24-25 / screen
 * 26-27) — that was #123 and left a missing piece at the playfield base.
 *
 * FIRE 18-19 + 6x2 logo + TIME + two equal gaps + hbar 23:
 *   2 + 2 + 1 + 2X rows must fit in MSX 18-22. Only X=0 fits.
 * X=1 needs FIRE on 16-17, which is the ROUND digit (do not collide
 * ROUND / LEVEL / ZANAC). Moving FIRE to 17-18 still yields X=0 (TIME
 * would land on the hbar). Chosen X=0, FIRE left at 18-19:
 *   FIRE 18-19, logo 20-21, TIME 22, gray hbar 23 (screen 25, y_off=16).
 * Rows are disjoint; TIME clear restamps only its own 0x4BDF row.
 */
#define HUD_FIRE_MSX_ROW     18
#define HUD_TIME_MSX_ROW     22
#define HUD_CLOSE_HBAR_ROW   23

void hud_init(void);
void hud_draw_alc(void);
void hud_draw_round(u8 round);
void hud_draw_time(u8 on, u8 e155);
void hud_draw_player(void);

/* Charset tile -> any plane. Original HUD / PAUSE / GAME OVER / banner. */
void hud_put_tile(u16 plane, u16 x, u16 y, u8 tid);
void hud_draw_str(u16 plane, u16 x, u16 y, const char *s);
void hud_fill_tile(u16 plane, u16 x, u16 y, u8 tid, u16 n);

#endif
