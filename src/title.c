#include "title.h"
#include "title_md.h"
#include "title_logo.h"
#include "game.h"
#include "map_script.h"
#include "sound.h"
#include "resources.h"
#include "player.h"
#include "mode.h"

/*
 * Original boot is MSX title_intro_seq 0x5A11:
 *   ev3, wait_frames B=2, SCORE/TOP, 5-bar swirl along logo_swirl_path
 *   0x5B59, draw_title_text, wait fire_edge 0x46BC.
 * Fire during the swirl RET C skips the rest of the intro (logo settles).
 *
 * HIS art, same motion:
 *   BG_B  - blue title_zanac wordmark, 5 staggered strips on the MSX path
 *           (deltas from path[0] mapped onto TITLE_ZANAC_TILE_X/Y).
 *   BG_A  - opaque groove lip + STATIC title_mdmark in front + SCORE/credits.
 * TITLE_MD_Y is 40 (two 8x8 rows under SCORE at TITLE_NT0) so the mark
 * is not cramped against the hiscore. Swirl deltas are unchanged.
 * The MD mark is drawn once at rest and never moves. Color 0 on both planes
 * is transparent, so the blue settles behind the mark.
 *
 * Mode pick stays small: FIRE/START = Original, a dim "ZANAC MD" row can
 * be highlighted. Do not open an SGDK START/OPTIONS menu.
 */

#define TITLE_TILE_BASE     (TILE_USER_INDEX + 32)
#define TITLE_ZANAC_VDP     (TITLE_TILE_BASE + 256)
#define BG_TILE             TILE_USER_INDEX
#define TITLE_NT0           2               /* 16px letterbox → MSX row 0 */
#define TITLE_COLS          32
#define PLANE_TH            32
#define SWIRL_WAIT          2               /* wait_frames B=2 at 0x5AA9 */

#define PHASE_PREWAIT       0
#define PHASE_SWIRL         1
#define PHASE_WAIT          2

static u8 s_phase;
static u8 s_sel;            /* 0 Original, 1 Zanac MD */
static u16 s_prev;
static u8 s_wait;
static u8 s_swirl[5];       /* E1FA..E1FE */
static u16 s_mdmark_vdp;

/* 7-tile-tall wordmark → 5 swirl bars. MSX used 5×1; the HIS underline is
 * 3 tiles so it travels as the last bar. dest Y = path_row + src_y, the
 * same stagger as draw_logo_row's (row + i). */
static const u8 k_bar_src_y[5] = { 0, 1, 2, 3, 4 };
static const u8 k_bar_h[5]     = { 1, 1, 1, 1, 3 };

/* Entry 12 is TMS_DARK_GREEN, not RGB24_TO_VDPCOLOR(0x21B03B): the macro
 * collides it with colour 2 and flattens the terrain. See inc/map_script.h. */
static const u16 k_tms[16] = {
    RGB24_TO_VDPCOLOR(0x000000),
    RGB24_TO_VDPCOLOR(0x000000),
    RGB24_TO_VDPCOLOR(0x21C842),
    RGB24_TO_VDPCOLOR(0x5EDC78),
    RGB24_TO_VDPCOLOR(0x5455ED),
    RGB24_TO_VDPCOLOR(0x7D76FC),
    RGB24_TO_VDPCOLOR(0xD4524D),
    RGB24_TO_VDPCOLOR(0x42EBF5),
    RGB24_TO_VDPCOLOR(0xFC5554),
    RGB24_TO_VDPCOLOR(0xFF7978),
    RGB24_TO_VDPCOLOR(0xD4C154),
    RGB24_TO_VDPCOLOR(0xE6CE80),
    TMS_DARK_GREEN,
    RGB24_TO_VDPCOLOR(0xC95BBA),
    RGB24_TO_VDPCOLOR(0xCCCCCC),
    RGB24_TO_VDPCOLOR(0xFFFFFF)
};

