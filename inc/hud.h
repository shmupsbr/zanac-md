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

/* Dashboard column below FIRE. FIRE stays 18-19; one blank; 6x2 logo;
 * one blank; TIME; closing gray hbar. TIME uses the bottom letterbox
 * HUD corner (screen 26) so the 6x2 is equidistant between FIRE and
 * TIME. TIME is 1 row above the hbar (≤2). */
#define HUD_TIME_MSX_ROW     24
#define HUD_CLOSE_HBAR_ROW   25

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
