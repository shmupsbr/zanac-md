#include "hud.h"
#include "hud_logo.h"
#include "mode.h"
#include "player.h"
#include "entity.h"

#define HUD_COL         MODE_BAR_COL
#define HUD_TEXT        (MODE_BAR_COL + 1)

static u8 s_hud_ready;
static u8 s_labels_ok;
static u8 s_time_lbl;

static void hud_fill_bar_backing(void);

/* Opaque PAL0 black on HUD cols 24-31, playfield rows 2-25. Charset 0
 * and SGDK tile 0 are color-0 / leftover white; WPV=2 letterbox must
 * not leave those in the dashboard. Layout 0x4BD4 is drawn on top. */
static void hud_fill_bar_backing(void)
{
    u16 blank;

    if (mode_get() != MODE_ORIGINAL)
        return;
    blank = mode_letter_attr();
    /* WINDOW replaces BG_A in the HUD strip. Charset 01/02/03/20 keep
     * SCREEN2 CT bg=0 (transparent to R7). Punch-through is BG_B, not
     * BG_A. Tile 0x20 is also the 0x96c2 " ROUND n " space on BG_A --
     * do not bake an opaque bg into that shared id. Fill BG_B cols
     * 24-31 so 0x4BDF (03 + six 20 + 03) cannot punch leftover white. */
    VDP_fillTileMapRect(WINDOW, blank, HUD_COL, 2, MODE_BAR_W, 24);
    VDP_fillTileMapRect(BG_A, blank, HUD_COL, 2, MODE_BAR_W, 24);
    VDP_fillTileMapRect(BG_B, blank, HUD_COL, 0, MODE_BAR_W, 32);
}

/* Wipe leftover WINDOW VRAM, then an opaque black HUD backing.
 * SGDK tile 0 (VDP_clearPlane) is not guaranteed blank; charset 0x00 is
 * all color 0 (MD transparent). Fill cols 0-23 with that so a WHP seam
 * at x=192 cannot show a white leftover column on the left of the bar.
 * Do not paint an opaque left bar -- playfield must stay visible. */
static void hud_wipe_window(void)
{
    u16 blank;
    u16 trans;

    blank = mode_letter_attr();
    trans = TILE_ATTR_FULL(PAL3, TRUE, FALSE, FALSE, HUD_TILE_BASE);
    /* WPV=2: rows 0-1 are the 16px letterbox. Charset 0 here is an extra
     * nametable write into the wrap (VSCROLL parks 97e3/peek in Y 8-15).
     * Leave those cells; mode_draw_letterbox restamps opaque PAL0. */
    VDP_fillTileMapRect(WINDOW, trans, 0, 2, MODE_H32_COLS, 26);
    VDP_fillTileMapRect(WINDOW, blank, HUD_COL, 0, MODE_BAR_W, 28);
    VDP_fillTileMapRect(BG_A, blank, HUD_COL, 0, MODE_BAR_W, 28);
    VDP_fillTileMapRect(BG_B, blank, HUD_COL, 0, MODE_BAR_W, 32);
    /* WPV=2 makes rows 0-1 full-width WINDOW. Restore the opaque top bar
     * so charset 0 from the wipe cannot sit in the 16px letterbox. */
    mode_draw_letterbox();
    hud_fill_bar_backing();
}

static u16 hud_y(u16 msx_row)
{
    return mode_text_row(msx_row);
}

static u16 hud_attr(u8 tid)
{
    /* PAL3 TMS charset. Per-row CT: gfx_charset_colors 0x64D3 via
     * decompress_block 0x5CCF (res/charset_ct.bin, one 2048-byte bank). */
    return TILE_ATTR_FULL(PAL3, TRUE, FALSE, FALSE,
                          (u16)(HUD_TILE_BASE + tid));
}

void hud_put_tile(u16 plane, u16 x, u16 y, u8 tid)
{
    VDP_setTileMapXY(plane, hud_attr(tid), x, y);
}

void hud_draw_str(u16 plane, u16 x, u16 y, const char *s)
{
    while (*s)
    {
        hud_put_tile(plane, x, y, (u8)*s);
        x++;
        s++;
    }
}

void hud_fill_tile(u16 plane, u16 x, u16 y, u8 tid, u16 n)
{
    while (n)
    {
        hud_put_tile(plane, x, y, tid);
        x++;
        n--;
    }
}

static void hud_put_win(u16 col, u16 row, u8 tid)
{
    hud_put_tile(WINDOW, col, row, tid);
}

static void hud_str_win(u16 col, u16 row, const char *s)
{
    hud_draw_str(WINDOW, col, row, s);
}

/* 0x4B83: 2 decimal digits, leading zero -> space 0x20. */
static void hud_digit2(u16 col, u16 row, u8 val)
{
    u8 d1;
    u8 d0;

    if (val >= 100)
        val = 99;
    d1 = (u8)(val / 10);
    d0 = (u8)(val % 10);
    hud_put_win(col, row, (u8)(d1 ? ('0' + d1) : ' '));
    hud_put_win((u16)(col + 1), row, (u8)('0' + d0));
}