static const u16 k_tms_dim[16] = {
    RGB24_TO_VDPCOLOR(0x000000),
    RGB24_TO_VDPCOLOR(0x000000),
    RGB24_TO_VDPCOLOR(0x0F5A1E),
    RGB24_TO_VDPCOLOR(0x2A6335),
    RGB24_TO_VDPCOLOR(0x25266A),
    RGB24_TO_VDPCOLOR(0x383572),
    RGB24_TO_VDPCOLOR(0x5F2422),
    RGB24_TO_VDPCOLOR(0x1D696E),
    RGB24_TO_VDPCOLOR(0x712625),
    RGB24_TO_VDPCOLOR(0x733636),
    RGB24_TO_VDPCOLOR(0x5F5725),
    RGB24_TO_VDPCOLOR(0x675C39),
    RGB24_TO_VDPCOLOR(0x0F4F1A),
    RGB24_TO_VDPCOLOR(0x5A2953),
    RGB24_TO_VDPCOLOR(0x5C5C5C),
    RGB24_TO_VDPCOLOR(0x737373)
};

static u8 charset_tile(char c)
{
    u8 t = (u8)c;

    if (t >= 'a' && t <= 'z')
        t = (u8)(t - 'a' + 'A');
    if (t == ' ' || t == '.' || t == '@'
        || (t >= '0' && t <= '9') || (t >= 'A' && t <= 'Z'))
        return t;
    return ' ';
}

static void put_tile(u16 x, u16 y, u8 tid, u16 pal)
{
    u16 tile = (u16)(TITLE_TILE_BASE + tid);

    VDP_setTileMapXY(BG_A, TILE_ATTR_FULL(pal, FALSE, FALSE, FALSE, tile), x, y);
}

static void draw_str_pal(const char *s, u16 x, u16 y, u16 pal)
{
    while (*s)
    {
        put_tile(x, y, charset_tile(*s), pal);
        x++;
        s++;
    }
}

static void draw_str_cx_pal(const char *s, u16 y, u16 pal)
{
    u16 len = (u16)strlen(s);
    u16 x = (len < TITLE_COLS) ? (u16)((TITLE_COLS - len) / 2) : 0;

    draw_str_pal(s, x, y, pal);
}

static u16 fire_mask(void)
{
    return (u16)(BUTTON_A | BUTTON_C | BUTTON_START);
}

static int fire_edge(u16 pressed)
{
    return (pressed & fire_mask()) != 0;
}

static void load_bg_tile(void)
{
    static const u32 black[8] = {
        0x11111111, 0x11111111, 0x11111111, 0x11111111,
        0x11111111, 0x11111111, 0x11111111, 0x11111111
    };

    VDP_loadTileData(black, BG_TILE, 1, CPU);
}

/* BG_A lid: tile 0 (transparent) above the slot so BG_B blue shows against
 * the backdrop; opaque black from TITLE_GROOVE_ROW down buries the rest. */
static void fill_groove(void)
{
    u16 attr = TILE_ATTR_FULL(PAL0, FALSE, FALSE, FALSE, BG_TILE);

    VDP_fillTileMapRect(BG_A, 0, 0, 0, TITLE_COLS, TITLE_GROOVE_ROW);
    VDP_fillTileMapRect(BG_A, attr, 0, TITLE_GROOVE_ROW,
                        TITLE_COLS, (u16)(28 - TITLE_GROOVE_ROW));
}

static void fill_letterbox(void)
{
    u16 attr = TILE_ATTR_FULL(PAL0, FALSE, FALSE, FALSE, BG_TILE);

    VDP_fillTileMapRect(BG_A, attr, 0, 0, TITLE_COLS, TITLE_NT0);
    VDP_fillTileMapRect(BG_A, attr, 0, 26, TITLE_COLS, 2);
}

static void load_title_tiles(void)
{
    VDP_loadTileData((const u32 *)charset_tiles, TITLE_TILE_BASE, 256, CPU);
    /* Credit AII marks still live in the MSX overlay (tiles 0xE7..0xEC). */
    VDP_loadTileData((const u32 *)logo_tiles,
                     (u16)(TITLE_TILE_BASE + LOGO_TILE_MSX_FIRST),
                     LOGO_TILE_COUNT, CPU);

    VDP_waitDMACompletion();
    s_mdmark_vdp = TITLE_ZANAC_VDP + title_zanac.tileset->numTile;
    VDP_loadTileSet(title_zanac.tileset, TITLE_ZANAC_VDP, CPU);
    VDP_loadTileSet(title_mdmark.tileset, s_mdmark_vdp, CPU);
}

