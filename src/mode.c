#include "mode.h"
#include "resources.h"

static GameMode s_mode;
static ModeAssets s_original;
static ModeAssets s_md;
static const ModeAssets *s_cur;

#define LETTER_TILE     TILE_USER_INDEX

static void load_letter_tile(void)
{
    /* Color 1 = black (color 0 is always transparent on MD). */
    static const u32 black[8] = {
        0x11111111, 0x11111111, 0x11111111, 0x11111111,
        0x11111111, 0x11111111, 0x11111111, 0x11111111
    };
    /* VDP_clearPlane / title groove index tile 0. Leftover title or
     * SGDK font pixels punch through SCREEN2 CT bg=0 (empty 0x28 sky)
     * into the visible top. All color-0 = backdrop (R7 black). Do not
     * stamp high-pri letter tiles on the playfield. */
    static const u32 clear0[8] = {
        0x00000000, 0x00000000, 0x00000000, 0x00000000,
        0x00000000, 0x00000000, 0x00000000, 0x00000000
    };

    VDP_loadTileData(black, LETTER_TILE, 1, CPU);
    VDP_loadTileData(clear0, 0, 1, CPU);
    PAL_setColor(1, RGB24_TO_VDPCOLOR(0x000000));
}

void mode_init(void)
{
    s_original.ship = &spr_ship;
    s_original.screen_width = 256;
    s_original.playfield_w = MODE_MSX_W;
    s_original.playfield_h = MODE_MSX_H;
    s_original.y_off = 16;
    s_original.name = "ORIGINAL";

    /* Display is H40 320×224 via mode_draw_*; sim culls stay 256×192. */
    s_md.ship = &spr_ship;
    s_md.screen_width = MODE_MD_W;
    s_md.playfield_w = MODE_MSX_W;
    s_md.playfield_h = MODE_MSX_H;
    s_md.y_off = 0;
    s_md.name = "ZANAC MD";

    s_mode = MODE_ZANAC_MD;
    s_cur = &s_md;
}

void mode_set(GameMode mode)
{
    s_mode = mode;
    s_cur = (mode == MODE_ORIGINAL) ? &s_original : &s_md;
}

GameMode mode_get(void)
{
    return s_mode;
}

const ModeAssets *mode_assets(void)
{
    return s_cur;
}

s16 mode_draw_y(s16 y)
{
    /* Both modes: sim Y + letterbox. Zanac MD y_off is 0 so this is 1:1
     * with wrap/peek (8px tiles). Do not *224/192 — that plus a 24→28
     * nametable dup skipped wrap rows and doubled a band mid-screen. */
    return (s16)(y + (s16)s_cur->y_off);
}

s16 mode_draw_x(s16 x, u8 sat_col)
{
    /* TMS9918 SAT colour bit7 = Early Clock: hardware draws at SAT_X-32.
     * Ship, shots, and EC enemies all use this so SAT overlap = graphic
     * overlap. Collision never calls this (4560 is SAT vs SAT). */
    if (s_mode == MODE_ORIGINAL)
    {
        if (sat_col & 0x80)
            return (s16)(x - 32);
        return x;
    }
    /* ZANAC MD: same EC, then * 320/256 so the visual column matches. */
    if (sat_col & 0x80)
        x = (s16)(x - 32);
    return (s16)(((s32)x * (s32)MODE_MD_W) / (s32)MODE_MSX_W);
}

u16 mode_letter_attr(void)
{
    return TILE_ATTR_FULL(PAL0, TRUE, FALSE, FALSE, LETTER_TILE);
}

int mode_hud_overlap(s16 draw_x, u16 width)
{
    s16 bar;
    s16 right;

    if (s_mode != MODE_ORIGINAL)
        return 0;
    bar = (s16)MODE_BAR_PX;
    if (draw_x >= bar)
        return 1;
    right = (s16)(draw_x + (s16)width);
    return (right > bar);
}

u16 mode_y_off(void)
{
    return s_cur->y_off;
}