/* 0x4B8D: 3 decimal digits, leading zeros blanked. Caller SETWRT. */
static void hud_digit3(u16 col, u16 row, u8 val)
{
    u8 d2;
    u8 d1;
    u8 d0;
    u8 nz = 0;

    d2 = (u8)(val / 100);
    d1 = (u8)((val / 10) % 10);
    d0 = (u8)(val % 10);
    hud_put_win(col, row, (u8)((d2 || nz) ? ('0' + d2) : ' '));
    if (d2)
        nz = 1;
    hud_put_win((u16)(col + 1), row, (u8)((d1 || nz) ? ('0' + d1) : ' '));
    hud_put_win((u16)(col + 2), row, (u8)('0' + d0));
}

/* render_score_bcd 0x49B5: 6 digits, leading zeros -> 0x20. */
static void hud_score6(u16 col, u16 row, u32 score)
{
    u8 i;
    u8 nz = 0;

    if (score > 999999UL)
        score = 999999UL;

    for (i = 0; i < 6; i++)
    {
        u32 div = 1;
        u8 k;
        u8 d;

        for (k = 0; k < (u8)(5 - i); k++)
            div *= 10;
        d = (u8)((score / div) % 10);
        if (d || nz)
        {
            hud_put_win((u16)(col + i), row, (u8)('0' + d));
            nz = 1;
        }
        else
            hud_put_win((u16)(col + i), row, ' ');
    }
}

/* render_hex_byte 0x4C74: ADD 0x30, CP 0x3A, ADD 0x07 for A-F. */
static void hud_hex2(u16 col, u16 row, u8 val)
{
    u8 hi = (u8)((val >> 4) & 0xF);
    u8 lo = (u8)(val & 0xF);

    hud_put_win(col, row, (u8)(hi < 10 ? ('0' + hi) : ('A' + (hi - 10))));
    hud_put_win((u16)(col + 1), row, (u8)(lo < 10 ? ('0' + lo) : ('A' + (lo - 10))));
}

/*
 * draw_hud_label_str 0x4BC7: after CALL 0x5C28 the inline bytes are
 * 01 02 02 02 02 02 02 01 00 -- a full-width 8-tile bar at col 24.
 */
static void hud_hbar(u16 msx_row)
{
    static const u8 bar[8] = {
        0x01, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x01
    };
    u16 y = hud_y(msx_row);
    u8 i;

    for (i = 0; i < 8; i++)
        hud_put_win((u16)(HUD_COL + i), y, bar[i]);
}

/*
 * Border loop 0x4BDF: B=0x0E rows from 0x3958.
 * 5C28 prints the bytes after CALL until 00. Assembled inline at 0x4BE2:
 *   INC BC          03
 *   JR NZ,0x4C05    20 20   (disp = 0x4C05-0x4BE5)
 *   JR NZ,0x4C07    20 20
 *   JR NZ,0x4C09    20 20
 *   INC BC          03
 *   NOP             00
 * = 03 20 20 20 20 20 20 03 at cols 24-31 (full 8-tile bar).
 * A 5-tile 03 20 20 20 03 read the JR opcodes as three spaces.
 */
static void hud_draw_border(void)
{
    static const u8 border[8] = {
        0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03
    };
    u8 i;
    u8 c;
    u16 y;

    for (i = 0; i < 14; i++)
    {
        y = hud_y((u16)(10 + i));
        for (c = 0; c < 8; c++)
            hud_put_win((u16)(HUD_COL + c), y, border[c]);
    }
}

static void hud_load_logo(void)
{
    VDP_loadTileData((const u32 *)hud_logo_tiles, HUD_LOGO_VDP,
                     HUD_LOGO_TILES, CPU);
}

/* Static miniature in the empty interior on / above the closing hbar.
 * Cols 25-30 keep the 0x4BDF 03 sides; TIME at MSX row 21 stays clear. */
static void hud_draw_logo(void)
{
    u16 y0 = hud_y(HUD_LOGO_MSX_ROW);
    u16 tid = HUD_LOGO_VDP;
    u8 ty;
    u8 tx;

    for (ty = 0; ty < HUD_LOGO_TILE_H; ty++)
    {
        for (tx = 0; tx < HUD_LOGO_TILE_W; tx++)
        {
            VDP_setTileMapXY(WINDOW,
                             TILE_ATTR_FULL(PAL3, TRUE, FALSE, FALSE, tid),
                             (u16)(HUD_LOGO_COL + tx), (u16)(y0 + ty));
            tid++;
        }
    }
}