static void draw_mdmark(void)
{
    VDP_setTileMapEx(BG_A, title_mdmark.tilemap,
                     TILE_ATTR_FULL(PAL1, FALSE, FALSE, FALSE, s_mdmark_vdp),
                     TITLE_MDMARK_TILE_X, TITLE_MDMARK_TILE_Y,
                     0, 0, TITLE_MDMARK_TILE_W, TITLE_MDMARK_TILE_H, CPU);
}

static void setup_title_palettes(void)
{
    PAL_setPalette(PAL0, k_tms, CPU);
    PAL_setPalette(PAL1, title_md_palette, CPU);
    PAL_setPalette(PAL2, k_tms_dim, CPU);
    PAL_setPalette(PAL3, k_tms, CPU);
    VDP_setBackgroundColor(0);
}

/* 0x3803 SCORE / 0x3811 TOP, then render_lives_score 0x4996. */
static void draw_score_top(void)
{
    char buf[8];
    u32 n;
    u8 i;
    u8 nz;
    u32 div;
    u8 d;
    u16 row = TITLE_NT0;

    draw_str_pal("SCORE", 3, row, PAL3);
    draw_str_pal("TOP", 17, row, PAL3);

    n = player_score();
    if (n > 999999UL)
        n = 999999UL;
    nz = 0;
    for (i = 0; i < 6; i++)
    {
        u8 k;

        div = 1;
        for (k = 0; k < (u8)(5 - i); k++)
            div *= 10;
        d = (u8)((n / div) % 10);
        if (d || nz || i == 5)
        {
            buf[i] = (char)('0' + d);
            nz = 1;
        }
        else
            buf[i] = ' ';
    }
    buf[6] = 0;
    draw_str_pal(buf, 9, row, PAL3);

    n = player_hiscore();
    if (n > 999999UL)
        n = 999999UL;
    nz = 0;
    for (i = 0; i < 6; i++)
    {
        u8 k;

        div = 1;
        for (k = 0; k < (u8)(5 - i); k++)
            div *= 10;
        d = (u8)((n / div) % 10);
        if (d || nz || i == 5)
        {
            buf[i] = (char)('0' + d);
            nz = 1;
        }
        else
            buf[i] = ' ';
    }
    buf[6] = 0;
    draw_str_pal(buf, 21, row, PAL3);
}

/* Path 0x5B59 is MSX nametable cells. Index 0 is rest (7,5); map the delta
 * onto Filipe's HIS rest pose so the chase shape is unchanged. */
static void lookup_swirl(u8 a, s16 *col, s16 *row)
{
    u8 i = (u8)(a << 1);

    *col = (s16)((s16)logo_swirl_path[i]
                 - (s16)logo_swirl_path[0]
                 + TITLE_ZANAC_TILE_X);
    *row = (s16)((s16)logo_swirl_path[i + 1]
                 - (s16)logo_swirl_path[1]
                 + TITLE_ZANAC_TILE_Y);
}

/* Clip to the 32-wide H32 view so the wordmark falls off the edge instead
 * of wrapping, the way draw_logo_row 0x5BA0 clipped n = 32-col. */