u16 mode_text_row(u16 msx_row)
{
    return (u16)(msx_row + (s_cur->y_off / 8));
}

u16 mode_camera_off(u16 scroll_px)
{
    return (u16)((scroll_px + s_cur->y_off) & 0xFF);
}

u16 mode_playfield_top(void)
{
    return s_cur->y_off;
}

u16 mode_map_cols(void)
{
    if (s_mode == MODE_ORIGINAL)
        return MODE_MSX_PF_COLS;
    return MODE_MD_PF_COLS;
}

void mode_map_dest_cols(u8 msx_col, u8 *x0, u8 *n)
{
    u8 a;
    u8 b;

    if (msx_col >= MODE_MSX_PF_COLS)
    {
        *x0 = MODE_MD_PF_COLS;
        *n = 0;
        return;
    }
    a = (u8)((u16)msx_col * MODE_MD_PF_COLS / MODE_MSX_PF_COLS);
    b = (u8)((u16)(msx_col + 1) * MODE_MD_PF_COLS / MODE_MSX_PF_COLS);
    *x0 = a;
    *n = (u8)(b - a);
}

void mode_apply_video(void)
{
    if (s_mode == MODE_ORIGINAL)
    {
        VDP_setScreenWidth256();
        /* L-window: rows 0-1 full width (16px letterbox) so BG_B wrap/peek
         * in NT 31 cannot show through a transparent BG_A cell. Rows 2-27
         * keep the right 8 tiles (WHP 12 = col 24). Bottom 16px stays BG_A. */
        VDP_setWindowHPos(TRUE, 12);
        VDP_setWindowVPos(FALSE, 2);
        load_letter_tile();
        PAL_setColor(0, RGB24_TO_VDPCOLOR(0x000000));
        VDP_setBackgroundColor(0);
    }
    else
    {
        VDP_setWindowOff();
        VDP_setScreenWidth320();
        /* Same PAL0 black tile Original uses for wrap/HUD backing, so
         * unused H40 cols 30-39 and NT 24-31 cannot keep title garbage. */
        load_letter_tile();
    }
}

void mode_draw_letterbox(void)
{
    u16 attr;

    if (s_mode != MODE_ORIGINAL)
        return;

    attr = mode_letter_attr();
    /* Screen rows 0-1 and 26-27: 16px letterbox. Full H32 width so
     * transparent WINDOW cells in cols 24-31 cannot show BG_B wrap. */
    VDP_fillTileMapRect(BG_A, attr, 0, 0, MODE_H32_COLS, 2);
    VDP_fillTileMapRect(BG_A, attr, 0, 26, MODE_H32_COLS, 2);
    /* WPV=2: rows 0-1 are full-width WINDOW. Opaque PAL0 black here hides
     * the NT 31 peek that VSCROLL parks in screen Y 8-15. Bottom letterbox
     * is opaque across the full width, including HUD cols 24-31 — TIME
     * and the closing hbar sit on the playfield (MSX 22 / 23), not here. */
    VDP_fillTileMapRect(WINDOW, attr, 0, 0, MODE_H32_COLS, 2);
    VDP_fillTileMapRect(WINDOW, attr, MODE_BAR_COL, 26, MODE_BAR_W, 2);
}

void mode_backdrop_flash(int on)
{
    /* 8A26 / 90fe: WRTVDP R7=0x0F (BD=15 white) then R7=0x01 (black).
     * TMS color 0 is transparent to that backdrop. MD color 0 is always
     * transparent, so the visible black is PAL0[1] (letterbox tile and
     * HUD BG_B backing). Flash that index plus the backdrop register.
     * Do not touch PAL2/PAL3 (half-greens / map stay). */
    if (s_mode != MODE_ORIGINAL)
        return;
    VDP_setBackgroundColor(on ? 15 : 0);
    PAL_setColor(1, RGB24_TO_VDPCOLOR(on ? 0xFFFFFF : 0x000000));
    PAL_setColor(15, RGB24_TO_VDPCOLOR(on ? 0xFFFFFF : 0xE0E0E0));
}