static void hud_draw_static_labels(void)
{
    u16 y;

    /*
     * Opaque black behind WINDOW charset (color 0 is transparent on MD).
     * MSX SCREEN2 backdrop is black (R7 BD=1), so punch-through is black.
     * Also replace leftover WINDOW tile 0 so the left HUD edge is not a
     * white stripe (Filipe playtest: listra at the WINDOW/playfield seam).
     */
    hud_wipe_window();

    hud_draw_border();

    /* 0x4C29 / 0x4C2F / 0x4C35 / 0x4C3B / 0x4C41 draw_hud_label_str. */
    hud_hbar(0);
    hud_hbar(3);
    hud_hbar(6);
    hud_hbar(9);
    hud_hbar(23);
    hud_draw_logo();

    /* Inline strings after CALL 0x5C28 (opcodes ARE the ASCII). */
    hud_str_win(HUD_TEXT, hud_y(4), "TOP");         /* 0x3899 */
    hud_str_win(HUD_TEXT, hud_y(7), "SCORE");       /* 0x38F9 */
    hud_str_win(HUD_TEXT, hud_y(10), "ZANAC");      /* 0x3959 */
    hud_str_win(HUD_TEXT, hud_y(12), "LEVEL");      /* 0x3999 */
    hud_str_win(HUD_TEXT, hud_y(15), "ROUND");      /* 0x39F9 */

    y = hud_y(8);
    hud_score6(HUD_COL, y, 0);
    y = hud_y(5);
    hud_score6(HUD_COL, y, player_hiscore());
}

static void hud_ensure_labels(void)
{
    if (!s_hud_ready || s_labels_ok)
        return;
    hud_draw_static_labels();
    s_labels_ok = 1;
}

void hud_init(void)
{
    s_hud_ready = 0;
    s_labels_ok = 0;
    s_time_lbl = 0;
    if (mode_get() != MODE_ORIGINAL)
        return;
    s_hud_ready = 1;
    hud_load_logo();
    /* Display is still off; wipe WINDOW leftover before bg_init shows. */
    hud_wipe_window();
}

void hud_draw_alc(void)
{
    u16 y;

    if (!s_hud_ready)
        return;
    hud_ensure_labels();

    /* base_encounter_ctrl 0xBFD6: "ALC" at 0x3839 then hex at 0x3859. */
    hud_str_win(HUD_TEXT, hud_y(1), "ALC");
    y = hud_y(2);
    hud_hex2(HUD_TEXT, y, entity_e12e());
    hud_hex2((u16)(HUD_TEXT + 2), y, entity_e132());
    hud_hex2((u16)(HUD_TEXT + 4), y, entity_e130());
}

void hud_draw_round(u8 round)
{
    if (!s_hud_ready)
        return;
    hud_ensure_labels();
    /* render_round_digit 0x4C68 -> 0x3A1B row 16 col 27. */
    hud_digit2((u16)(HUD_COL + 3), hud_y(16), round);
}

void hud_draw_time(u8 on, u8 e155)
{
    u16 row;

    if (!s_hud_ready)
        return;
    hud_ensure_labels();

    row = hud_y(21);
    if (!on)
    {
        if (s_time_lbl)
        {
            hud_fill_tile(WINDOW, HUD_TEXT, row, ' ', 6);
            s_time_lbl = 0;
        }
        return;
    }

    /* 0x901A "TIME" at 0x3AB9; value at 0x3ABD via render_hex_byte. */
    if (!s_time_lbl)
    {
        hud_str_win(HUD_TEXT, row, "TIME");
        s_time_lbl = 1;
    }
    hud_hex2((u16)(HUD_COL + 5), row, e155);
}

void hud_draw_player(void)
{
    u32 top;
    u8 lives;
    u8 fire;

    if (!s_hud_ready)
        return;
    hud_ensure_labels();

    /* SCORE @0x3918 row 8 col 24. */
    hud_score6(HUD_COL, hud_y(8), player_score());

    /* score_display_update 0x4AA5: TOP @0x38B8; bit6 flash, bit2 show vs
     * FILVRM 7 spaces. INC E114 every active frame. */
    top = player_top_display();
    if (player_top_flash_blank())
        hud_fill_tile(WINDOW, HUD_COL, hud_y(5), ' ', 7);
    else
        hud_score6(HUD_COL, hud_y(5), top);
    if (player_top_flash_active())
        player_top_flash_tick();

    /* update_status_bar: level @0x39BB row 13 col 27. */
    hud_digit2((u16)(HUD_COL + 3), hud_y(13), player_shot_level());

    /* Lives @0x397A row 11 col 26: DEC E10A; RET Z if zero (no write). */
    lives = player_lives();
    if (lives)
        hud_digit3((u16)(HUD_COL + 2), hud_y(11), (u8)(lives - 1));

    /* update_fire_display 0x7594: "FIRE " @0x3A59, digit @0x3A5E,
     * ammo 3-digit @0x3A7A or 3 spaces if E14B==0. */
    fire = player_fire_num();
    hud_str_win(HUD_TEXT, hud_y(18), "FIRE ");
    hud_put_win((u16)(HUD_TEXT + 5), hud_y(18), (u8)('0' + (fire % 10)));
    if (!fire)
        hud_fill_tile(WINDOW, (u16)(HUD_COL + 2), hud_y(19), ' ', 3);
    else
        hud_digit3((u16)(HUD_COL + 2), hud_y(19), player_fire_ammo());
}