static void blit_zanac_bar(s16 dest_x, s16 dest_y, u8 src_y, u8 h, int draw)
{
    s16 x = dest_x;
    s16 y = dest_y;
    u8 sx = 0;
    u8 sy = src_y;
    u8 w = TITLE_ZANAC_TILE_W;

    if (!h)
        return;
    if (x >= (s16)TITLE_COLS || y >= (s16)PLANE_TH)
        return;
    if (x < 0)
    {
        if ((s16)(-x) >= (s16)w)
            return;
        sx = (u8)(-x);
        w = (u8)(w - sx);
        x = 0;
    }
    if ((u16)x + w > TITLE_COLS)
        w = (u8)(TITLE_COLS - (u16)x);
    if (y < 0)
    {
        u8 skip;

        if ((s16)(-y) >= (s16)h)
            return;
        skip = (u8)(-y);
        sy = (u8)(sy + skip);
        h = (u8)(h - skip);
        y = 0;
    }
    if ((u16)y + h > PLANE_TH)
        h = (u8)(PLANE_TH - (u16)y);
    if (!w || !h)
        return;

    if (draw)
        VDP_setTileMapEx(BG_B, title_zanac.tilemap,
                         TILE_ATTR_FULL(PAL1, FALSE, FALSE, FALSE, TITLE_ZANAC_VDP),
                         (u16)x, (u16)y, sx, sy, w, h, CPU);
    else
        VDP_fillTileMapRect(BG_B, 0, (u16)x, (u16)y, w, h);
}

static void draw_zanac_bar(u8 i, s16 col, s16 row, int draw)
{
    blit_zanac_bar(col, (s16)(row + k_bar_src_y[i]),
                   k_bar_src_y[i], k_bar_h[i], draw);
}

/* draw_title_text 0x5AC8. Nametable rows + letterbox. */
static void draw_title_text(void)
{
    static const u8 k_mark0[3] = { 0xE7, 0xE9, 0xEB };
    static const u8 k_mark1[3] = { 0xE8, 0xEA, 0xEC };
    u8 i;

    draw_str_pal("GAME DESIGNED BY COMPILE", 3, (u16)(TITLE_NT0 + 15), PAL3);
    draw_str_pal("PRODUCED      BY AII", 3, (u16)(TITLE_NT0 + 16), PAL3);
    draw_str_pal("PRESENTED     BY PONY INC.", 3, (u16)(TITLE_NT0 + 17), PAL3);
    draw_str_pal("COPYRIGHT @ 1986 PONY INC.", 3, (u16)(TITLE_NT0 + 18), PAL3);
    /* Port credit. Same PAL3 charset and col 3 as the MSX lines above. */
    draw_str_pal("MD Conversion by SHMUPSBR", 3, (u16)(TITLE_NT0 + 19), PAL3);
    for (i = 0; i < 3; i++)
    {
        put_tile((u16)(14 + i), (u16)(TITLE_NT0 + 20), k_mark0[i], PAL3);
        put_tile((u16)(14 + i), (u16)(TITLE_NT0 + 21), k_mark1[i], PAL3);
    }
}

static void swirl_init(void)
{
    u8 i;
    u8 a = 0x1C;

    for (i = 0; i < 5; i++)
    {
        s_swirl[i] = a;
        a = (u8)(a + 4);
    }
}

/* One body of LAB_ram_5a4a. Returns 1 when all 5 bars have reached 0. */
static int swirl_step(void)
{
    u8 i;
    u8 done = 0;
    s16 col;
    s16 row;
    u8 a;

    for (i = 0; i < 5; i++)
    {
        a = s_swirl[i];
        if (!a || a >= 0x1C)
            continue;
        lookup_swirl(a, &col, &row);
        draw_zanac_bar(i, col, row, 0);
    }

    for (i = 0; i < 5; i++)
    {
        a = s_swirl[i];
        a--;
        if ((s8)a < 0)
        {
            done++;
            a++;
        }
        s_swirl[i] = a;
        if (a >= 0x1C)
            continue;
        lookup_swirl(a, &col, &row);
        draw_zanac_bar(i, col, row, 1);
    }
    return (done >= 5);
}

static void swirl_settle(void)
{
    u8 i;
    s16 col;
    s16 row;
    u8 a;

    /* Erase whatever is still in flight, then park every bar at rest.
     * a == 0 is already home (skip erase); a >= 0x1C has not entered. */
    for (i = 0; i < 5; i++)
    {
        a = s_swirl[i];
        if (!a || a >= 0x1C)
            continue;
        lookup_swirl(a, &col, &row);
        draw_zanac_bar(i, col, row, 0);
    }
    lookup_swirl(0, &col, &row);
    for (i = 0; i < 5; i++)
        draw_zanac_bar(i, col, row, 1);
}

static void draw_mode_hint(void)
{
    /* Small, not a full menu. Default Original; MD is the dim second line. */
    draw_str_cx_pal("FIRE START", (u16)(TITLE_NT0 + 22), PAL3);
    draw_str_cx_pal("ORIGINAL", (u16)(TITLE_NT0 + 23),
                    (s_sel == 0) ? PAL3 : PAL2);
    draw_str_cx_pal("ZANAC MD", (u16)(TITLE_NT0 + 24),
                    (s_sel == 0) ? PAL2 : PAL3);
}

static void enter_wait(void)
{
    s_phase = PHASE_WAIT;
    s_sel = 0;
    swirl_settle();
    draw_title_text();
    draw_mode_hint();
}

static void confirm_start(void)
{
    GameMode mode = (s_sel == 0) ? MODE_ORIGINAL : MODE_ZANAC_MD;
    u16 joy = JOY_readJoypad(JOY_1);

    /* Debug warps stay START-held modifiers so fire (A/C) starts the game. */
    if ((joy & BUTTON_START) && (joy & BUTTON_C))
        game_start_round(mode, map_script_continue_round());
    else if ((joy & BUTTON_START) && (joy & BUTTON_B))
        game_start_ending(mode);
    else if ((joy & BUTTON_START) && (joy & BUTTON_A))
        game_start_round(mode, 8);
    else
        game_start(mode);
}

void title_enter(void)
{
    s_phase = PHASE_PREWAIT;
    s_sel = 0;
    s_prev = JOY_readJoypad(JOY_1);
    s_wait = SWIRL_WAIT;
    swirl_init();

    VDP_setEnable(FALSE);
    VDP_setWindowOff();
    VDP_setScreenWidth256();

    map_script_reset_scroll();
    VDP_setScrollingMode(HSCROLL_PLANE, VSCROLL_PLANE);
    VDP_setHorizontalScroll(BG_A, 0);
    VDP_setVerticalScroll(BG_A, 0);
    VDP_setHorizontalScroll(BG_B, 0);
    VDP_setVerticalScroll(BG_B, 0);
    VDP_clearPlane(BG_A, TRUE);
    VDP_clearPlane(BG_B, TRUE);
    VDP_clearPlane(WINDOW, TRUE);
    SPR_reset();

    load_bg_tile();
    setup_title_palettes();
    load_title_tiles();
    fill_groove();
    fill_letterbox();
    /* MD mark is the front layer from frame 0; it does not swirl. */
    draw_mdmark();
    sound_play_title();
}

void title_update(void)
{
    u16 joy = JOY_readJoypad(JOY_1);
    u16 pressed = (u16)(joy & ~s_prev);

    if (s_phase == PHASE_PREWAIT)
    {
        /* 0x5A11 fire_edge before load still applies: skip straight to wait. */
        if (fire_edge(pressed))
        {
            VDP_setEnable(TRUE);
            draw_score_top();
            enter_wait();
            s_prev = joy;
            return;
        }
        if (s_wait)
        {
            s_wait--;
            if (!s_wait)
            {
                VDP_setEnable(TRUE);
                draw_score_top();
                draw_title_text();
                s_phase = PHASE_SWIRL;
                s_wait = 0;
            }
        }
        s_prev = joy;
        return;
    }

    if (s_phase == PHASE_SWIRL)
    {
        if (fire_edge(pressed))
        {
            enter_wait();
            s_prev = joy;
            return;
        }
        if (s_wait)
        {
            s_wait--;
            s_prev = joy;
            return;
        }
        if (swirl_step())
            enter_wait();
        else
            s_wait = SWIRL_WAIT;
        s_prev = joy;
        return;
    }

    if (pressed & (BUTTON_UP | BUTTON_DOWN))
    {
        s_sel ^= 1;
        draw_mode_hint();
    }

    if (fire_edge(pressed))
    {
        if (joy & BUTTON_DOWN)
            s_sel = 1;
        confirm_start();
    }

    s_prev = joy;
}
