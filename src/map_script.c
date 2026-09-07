#include "map_script.h"
#include "map_scripts.h"
#include "mode.h"
#include "entity.h"
#include "player.h"
#include "resources.h"
#include "sound.h"
#include "hud.h"
#include <string.h>

/*
 * 13-command jump table, matching MSX 0x94EB.
 * Operand grammar from zanac-re/tools/decode_mapscript2.py.
 *
 * PC is an MSX address into map_blob (base 0x9B64). Cmd 9 dest is an MSX
 * address; resolve_round_from_ptr walks the 0x945C table high-to-low.
 */

#define COL_SLOTS       16
#define COL_READ        4       /* scroll_map_reader B=4 at 0x98D2 */
#define STREAM_SLOTS    8
#define MAX_FIRE        16
#define BG_TILE_BASE    (TILE_USER_INDEX + 32)
#define ASM_W           32      /* MSX work buffer 0xEA40, fill to 0x20 */
#define ASM_SKIP        8       /* commit 24 bytes from 0xEA48 */
#define PF_COLS         24      /* name-table playfield; HUD cols 24-31 */
#define BOOT_ROWS       24      /* MSX build_tile_screen B=0x18 */

typedef struct {
    u8  pos;            /* IY+0 column X; 0x80 = inactive */
    u8  param;          /* IY+1 table/offset bits */
    u16 ptr;            /* IY+2:3 column-descriptor cursor */
    u16 src;            /* IY+4:5 tile-source cursor */
    u8  t6;             /* IY+6 per-column width timer */
    u8  t7;             /* IY+7 run count */
} ColSlot;

/* Inner tile-stream slots @0xE2E0 (cmd 5 / cmd B). */
typedef struct {
    u8  used;
    u8  ybase;          /* IY+0 column X in the 24-tile row */
    u8  count;          /* remaining tile-runs (IY+1) */
    u8  delay;          /* timed slot countdown (cmd 5 bit3) */
    u16 ptr;
} StreamSlot;

static MapScript s_ms;
static ColSlot s_col[COL_SLOTS];
static StreamSlot s_stream[STREAM_SLOTS];
static u8  s_idol_cur;          /* IX+0x1D wide-structure table cursor */
static u16 s_bg_base;
static u8  s_rowbuf[ASM_W];
static u16 s_tbl[8];            /* 0xE2AC word table (tile_tables) */
static u8  s_fill_param;        /* IX+0x17 */
static u8  s_asm_x;             /* IX+0x19 assembled width */

/* scroll_velocity_ctrl 0x9480: E710+=E711, carry -> map_script_step (row++). */
#define SCROLL_SPEED_TGT    0x34
#define SCROLL_SPEED_CRED   0x80
static u8  s_e710;              /* current_scroll_speed */
static u8  s_e711;              /* scroll_timing_acc */
static u8  s_e712;              /* target_scroll_speed */
static u8  s_e713;              /* velocity_timer (mod 4) */
static u8  s_e152;              /* last bit7 group count (E151->E152) */
static u8  s_e153;              /* cmd B threshold (0x976c) */
static u8  s_e155;              /* cmd B E155 */
static u8  s_e156;              /* cmd B approach countdown */
static u8  s_e157;              /* cmd B encounter mode */
static u8  s_e158;              /* cmd B E158 */
static u8  s_e159;              /* 8fca copy of E155 */
static u16 s_e15a;              /* 8f5e hold timer, armed = 0x00C0 */
static u8  s_e154;              /* BCD hold-timer low (seconds), word with E155 */
static u8  s_time_on;           /* TIME HUD at 0x3AB9 / 0x3ABD */
static u8  s_clr_phase;         /* 90a6/91a6 non-blocking sequencer */
static u16 s_clr_wait;
static u8  s_clr_mode;          /* E157&0x1F latched at 90a6 */
static u8  s_boot_quiet;        /* type-72 warp: skip boot/ending default BGM */
static u8  s_warp_jingle;       /* 1 = ev11 playing; wait 0x64 then load */
static u16 s_warp_jwait;
static u8  s_warp_old;
static u8  s_warp_new;
static u16 s_warp_dest;         /* E722: load after wait_frames(0x64), not before */
/* 40DA CALL 4177: walk 24x24 E800 onto VRAM (blank before wait, reveal
 * after 940c). Japan is a blocking VDP walk (~3 frames); we step it. */
static u8  s_dump_h;
static u8  s_dump_l;
static u16 s_dump_left;
static u8  s_dump_phase;        /* 0 idle, 1 blank, 2 reveal */
static u8  s_defer_nt_flush;    /* script_boot assembles E800; 4177 reveals */
static u8  s_nt[32][PF_COLS];   /* VRAM playfield shadow, 24-col */
static u8  s_e800[BOOT_ROWS][PF_COLS]; /* MSX E800 circular 24x24 */
static u8  s_e714;              /* E714 circular write index 0-23 */
static u8  s_e700;              /* E700: bit0 vram-pending, bit1 row-carry,
                                 * bit2 980e column-reveal, bit3 first-sync */
static u8  s_e70d;              /* E70D: 980e remaining column steps */
/* 91FD LDIRVM E800 -> VRAM 0x3C00 is TMS scratch (24x24). MD has no 0x3C00
 * window; keep the stash in RAM so the playfield restore is exact. */
static u8  s_3c00[BOOT_ROWS][PF_COLS];
static u8  s_eb00[BOOT_ROWS][PF_COLS]; /* 91FD LDIR E800 -> EB00 */
static u8  s_end_snapped;       /* 980e flushed E714=0 linear NT 0-23 */
static u8  s_end_phase;         /* 9251 sequencer; 0 = idle */
static u8  s_end_wait;
static u8  s_end_rows;          /* remaining 9263 iterations */
static u8  s_end_y;             /* SAT Y for 92f3; starts 0x4C */
static u8  s_end_tms_row;       /* TMS nametable row; starts 9 (0x3924) */
/* scroll_speed_ramp_table 0x8F9A; 8f5e indexes 0x8F99+countdown (1-9). */
static const u8 k_approach[10] = {
    0x00, 0x0C, 0x11, 0x14, 0x17, 0x1A, 0x1D, 0x20, 0x23, 0x26
};
/* cmd11_index_table 0x976c: E157&0x1F -> E153. */
static const u8 k_e153[17] = {
    0x00, 0x02, 0x02, 0x00, 0x03, 0x03, 0x02, 0x03,
    0x03, 0x03, 0x04, 0x01, 0x00, 0x00, 0x00, 0x07, 0x03
};
/* base_clear_award_index_table 0x9302. */
static const u8 k_clear_award[19] = {
    0x0A, 0x0C, 0x0D, 0x10, 0x0E, 0x0F, 0x0E, 0x0F,
    0x0F, 0x10, 0x11, 0x11, 0x00, 0x00, 0x00, 0x11,
    0x12, 0x13, 0x14
};
/* Intentional MD enhancement: TMS nametable is 8px steps (97e3 on
 * E711 carry). VSCROLL uses the leftover E711>>5 so the plane slides
 * 1px/tick at E710=0x20. Do not snap this to 8. Stamps stay tile_wrap. */
static u16 s_scroll_px;         /* pixel VSCROLL = 8*(row-base) + (E711>>5) */
static u8  s_scroll_delta;      /* pixels advanced this frame */
static u8  s_row_carry;         /* E700 bit 1: 97e3 ran this frame */
static u16 s_scroll_base;       /* E702 after build_tile_screen; VSCROLL 0 */
static u8  s_skip_precompute;   /* cmd 9 941b RET: this step does not 97e3 */
static u8  s_ram_only;          /* boot: assemble E800 without poking VRAM */
static u8  s_assemble_peek;     /* peek assemble: tiles only, no place */
static u8  s_wrap_pending;      /* 97e3 row waiting for post-88ed DMA */
static u8  s_wrap_nt;           /* hidden_wrap(pre) latched at 97e3 */
/* Two DMA_QUEUE HUD sources -- SGDK stores the pointer until vblank.
 * Playfield is 24-col CPU (Japan 9a79); only the HUD slice is queued.
 * Original pads dst[24-31] so the restore cannot leak leftover charset. */
static u16 s_dma_row[2][MODE_H32_COLS];
static u8  s_dma_flip;
static TransferMethod s_row_tm = DMA_QUEUE;
static ColSlot s_col_snap[COL_SLOTS];
static StreamSlot s_stream_snap[STREAM_SLOTS];

static void stream_stamp_buf(void);
static void arm_ending_stream(void);
static void scroll_speed_reset(u8 target);
static void fire_pending(void);
static void scroll_precompute(u16 map_row);
static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm);
static void peek_next_row_at(u16 map_row, u16 wrap_px);
static void peek_next_row(u16 map_row);
static u8 hidden_wrap_nt_at(u16 scroll_px);
static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row);
static void fill_letterbox_b(void);
static void bg_set_vscroll(void);
static void base_mode_11(void);
static void place_ctrl_at(u16 ptr);
static void scroll_sync(void);
static void lab_980e(void);
static void ending_setup_91fd(void);
static void lab_9251_start(void);
static void lab_9251_tick(void);
static void base_hold(void);
static void base_clear_tick(void);
static void script_boot(u8 round, u16 pc);
static void warp_commit_load(void);
static void warp_jingle_tick(void);
static void recolor_charset_tile(u8 tid, const u8 *ct8);
static void recolor_charset_tile_fill(u8 tid, u8 ct);
#if MAP_HAS_CHARSET
static void apply_hud_charset_ct(void);
#endif

/* credits_control_table 0x4775 + length-prefixed strings 0x47AA (ASCII only). */
#define CRED_ROW0       5
#define CRED_WAIT_PAGE  0x190
#define CRED_WAIT_LAST  0x4B0
#define CRED_SETTLE     0x50

static const u8 k_cred_ctrl[] = {
    0x01, 0x00, 0x06, 0x0A, 0x07, 0xFF,
    0x02, 0x00, 0x0A, 0x07, 0xFF,
    0x10, 0x00, 0x0B, 0xFF,
    0x04, 0x00, 0x07, 0xFF,
    0x04, 0x02, 0x00, 0x07, 0xFF,
    0x03, 0x00, 0x06, 0x0C, 0xFF,
    0x0E, 0x00, 0x0F, 0x11, 0x09, 0xFF,
    0x17, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
    0x00, 0x05, 0x00, 0x0A, 0x00, 0x00, 0x0D, 0x08, 0x0D, 0xFF,
    0xFF
};

static const char *const k_cred_str[] = {
    "GAME DESIGN", "PROGRAM", "GRAPHICS", "SOUND", "DIRECTOR",
    "JANUS", "JEMINI", "COMPILE", "WAO", "MOO",
    "MIYAMOTO", "YORIKI", "       ", "THANKS", "PAL",
    "MUSIC", "LUNARIAN"
};
#define CRED_NSTR   17

static u8  s_cred_on;
static u8  s_cred_exit;
static u8  s_cred_idx;
static u16 s_cred_wait;
static u8  s_cred_settle;
static u16 s_cred_age;
static u8  s_cred_dirty;

/* MSX E701 continue: last round reached this power cycle (title + C). */
static u8  s_continue_round = 1;
static u8  s_banner_bgm_arm;

static const char *const s_cmd_name[13] = {
    "spawn_ctrl", "place_tiles", "col_groups", "tile_copy",
    "col_groups+", "stream_slots", "set_E71C", "disable_grps",
    "idol_tbl/BANNER", "SCRIPT_JUMP", "vram_glyph", "wide_slot",
    "spawn_pace"
};

typedef void (*MapCmdFn)(u8 cmd, const u8 *ops);

static u16 read_le16(const u8 *p)
{
    return (u16)p[0] | ((u16)p[1] << 8);
}

static int blob_ok(u16 addr, u16 n)
{
    if (addr < MAP_BLOB_BASE || addr > MAP_BLOB_END)
        return 0;
    if (n && ((u16)(MAP_BLOB_END - addr) + 1) < n)
        return 0;
    return 1;
}

static const u8 *blob_at(u16 addr)
{
    if (!blob_ok(addr, 1))
        return NULL;
    return map_blob + (addr - MAP_BLOB_BASE);
}

static u8 resolve_round_from_ptr(u16 dest)
{
    u8 i;

    /* First 8 table entries, highest address first. Below round-1 -> 0. */
    for (i = 0; i < 8; i++)
    {
        if (dest >= map_script_ptrs[i])
            return (u8)(8 - i);
    }
    return 0;
}

static u16 cmd5_len(const u8 *ops)
{
    u8 n = ops[0];
    u16 q = 1;
    u8 i;

    for (i = 0; i < n; i++)
    {
        u8 b0 = ops[q];
        q += (b0 & 0x08) ? 5 : 4;
    }
    return q;
}

static u16 op_len(u8 cmd, const u8 *ops)
{
    u8 nib = cmd & 0x0F;
    u8 n;

    switch (nib)
    {
        case MAPCMD_SPAWN_CTRL:
            if (ops[0] & 0x04)
            {
                n = ops[1];
                return (u16)(1 + 1 + 3 * n);
            }
            return 1;
        case MAPCMD_PLACE_TILES:
            n = ops[0];
            return (u16)(1 + 3 * n);
        case MAPCMD_COL_GROUPS:
        case MAPCMD_COL_GROUPS_ADD:
            n = ops[0];
            return (u16)(1 + 5 * n);
        case MAPCMD_TILE_COPY:
            n = ops[0];
            return (u16)(1 + 2 * n);
        case MAPCMD_STREAM_SLOTS:
            return cmd5_len(ops);
        case MAPCMD_SET_E71C:
            return 1;
        case MAPCMD_DISABLE_GRPS:
            n = ops[0];
            return (u16)(1 + n);
        case MAPCMD_IDOL_BANNER:
            return 2;
        case MAPCMD_SCRIPT_JUMP:
            return 2;
        case MAPCMD_VRAM_GLYPH:
            return 1;
        case MAPCMD_WIDE_SLOT:
            return 7;
        case MAPCMD_SPAWN_PACE:
            return 1;
        default:
            return 0;
    }
}

/* ---- TMS9918 palette on PAL3, charset (or dummy) on BG_B ---- */

/* TMS9918A palette as Mega Drive colours.
 *
 * Entry 12 is NOT written through RGB24_TO_VDPCOLOR, and that is the point.
 * The macro rounds each channel up by 0x10 before masking to the MD's 3 bits,
 * which maps TMS 2 (0x21C842) and TMS 12 (0x21B03B) onto the SAME colour,
 * 0x4C2. Those two greens are the entire ground texture: charset tiles 0x25,
 * 0x26 and 0x27 are nothing but a 2/12 stipple, so collapsing them renders
 * every land tile as one flat green. Measured: with the whole playfield forced
 * to tile 0x26, the frame contained a single green (49,206,87) and no second
 * one, while the same scene on openMSX is roughly half colour 2 and half
 * colour 12.
 *
 * Plain nearest-level rounding does not help -- both greens round to 0x4A2 --
 * so the pair has to be separated on purpose. Searching every distinguishable
 * MD pair for the lowest channel error while keeping the original luminance
 * gap (14.9) gives 2 -> 0x4C2, 12 -> 0x4A2: squared error 660, gap 21.7, the
 * best of the field. Entry 2 keeps the value it already had, so this changes
 * exactly one colour. */
static const u16 s_tms_pal[16] = {
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

static void select_tables(u16 map_row)
{
    u16 ph3 = (u16)(map_row & 3);
    u16 ph7 = (u16)(map_row & 7);

    /* scroll_map_reader 0x9888: E2AE/B0/B2 from E702; E2B4/B6 fixed. */
    s_tbl[0] = 0xA444;
    s_tbl[1] = (u16)(0xA444 + ph3 * 24);
    s_tbl[2] = (u16)(0xA4A4 + ph7 * 24);
    s_tbl[3] = (u16)(0xA564 + ph7 * 24);
    s_tbl[4] = 0xA624;
    s_tbl[5] = 0xA63C;
    s_tbl[6] = 0xA444;
    s_tbl[7] = 0xA444;
}

static u8 rom_tile(u16 addr)
{
    const u8 *p = blob_at(addr);

    return p ? *p : 0x28;
}

static void row_put(u16 x, u8 tid)
{
    if (x < ASM_W)
        s_rowbuf[x] = tid;
}

static void row_fill_tbl(u8 tidx, u16 src_off, u16 dst, u16 n)
{
    u16 i;
    u16 base = s_tbl[tidx & 7];

    for (i = 0; i < n; i++)
        row_put((u16)(dst + i), rom_tile((u16)(base + src_off + i)));
}

/* LAB_98f6: HL at count byte. */
static void col_fetch_from(ColSlot *s, u16 hl)
{
    u16 guard;

    /* 0x98f6 has no iteration cap: it loops on b0 == 0 (jump) and b0 == 0xFF
     * (inline skip) until it reaches a real record.  A 0xFF chain walks the
     * stream one record at a time and is legitimately long, so the cap only
     * exists to stop malformed data hanging the frame -- 8 was low enough to
     * kill live slots. */
    for (guard = 0; guard < 512; guard++)
    {
        const u8 *p;
        u8 b0;
        u16 tgt;

        p = blob_at(hl);
        if (!p || !blob_ok(hl, 4))
        {
            s->pos = 0x80;
            return;
        }
        s->t7 = p[0];
        hl = (u16)(hl + 1);
        s->ptr = hl;
        p = blob_at(hl);
        if (!p || !blob_ok(hl, 3))
        {
            s->pos = 0x80;
            return;
        }
        b0 = p[0];
        s->t6 = b0;
        tgt = read_le16(p + 1);
        if (b0 == 0x00)
        {
            hl = tgt;
            continue;
        }
        if (b0 == 0xFF)
        {
            /* 0x990d CP 0xFF / 0x9911 pos += t7 / 0x991a EX DE,HL / 0x991b DEC
             * HL / 0x991c JR 0x98f6.  At 0x9909 EX DE,HL left DE = ptr+2, so
             * after the second EX DE,HL and the DEC, HL is ptr+1 -- the stream
             * CONTINUES INLINE at the byte right after b0.  The two bytes read
             * as `tgt` are not a target: they are the next count byte and the
             * next b0.  Jumping to tgt-1 sent the reader outside the blob, the
             * blob_ok guard then latched pos = 0x80 and the column slot died
             * mid-scroll, so the land stopped on a hard horizontal line and the
             * base fill took over from that row down. */
            s->pos = (u8)(s->pos + s->t7);
            hl = (u16)(s->ptr + 1);
            continue;
        }
        s->src = tgt;
        return;
    }
    s->pos = 0x80;
}

/* LAB_9901: ptr already at b0 of the current 4-byte record. */
static void col_refetch_b0(ColSlot *s)
{
    const u8 *p;
    u8 b0;
    u16 tgt;

    p = blob_at(s->ptr);
    if (!p || !blob_ok(s->ptr, 3))
    {
        s->pos = 0x80;
        return;
    }
    b0 = p[0];
    s->t6 = b0;
    tgt = read_le16(p + 1);
    if (b0 == 0x00)
    {
        col_fetch_from(s, tgt);
        return;
    }
    if (b0 == 0xFF)
    {
        /* Same 0x991a EX DE,HL / DEC HL continuation as col_fetch_from. */
        s->pos = (u8)(s->pos + s->t7);
        col_fetch_from(s, (u16)(s->ptr + 1));
        return;
    }
    s->src = tgt;
}

/* Japan column stream into EA40; commit 24 tiles from EA48 (ASM_SKIP 8).
 * Coast / island edges are those stream bytes — do not invent stamps. */
static void col_paint(ColSlot *s)
{
    u8 bx;
    u8 cx;
    u8 tidx;
    u8 row;
    u8 len;
    u8 i;
    u16 dst;
    const u8 *p;

    if (s->pos == 0x80)
        return;
    if (s->pos >= 0x28)
    {
        s->pos = 0x80;
        return;
    }

    bx = s->pos;
    cx = s_asm_x;
    dst = cx;

    if (cx < bx)
    {
        tidx = (u8)((s->param >> 4) & 7);
        row_fill_tbl(tidx, cx, cx, (u16)(bx - cx));
        dst = bx;
    }
    else
        dst = bx;

    p = blob_at(s->src);
    if (!p || !blob_ok(s->src, 2))
        return;
    row = p[0];
    len = p[1];
    if (len && blob_ok(s->src, (u16)(2 + len)))
    {
        if (s->param & 0x80)
        {
            u8 add = (u8)((s->param & 0x08) ? 0x2E : 0x17);

            for (i = 0; i < len; i++)
                row_put((u16)(dst + i), (u8)(p[2 + i] + add));
        }
        else
        {
            for (i = 0; i < len; i++)
                row_put((u16)(dst + i), p[2 + i]);
        }
        dst = (u16)(dst + len);
    }
    s->src = (u16)(s->src + 2 + len);
    s_asm_x = (u8)(len + bx);
    s->pos = (u8)(s->pos + row);
    s_fill_param = s->param;
    (void)dst;
}

static void col_step(ColSlot *s)
{
    if (s->pos == 0x80)
        return;

    if (s->t6)
        s->t6--;
    if (!s->t6)
    {
        if (!s->t7)
            col_refetch_b0(s);
        else
        {
            s->t7--;
            if (s->t7)
                col_refetch_b0(s);
            else
                col_fetch_from(s, (u16)(s->ptr + 3));
        }
    }
    if (s->pos != 0x80)
        col_paint(s);
}

static void bind_col_slot(u8 slot, u8 status, u8 param, u16 entry, u8 additive)
{
    ColSlot *s;

    slot &= 0x0F;
    s = &s_col[slot];
    if (additive)
        s->pos = (u8)(s->pos + status);
    else
        s->pos = status;
    s->param = param;
    s->ptr = entry;
    s->src = 0;
    s->t6 = 1;
    s->t7 = 1;
}

static void assemble_row(u16 map_row)
{
    u8 i;

    select_tables(map_row);
    for (i = 0; i < ASM_W; i++)
        s_rowbuf[i] = 0x28;

    s_fill_param = s_ms.e71c;
    s_asm_x = 0;

    for (i = 0; i < COL_READ; i++)
        col_step(&s_col[i]);

    if (s_asm_x < ASM_W)
        row_fill_tbl((u8)(s_fill_param & 7), s_asm_x, s_asm_x,
                     (u16)(ASM_W - s_asm_x));

    stream_stamp_buf();
}

static u16 tile_attr(u8 tid)
{
    return TILE_ATTR_FULL(PAL3, FALSE, FALSE, FALSE,
                          (u16)(s_bg_base + (tid & 0xFF)));
}

/* NT row at the top of the 192 (screen Y 16 / SAT Y 0).
 * VSCROLL = -(scroll_px + 16); plane_y(16) = 16 - off.
 * At leftover E711 frac 1-7 this is the peek sliver (1-2px), not the
 * 8px tile 97e3 wrote — see tile_wrap_nt_at. Y=8 (letterbox mid) is one
 * row north of the aligned top; do not DMA 97e3 there. */
static u8 hidden_wrap_nt_at(u16 scroll_px)
{
    u16 off = (u16)((scroll_px + mode_y_off()) & 0xFF);
    u8 py = (u8)(16 - off);

    return (u8)(py >> 3);
}

/*
 * 8px nametable cell that holds TMS row 0 (Japan 8948 Y/8).
 * hidden_wrap(raw) at leftover E711 frac 1-7 is the peek sliver (1-2px
 * at the playfield top / letterbox). 97e3 DMA still uses wrap(pre-carry)
 * RAW — that equals this aligned slot. #95 sat_to_nt wrap+(Y/8) on RAW
 * scroll parked 87e2/88ed/8c15 on wrap(post)==peek: missing digits,
 * dest tiles one row off (purple L-mark leftover), and a sky/green cut.
 */
static u8 tile_wrap_nt_at(u16 scroll_px)
{
    return hidden_wrap_nt_at((u16)(scroll_px & 0xFFF8));
}

/*
 * One nametable row. Japan 9a79 OUT's BC=0x18 playfield tiles from
 * E800 at nametable col 0 (stride 0x20, HUD 24-31 untouched).
 *
 * Original used to DMA_QUEUE 32 H32 cols (HUD pad) then restore 24-31.
 * That 32-word queued burst dropped the first cell: playfield col 0
 * kept leftover 0x28 sky. Invisible over water; at a coast it is the
 * left-edge blue notch. Do not invent shore tiles — write the 24-col
 * stream, first cell included.
 *
 * Gameplay writes those 24 with CPU (Japan's per-tile OUT) so SGDK
 * DMA_QUEUE cannot skip word 0. Boot uses DMA while the display is
 * off. HUD cols 24-31 still restore via tm (WINDOW 0x20 CT bg=0).
 */
static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)
{
    u8 x;
    u16 *dst;
    TransferMethod play_tm;

    nt_y &= 31;
    dst = s_dma_row[s_dma_flip];
    for (x = 0; x < PF_COLS; x++)
    {
        s_nt[nt_y][x] = src[x];
        dst[x] = tile_attr(src[x]);
    }
    /* 9a79 B=0x18 at col 0. Do not expand to MODE_H32_COLS. */
    play_tm = (tm == DMA_QUEUE) ? CPU : tm;
    VDP_setTileMapDataRow(BG_B, dst, nt_y, 0, PF_COLS, play_tm);
    if (mode_get() == MODE_ORIGINAL)
    {
        u16 blank = mode_letter_attr();

        for (; x < MODE_H32_COLS; x++)
            dst[x] = blank;
        /* Restore cols 24-31 after the playfield write so WINDOW
         * punch-through stays letter backing (0x4BDF six 0x20).
         * Same tm: DMA_QUEUE restore commits in vblank. One row x 8
         * tiles -- not a playfield fill, not a per-tick letterbox. */
        VDP_setTileMapDataRow(BG_B, dst + MODE_BAR_COL, nt_y,
                              MODE_BAR_COL, MODE_BAR_W, tm);
    }
    /* DMA_QUEUE keeps the HUD source pointer until vblank -- do not
     * reuse this buffer while that restore is queued. */
    if (tm == DMA_QUEUE)
        s_dma_flip ^= 1;
    /* Letterbox is clipped once per frame in bg_set_vscroll. Filling
     * four rects here on every 1-row DMA hitch the 60Hz loop. */
}

/*
 * 9a79 display order onto the 32-row plane: NT row i =
 * E800[(E714+i) mod 24]. Newest sits at NT 0. VSCROLL = -scroll_px - y_off
 * then puts NT 0 at the top of the 192 and reveals wrap 31,30,... as
 * pixels. TMS has no VSCROLL; those wrap pixels fall in the 16px bars.
 */
static void flush_boot_playfield(void)
{
    u8 i;

    for (i = 0; i < BOOT_ROWS; i++)
        dma_nt_row(i, s_e800[(u8)((s_e714 + i) % BOOT_ROWS)], DMA);
}

/*
 * Unused 32-row wrap (NT 24-31 at boot) is the same PAL0 black tile as
 * BG_A letterbox -- never charset 0x28. Prefetch overwrites NT 31 with map.
 * Full H32 width: cols 24-31 of a wrap row are otherwise leftover VRAM.
 */
static void fill_letterbox_b(void)
{
    if (mode_get() != MODE_ORIGINAL)
        return;

    VDP_fillTileMapRect(BG_B, mode_letter_attr(), 0, BOOT_ROWS, MODE_H32_COLS,
                        (u16)(32 - BOOT_ROWS));
}

/*
 * TMS nametable row 0 is screen row 0 (no VSCROLL, 24 rows). MD 32-row
 * plane plus 16px letterbox must start at VSCROLL = -scroll_px - y_off so
 * NT 0 sits at the top of the 192, not in screen Y 0-15.
 * VSRAM is 10-bit; the plane wraps at 256px -- keep the low 8 bits.
 */
static void bg_set_vscroll(void)
{
    u16 off;

    VDP_setVerticalScroll(BG_A, 0);
    off = (u16)((s_scroll_px + mode_y_off()) & 0xFF);
    VDP_setVerticalScroll(BG_B, (s16)(-(s16)off));
    /* Letterbox tiles live on BG_A / WINDOW (VSCROLL 0). They are
     * stamped once at boot / hud_wipe. Filling them every tick was a
     * second VRAM burst on top of SYS_doVBlankProcess. */
}

/* 97e3 scroll_precompute: DEC E714 (wrap 0->23), assemble once. */
static void scroll_precompute(u16 map_row)
{
    u8 x;

    /* Real 97e3 always places. A leaked s_assemble_peek from wrap
     * preview would skip entity_place_ground / entity_base_open so
     * nametable idols/bases appear with no 44CA hitbox. */
    s_assemble_peek = 0;

    if (!s_e714)
        s_e714 = BOOT_ROWS - 1;
    else
        s_e714--;

    assemble_row(map_row);
    for (x = 0; x < PF_COLS; x++)
        s_e800[s_e714][x] = s_rowbuf[ASM_SKIP + x];
    if (s_ram_only)
        return;
    /* Wrap NT is still wrap(pre) RAW — VSCROLL has not moved. Japan 9a79
     * copies E800 in vblank after 87e2/88ed. DMA_QUEUE snapshots s_dma_row
     * now would flush that pre-punch assemble over the digit/wreckage
     * XY poke (script=1, never retried). Latch and DMA after punches. */
    s_wrap_nt = hidden_wrap_nt_at(s_scroll_px);
    if (s_row_tm != DMA_QUEUE)
        dma_nt_row(s_wrap_nt, s_e800[s_e714], s_row_tm);
    else
        s_wrap_pending = 1;
}

void map_script_commit_wrap(void)
{
    if (!s_wrap_pending)
        return;
    s_wrap_pending = 0;
    dma_nt_row(s_wrap_nt, s_e800[s_e714], s_row_tm);
}

/*
 * Subpixel VSCROLL (E711>>5) reveals the next map row 1-7 px before the
 * E711-carry that runs 97e3. Peek that row into the wrap NT, then restore
 * column/stream cursors so col_step is not advanced twice (PR #1).
 * Commands still run only on the real carry (not during the peek).
 */
static void peek_next_row_at(u16 map_row, u16 wrap_px)
{
    u8 x;
    u8 line[PF_COLS];
    u8 idol_snap;

    if (s_ram_only)
        return;
    memcpy(s_col_snap, s_col, sizeof(s_col));
    memcpy(s_stream_snap, s_stream, sizeof(s_stream));
    idol_snap = s_idol_cur;
    /* Tile preview of row+1 only. place_tile_group / 95ed must not
     * spawn: a delay that hits 0 here would place, then restore the
     * stream so the next real 97e3 places again (stacked bases).
     * Always clear after assemble — 97e3 also forces 0 before place. */
    s_assemble_peek = 1;
    assemble_row(map_row);
    s_assemble_peek = 0;
    for (x = 0; x < PF_COLS; x++)
        line[x] = s_rowbuf[ASM_SKIP + x];
    /* wrap_px selects the playfield-top NT the next 1-8px of VSCROLL
     * will reveal. In-game wrap_px is scroll_px+8 so peek does not
     * overwrite this carry's 97e3 row. */
    dma_nt_row(hidden_wrap_nt_at(wrap_px), line, s_row_tm);
    memcpy(s_col, s_col_snap, sizeof(s_col));
    memcpy(s_stream, s_stream_snap, sizeof(s_stream));
    s_idol_cur = idol_snap;
}

static void peek_next_row(u16 map_row)
{
    /* After 97e3 already filled hidden_wrap_nt_at(scroll_px) (playfield
     * top). +8 is the next SAT-Y-0 row so the peek does not overwrite
     * the carry row. */
    peek_next_row_at(map_row, (u16)(s_scroll_px + 8));
}

/* 8ca2 / 88ed: stamp into circular E800 + the displayed nametable row. */
static void nt_put(u8 col, u8 row, u8 tid)
{
    u8 vis;
    u8 wrap;

    if (col >= PF_COLS)
        return;
    row &= 31;
    s_nt[row][col] = tid;
    VDP_setTileMapXY(BG_B, tile_attr(tid), col, row);

    /* 9a79: screen i = E800[(E714+i) mod 24]. Playfield top is NT[(-k)&31]
     * after k = scroll_px/8 wraps, so vis i = (nt_row - first) & 31. */
    {
        u8 k = (u8)(s_scroll_px >> 3);
        u8 first = (u8)((0 - k) & 31);

        vis = (u8)((row - first) & 31);
        if (vis < BOOT_ROWS)
            s_e800[(u8)((s_e714 + vis) % BOOT_ROWS)][col] = tid;
    }
    /* Wrap/letterbox NT (hidden_wrap_nt_at) is e800[e714] -- the newest
     * map row. vis>=24 skipped that slot, so a later wrap DMA restored
     * the live tiles and half the original sprite scrolled with the map. */
    wrap = hidden_wrap_nt_at(s_scroll_px);
    if (row == wrap)
        s_e800[s_e714][col] = tid;
}

/* 8948: E800[(E714 + Y/8) mod 24][X/8] is the source wrap DMA reads.
 * Write that slot first (MSX), then the NT cell now showing playfield Y. */
static void punch_cell(u8 col, u8 screen_row, u8 tid)
{
    u8 nt_col;
    u8 nt_row;

    if (col >= PF_COLS || screen_row >= BOOT_ROWS)
        return;
    s_e800[(u8)((s_e714 + screen_row) % BOOT_ROWS)][col] = tid;
    if (!sat_to_nt((s16)((u16)col << 3), (s16)((u16)screen_row << 3),
                   &nt_col, &nt_row))
        return;
    (void)nt_col;
    s_nt[nt_row][col] = tid;
    VDP_setTileMapXY(BG_B, tile_attr(tid), col, nt_row);
}

/*
 * Japan 8948: TMS VRAM row is Y/8 from the top of the 192 (no VSCROLL).
 * E800 index is (E714 + Y/8) mod 24. MD VSCROLL parks that 8px tile at
 * tile_wrap_nt_at (wrap of scroll&~7), so the cell showing SAT Y is
 *   (tile_wrap + Y/8) & 31
 * #95 used hidden_wrap(raw)+Y/8. At leftover E711 frac 1-7 wrap(raw) is
 * the peek sliver (wrap(post)), one NT row north of 97e3's wrap(pre)
 * tile — 87e2 digits in the letterbox, 88ed dest leftover on the live
 * row, 8c15/stamps cutting a sky line through green.
 * x is already nametable pixel X (SAT-32). C>=0x18 reject stays.
 */
static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row)
{
    u8 c;
    u8 sat_row;

    if (x < 0)
        return 0;
    c = (u8)((u16)x >> 3);
    if (c >= PF_COLS)
        return 0;
    /* 88ed: C = Y/8 on the 192; C>=0x18 -> no punch. Y is the 8948 L
     * (aligned punch origin), unsigned like MSX SUB on SAT Y.
     * SAT Y walks +8 per E700.1 (8f25/8a5a/8f45). MD VSCROLL also has
     * E711>>5 subpixels; bind with the 8px row so the stamp hits the
     * 1-row DMA cell (MSX nametable has no subpixel scroll). Sprite DRAW
     * adds (scroll_px & 7) in entity.c; SAT/collision stay on this grid.
     * The stamp then rides live VSCROLL with the rest of the nametable,
     * so wreck tiles are not crooked vs neighboring tiles. */
    if (y < 0)
        return 0;
    sat_row = (u8)((u16)y >> 3);
    if (sat_row >= BOOT_ROWS)
        return 0;
    *col = c;
    *row = (u8)((tile_wrap_nt_at(s_scroll_px) + sat_row) & 31);
    return 1;
}

/* 8854 / 8ca2 SUB 0x20: nametable pixel X of the tiles the player sees.
 * Original stamps SAT_X-32 so the art sits with EC sprites; 4560 still
 * uses stored SAT X. Zanac MD has no EC -- stamp at SAT X. */
static s16 nt_from_sat_x(s16 sat_x)
{
    if (mode_get() == MODE_ORIGINAL)
        return (s16)(sat_x - 0x20);
    return sat_x;
}

/* 0x964C: A=ybase; ADD A,A*3; ADD blob_X; SUB 0x20. All 8-bit.
 * 16-bit add sent R1 west blob 0xE8 (ybase 0x15) to SAT 368→clamp 248;
 * Japan SAT is 112. 8948 then rejected col 27 and the left eye never
 * opened. Unsigned SUB 0x20 is still Japan 8a92; it is not this bug. */
static s16 sat_x_964c(u8 ybase, u8 blob_x)
{
    return (s16)(u8)((u8)((u8)(ybase << 3) + blob_x) - 0x20);
}

/* type62 8744: LDIRVM 0x20 bytes from 876b+(phase?0x20:0) -> VRAM 0x1800.
 * 24-col playfield only -- HUD cols 24-31 untouched. */
static const u8 k_riser_nt[2][32] = {
    {
        0x07,0x1F,0x3F,0x7F,0x43,0x81,0xE1,0xE1,
        0x81,0x43,0x7F,0x30,0x1C,0x17,0xD0,0x38,
        0xC0,0xF0,0xF8,0xFC,0x84,0x02,0xC2,0xC2,
        0x02,0x84,0xFC,0x18,0x70,0xD0,0x16,0x38
    },
    {
        0x07,0x1F,0x3F,0x7F,0x43,0x81,0x87,0x87,
        0x81,0x43,0x7F,0x30,0x9F,0xA7,0x40,0x20,
        0xC0,0xF0,0xF8,0xFC,0x84,0x02,0x0E,0x0E,
        0x02,0x84,0xFC,0x18,0xF2,0xCA,0x04,0x08
    }
};

void map_script_type62_poke(u8 phase)
{
    u8 i;
    const u8 *src = k_riser_nt[phase & 1];
    /* Top of the 192: NT row that VSCROLL currently places at sim Y=0. */
    u8 top = (u8)((-(s16)s_scroll_px >> 3) & 31);

    for (i = 0; i < PF_COLS; i++)
        nt_put(i, top, src[i]);
}

/* LAB_ram_90fe / 9118: 0xE800 x 0x240. D==2: A0+ -> E7, A7-AA -> +0x3C.
 * D==1: E3-E7 -> 3E, E3-E6 -> -0xA9. 24-col only (HUD 24-31 stays). */
static void sweep_nametable(u8 d)
{
    u8 row;
    u8 col;

    for (row = 0; row < 32; row++)
    {
        for (col = 0; col < PF_COLS; col++)
        {
            u8 t = s_nt[row][col];
            u8 n;

            if (d == 2)
            {
                if (t < 0xA0)
                    continue;
                n = 0xE7;
                if (t >= 0xA7 && t < 0xAB)
                    n = (u8)(t + 0x3C);
            }
            else
            {
                if (t < 0xE3 || t >= 0xE8)
                    continue;
                n = 0x3E;
                if (t != 0xE7)
                    n = (u8)(t - 0xA9);
            }
            nt_put(col, row, n);
        }
    }
}

static void punch_bind(s16 x, s16 y, u8 variant)
{
    u8 col;
    u8 row;
    u8 w;
    u8 h;
    u8 tiles[9];
    u8 r;
    u8 c;
    u8 ysub;

    /* 8ca2: B=SAT_X-0x20, H=SAT_X-0x1C, C=SAT_Y-0x10, L=SAT_Y-0x0C, then
     * 75 (0x4B) JP 88ed with HL; 76 (0x4C) JR 8cd6 (skips LD L,C) so H=B
     * and L stays Y-0x0C; 77 (0x4D) LD L,C then JP 88ed; 73/74/78 fall
     * through LD L,C / DE=8cda / LD H,B so X-0x20 Y-0x10.
     * Type 75/76 table yo=0xFC: live Y-0x10 floors one 8px row above the
     * 8c15 bind cell (8948 after Y+0x10, before xo/yo). */
    if (variant == 75 || variant == 77)
        x = (s16)(x - 0x1C);
    else
        x = (s16)(x - 0x20);
    if (variant == 75 || variant == 76)
        ysub = (u8)((u8)y - 0x0C);
    else
        ysub = (u8)((u8)y - 0x10);
    if ((u8)(ysub >> 3) >= 0x18)
        return;
    if (!sat_to_nt(x, (s16)(ysub & 0xF8), &col, &row))
        return;
    (void)row;
    w = 1;
    h = 1;
    tiles[0] = 0xE7;
    if (variant == 76)
    {
        w = 2;
        tiles[0] = tiles[1] = 0xE7;
    }
    else if (variant == 77)
    {
        h = 2;
        tiles[0] = tiles[1] = 0xE7;
    }
    else if (variant == 79)
    {
        /* Death punch is 8c80 -> 8d07, not a 3x3 of 0xE7. */
        w = 3;
        h = 3;
        tiles[0] = 0x82; tiles[1] = 0x1E; tiles[2] = 0x83;
        tiles[3] = 0xA4; tiles[4] = 0x1E; tiles[5] = 0xA3;
        tiles[6] = 0x83; tiles[7] = 0x1E; tiles[8] = 0x82;
    }
    else if (variant != 75)
    {
        w = 2;
        h = 2;
        tiles[0] = 0xE3;
        tiles[1] = 0xE4;
        tiles[2] = 0xE5;
        tiles[3] = 0xE6;
    }
    for (r = 0; r < h; r++)
    {
        /* 88ed INC C per row; C>=0x18 JP NC 8943 aborts the rest. */
        if ((u8)(((u8)(ysub & 0xF8) >> 3) + r) >= BOOT_ROWS)
            break;
        for (c = 0; c < w; c++)
            punch_cell((u8)(col + c),
                       (u8)(((u8)(ysub & 0xF8) >> 3) + r),
                       tiles[(u8)(r * w + c)]);
    }
}

void map_script_base_seg_down(s16 x, s16 y, u8 variant)
{
    if (s_e152)
        s_e152--;
    if (variant == 79)
        map_script_punch_79_hp(x, y, 0);
    else
        punch_bind(x, y, variant);
}

/* 8ced / 8cfa / 8d07: 88ed row-major desc (rows, then per-row width+tiles). */
static const u8 k_79_8ced[] = {
    3, 3, 0x8C, 0x8D, 0x8E, 3, 0x8F, 0x90, 0x91, 3, 0x92, 0x93, 0x94
};
static const u8 k_79_8cfa[] = {
    3, 3, 0x95, 0x96, 0x97, 3, 0x98, 0x99, 0x9A, 3, 0x9B, 0x9C, 0x9D
};
static const u8 k_79_8d07[] = {
    3, 3, 0x82, 0x1E, 0x83, 3, 0xA4, 0x1E, 0xA3, 3, 0x83, 0x1E, 0x82
};

static void punch_88ed(s16 x, s16 y, const u8 *d, s16 xadj, s16 yadj);

void map_script_punch_79_hp(s16 x, s16 y, u8 hp)
{
    const u8 *d = k_79_8d07;

    /* 8c80: CP 0x15 NC -> 8ced; NZ -> 8cfa; Z -> 8d07. Origin X-0x24 Y-0x14. */
    if (hp >= 0x15)
        d = k_79_8ced;
    else if (hp)
        d = k_79_8cfa;
    punch_88ed(x, y, d, -4, -4);
}

static void base_nt_cell(s16 x, s16 y, u8 dc, u8 dr, u8 tid)
{
    u8 col;
    u8 row;
    u8 ysub;

    /* 8c39 uses +06/+07 from 8948: H=SAT_X-0x20, L=SAT_Y pre +0x10.
     * Caller passes SAT after 8a7e Y+0x10 and before 8ac7 xo/yo. */
    ysub = (u8)((u8)y - 0x10);
    if ((u8)(ysub >> 3) >= 0x18)
        return;
    if (!sat_to_nt((s16)(x - 0x20), (s16)(ysub & 0xF8), &col, &row))
        return;
    nt_put((u8)(col + dc), (u8)((row + dr) & 31), tid);
}

int map_script_8948_cell(s16 sat_x, s16 sat_y_pre, u8 *col, u8 *row)
{
    u8 ysub = (u8)sat_y_pre;
    /* 8a92 SUB 0x20 is unsigned (Japan). R1 left-eye miss was 964C
     * 16-bit SAT X, not this subtract: west SAT 112, H=80, col 10. */
    u8 hx = (u8)((u8)sat_x - 0x20);

    /* 8948 L is SAT Y before 8a7d +0x10. C = Y/8; C>=0x18 no write. */
    if ((u8)(ysub >> 3) >= 0x18)
        return 0;
    return sat_to_nt((s16)hx, (s16)(ysub & 0xF8), col, row);
}

void map_script_base_8c15_at(u8 col, u8 row, u8 variant, u8 phase)
{
    u8 p = (u8)(phase & 3);
    u8 t0;
    u8 rows;
    u8 cols;
    u8 step;
    u8 r;
    u8 c;

    if (variant == 79)
        return;
    if (variant == 73)
    {
        t0 = (u8)(0xD3 + p * 4);
        rows = 2;
        cols = 2;
        step = 1;
    }
    else if (variant == 74)
    {
        t0 = (u8)(0xC3 + p * 4);
        rows = 2;
        cols = 2;
        step = 1;
    }
    else
    {
        /* 75-78: Japan 8c66 C=0xBF+phase, E=0 (same tile). B/D can be
         * 1x1 / 1x2 / 2x1 / 2x2, but charset 0xBF-0xC2 is one 8x8 lens
         * (phase 3 = 0xC2 red weak). Repeating that tile south made the
         * second stacked circle on every pod. One cell per pod. */
        t0 = (u8)(0xBF + p);
        step = 0;
        rows = 1;
        cols = 1;
    }
    for (r = 0; r < rows; r++)
        for (c = 0; c < cols; c++)
            nt_put((u8)(col + c), (u8)((row + r) & 31),
                   (u8)(t0 + (step ? (u8)(r * cols + c) : 0)));
}

void map_script_base_8c15(s16 x, s16 y, u8 variant, u8 phase)
{
    /* x,y are 8948 SAT, not live SAT after k_base xo/yo. Type 75
     * xo/yo 0xFC/0xFC: live-SAT paint lands one 8px cell left and up. */
    u8 p = (u8)(phase & 3);
    u8 t0;
    u8 rows;
    u8 cols;
    u8 step;
    u8 r;
    u8 c;

    if (variant == 79)
        return;
    if (variant == 73)
    {
        t0 = (u8)(0xD3 + p * 4);
        rows = 2;
        cols = 2;
        step = 1;
    }
    else if (variant == 74)
    {
        t0 = (u8)(0xC3 + p * 4);
        rows = 2;
        cols = 2;
        step = 1;
    }
    else
    {
        /* 75-78: one 0xBF+phase lens. Do not repeat south (double eye). */
        t0 = (u8)(0xBF + p);
        step = 0;
        rows = 1;
        cols = 1;
    }
    for (r = 0; r < rows; r++)
        for (c = 0; c < cols; c++)
            base_nt_cell(x, y, c, r, (u8)(t0 + (step ? (u8)(r * cols + c) : 0)));
}

void map_script_base_no_segments(void)
{
    s_e152 = 0;
}

/* 88ab word table: 84->88B1, 85->88B8, 86->88C2.
 * 88b1 / 88c2 also used by 8892 type 87 and 8824 type 81.
 * 88cb = type 88; 88d8 = type 82 / 89. */
static const u8 k_88ab_84[] = { 2, 2, 0x3B, 0x3C, 2, 0x3A, 0x3D };
static const u8 k_88ab_85[] = { 3, 2, 0x3B, 0x3C, 2, 0x3E, 0x3E, 2, 0x3A, 0x3D };
static const u8 k_88ab_86[] = { 2, 3, 0x3B, 0x3E, 0x3C, 3, 0x3A, 0x3E, 0x3D };
static const u8 k_88cb[] = {
    3, 3, 0x3B, 0x3E, 0x3C, 3, 0x3E, 0x3E, 0x3E, 3, 0x3A, 0x3E, 0x3D
};
static const u8 k_88d8[] = {
    4, 4, 0x3B, 0x3E, 0x3E, 0x3C, 4, 0x3E, 0x3E, 0x3E, 0x3E,
    4, 0x3E, 0x3E, 0x3E, 0x3E, 4, 0x3A, 0x3E, 0x3E, 0x3D
};

/* 88ed: desc at (x+xadj, y+yadj). Baseline 8854 is SAT_X-0x20 / Y-0x10.
 * Callers pass live SAT X/Y; nt_from_sat_x does the 8948 nametable bind.
 * Y SUB is unsigned (u8) like MSX; 70/71/81/84-89 keep unsigned SAT Y so
 * Y-0x10 on 0x00..0x0F underflows and CP 0x18 skips (no punch off-screen). */
static void punch_88ed(s16 x, s16 y, const u8 *d, s16 xadj, s16 yadj)
{
    u8 col0;
    u8 row0;
    u8 rows;
    u8 r;
    u8 w;
    u8 c;
    u8 ysub;
    s16 px = nt_from_sat_x((s16)(x + xadj));
    s16 py = (s16)(y + yadj);

    /* MSX 8854: L = SAT_Y-0x10 (u8), then 88ed CP 0x18 on Y/8. */
    ysub = (u8)((u8)py - 0x10);
    if ((u8)(ysub >> 3) >= 0x18)
        return;
    if (!sat_to_nt(px, (s16)(ysub & 0xF8), &col0, &row0))
        return;
    (void)row0;

    rows = *d++;
    for (r = 0; r < rows; r++)
    {
        /* 88ed: INC C each row; C>=0x18 JP NC 8943 (rest of desc unused). */
        if ((u8)(((u8)(ysub & 0xF8) >> 3) + r) >= BOOT_ROWS)
            break;
        w = *d++;
        for (c = 0; c < w; c++)
            punch_cell((u8)(col0 + c),
                       (u8)(((u8)(ysub & 0xF8) >> 3) + r),
                       *d++);
    }
}

void map_script_punch_88ab(s16 x, s16 y, u8 type)
{
    const u8 *d;

    if (type < 84 || type > 86)
        return;
    if (type == 84)
        d = k_88ab_84;
    else if (type == 85)
        d = k_88ab_85;
    else
        d = k_88ab_86;
    punch_88ed(x, y, d, 0, 0);
}

void map_script_punch_88b1(s16 x, s16 y)
{
    punch_88ed(x, y, k_88ab_84, 0, 0);
}

void map_script_punch_88c2(s16 x, s16 y)
{
    /* 8824: SUB 0x24 vs 8854 SUB 0x20. */
    punch_88ed(x, y, k_88ab_86, -4, 0);
}

void map_script_punch_88cb(s16 x, s16 y)
{
    punch_88ed(x, y, k_88cb, 0, 0);
}

void map_script_punch_88d8(s16 x, s16 y)
{
    /* 8874: SUB 0x28 / 0x18 vs 8854 SUB 0x20 / 0x10. */
    punch_88ed(x, y, k_88d8, -8, -8);
}

/* 8833 type 70/71: CALL bfc8 / 4a6a / alloc child 0xD1. No JP 88ed.
 * Punching a 3x2 of 0x28 (empty / blue sky) onto the yellow totem was
 * the playtest junk on top. Japan leaves the stream face. */

/* 87e2: only type 82. H=X-0x28 L=Y-0x10 via 8948; write 0x30+(IX+0x1c).
 * nt_from_sat_x is 8854's SAT-0x20; extra -8 = 8874/87e2 SAT-0x28.
 * MSX sat_color stays 0 -- digit is nametable-only. */
void map_script_stamp_82_digit(s16 x, s16 y, u8 fire_num)
{
    u8 col0;
    u8 row0;
    u8 ysub;
    s16 px = (s16)(nt_from_sat_x(x) - 8);

    /* 87e2: H=SAT_X-0x28 L=SAT_Y-0x10, then 8948. */
    ysub = (u8)((u8)y - 0x10);
    if ((u8)(ysub >> 3) >= 0x18)
        return;
    if (!sat_to_nt(px, (s16)(ysub & 0xF8), &col0, &row0))
        return;
    (void)row0;
    /* 87e2: LD (HL),A on 8948's E800 then SETWRT VRAM. punch_cell is
     * that order so commit_wrap DMA (Japan 9a79) includes the digit. */
    punch_cell(col0, (u8)((u8)(ysub & 0xF8) >> 3), (u8)(0x30 + fire_num));
}

static void bg_fill_plane(void)
{
    u8 i;

    /* 9ae4 scroll_sync: E714 := 0. 0x28 is the MSX empty-playfield tile in
     * RAM only -- never a visible boot wallpaper. Assemble 24 rows without
     * poking VRAM, then one flush, then prefetch the wrap row, then show. */
    memset(s_e800, 0x28, sizeof(s_e800));
    s_e714 = 0;
    s_ram_only = 1;
    s_dma_flip = 0;

    /* MSX build_tile_screen 0x946E: map_script_step x24.
     * Each step INC E702, fire-if-trigger, else/then scroll_precompute.
     * Cmd 9 (JP 9433 RET) skips that step's assemble. RAM only -- 0x28 is
     * never a visible boot wallpaper (display is off until the flush). */
    for (i = 0; i < BOOT_ROWS; i++)
    {
        s_skip_precompute = 0;
        s_ms.row++;
        fire_pending();
        if (!s_skip_precompute)
            scroll_precompute(s_ms.row);
    }
    s_scroll_px = 0;
    s_scroll_delta = 0;
    s_scroll_base = s_ms.row;
    s_ram_only = 0;
    s_row_tm = DMA;
    /* 40DA 4177 dumps E800 after 946e. Instant flush is the "jump". */
    if (!s_defer_nt_flush)
        flush_boot_playfield();
    fill_letterbox_b();
    /* hidden_wrap is SAT Y 0 (screen 16). At scroll_px=0 that is NT 0
     * (already flushed). +8 is NT 31 -- the row the first 1-8px reveal.
     * Peeking at scroll_px=0 would overwrite the live playfield top. */
    peek_next_row_at((u16)(s_ms.row + 1), (u16)(s_scroll_px + 8));
    s_row_tm = DMA_QUEUE;
    /* NT 0 at the top of the 192 before the first visible line. VSCROLL 0
     * would park NT 0-1 in the 16px bar and NT 24-25 in the 192. */
    bg_set_vscroll();
}

/* Set by script_boot when this round is the one the MSX swaps the late-stage
 * background in for -- see load_bg_late. */
static u8 s_bg_late_on;
static u8 s_prev_round;

#if MAP_HAS_CHARSET
/* load_bg_tiles 0x5C60. The MSX swaps part of the charset for a late-stage
 * background so a round that is a multiple of 8 does not look like round 1:
 * patterns and colours for 20 tiles at 23 and 67 tiles at 91, plus two
 * colour-only tiles at 158/159 (0x5C9A writes 552 colour bytes against 536
 * pattern bytes). Byte offsets 0x00B8 and 0x02D8 are /8 = tiles 23 and 91.
 * res/bg_late.bin is those 89 tiles already baked to MD 4bpp by
 * tools/extract_bg_late.py -- the MD has no colour table to swap.
 *
 * The gate is the round transition at 0x4110-0x4128, and only that one:
 *
 *   new = resolve_round_from_ptr, old = E701 before the write
 *   new & 7 != 0            -> neither loader runs      (0x411B)
 *   new & 7 == 0, old & 7   -> load_bg_tiles            (0x4122)
 *   new & 7 == 0, !(old&7)  -> load_charset_sprites     (0x412A load_bg_level)
 *
 * title_screen_init also calls load_bg_tiles at 0x4262 when 8 - E701 is a
 * multiple of 8, but starting the game from there runs straight into the
 * old&7 == 0 arm above and load_charset_sprites wipes it again. Measured on
 * openMSX C-BIOS_MSX1 with E701 forced to 8 at 0x425A: the breakpoint trace is
 * 425A -> 4262 -> 5C60 -> 5CA5, and VRAM 0x00B8 afterwards is byte-identical to
 * the plain charset. So a title start or continue at round 8 shows the normal
 * tiles, and only reaching it in play shows the late set. */
static void load_bg_late(void)
{
    if (!s_bg_late_on)
        return;
    VDP_loadTileData((const u32 *)bg_late, (u16)(s_bg_base + 23), 20, CPU);
    VDP_loadTileData((const u32 *)bg_late + 20 * 8, (u16)(s_bg_base + 91), 69,
                     CPU);
}
#endif

static void bg_load_tiles(void)
{
    PAL_setPalette(PAL3, s_tms_pal, CPU);
    s_bg_base = BG_TILE_BASE;

#if MAP_HAS_CHARSET
    /* charset_tiles.bin is screen2_to_md4 of 1bpp PGT + this CT bank. HUD
     * WINDOW ids are then recolored from charset_ct so bars 01/02 keep
     * per-row F then E (one CT byte for all 8 rows would flatten them). */
    VDP_loadTileData((const u32 *)charset_tiles, s_bg_base, 256, CPU);
    apply_hud_charset_ct();
    load_bg_late();
#else
    {
        static u32 dummy[256 * 8];
        u16 t;
        u8 r, px;
        for (t = 0; t < 256; t++)
        {
            u8 c = (u8)((t >> 4) & 0x0F);
            if (!c) c = 1;
            for (r = 0; r < 8; r++)
            {
                u32 row = 0;
                for (px = 0; px < 8; px++)
                    row = (row << 4) | (u32)(((t >> px) & 1) ? c : 0);
                dummy[t * 8 + r] = row;
            }
        }
        VDP_loadTileData(dummy, s_bg_base, 256, CPU);
    }
#endif
}

static void bg_init(void)
{
    if (mode_get() == MODE_ORIGINAL)
        VDP_setEnable(FALSE);
    VDP_setScrollingMode(HSCROLL_PLANE, VSCROLL_PLANE);
    VDP_setHorizontalScroll(BG_A, 0);
    VDP_setHorizontalScroll(BG_B, 0);
    VDP_setVerticalScroll(BG_A, 0);
    VDP_setVerticalScroll(BG_B, 0);
    VDP_clearPlane(BG_B, TRUE);
    memset(s_nt, 0, sizeof(s_nt));
    bg_load_tiles();
    bg_fill_plane();
    /* Charset load does not touch BG_A, but restamp the 16px bars so a
     * leftover tile 0 cannot sit under the ship at SAT Y 0xB8. */
    mode_draw_letterbox();
    if (mode_get() == MODE_ORIGINAL)
        VDP_setEnable(TRUE);
}

static void bg_update(void)
{
    /* Wrap row is already in VRAM (prefetch / this carry). Then move VSCROLL
     * and re-clip the 16px bars so wrap/peek cannot leak above the 192. */
    bg_set_vscroll();
}

void map_script_reset_scroll(void)
{
    VDP_setVerticalScroll(BG_A, 0);
    VDP_setVerticalScroll(BG_B, 0);
    VDP_setHorizontalScroll(BG_A, 0);
    VDP_setHorizontalScroll(BG_B, 0);
}

/* ---- inner stream / place_tile_group (cmd 1 / 5 / B) ---- */

static void place_tile_group(StreamSlot *st, u16 *pptr)
{
    const u8 *p;
    u8 extra;
    u8 ctrl;
    u8 n;
    u8 i;
    u16 ptr = *pptr;

    p = blob_at(ptr);
    if (!p || !blob_ok(ptr, 2))
        return;
    extra = p[0];
    ctrl = p[1];
    n = ctrl & 0x1F;
    ptr = (u16)(ptr + 2);
    {
        u8 nbase = 0;
    for (i = 0; i < n; i++)
    {
        const u8 *r = blob_at(ptr);
        u8 type;
        s16 y;
        s16 x;
        u16 dest;
        const u8 *tbl;
        if (!r || !blob_ok(ptr, 3))
            break;
        type = r[0];
        y = (s16)r[1];
        /* 0x964C: SAT X = ybase*8 + blob X - 0x20, 8-bit wrap. Collision
         * uses this SAT X (4560). Original stamps tiles at SAT-32 (EC). */
        x = sat_x_964c(st->ybase, r[2]);
        dest = 0;
        if (s_ms.idol_ptr)
        {
            tbl = blob_at((u16)(s_ms.idol_ptr + s_idol_cur));
            if (tbl && blob_ok((u16)(s_ms.idol_ptr + s_idol_cur), 2))
                dest = (u16)tbl[0] | ((u16)tbl[1] << 8);
        }
        /* 87b0: A=+0x03 (cursor stuffed at 9654), HL=E720, ADD HL,BC,
         * +0x1c/+0x1d = word. No round filter. Table 0xB787 +0 is 0x0000
         * and +3/+0x0A are 0xB7A5; 8a0b stores that in E722 as-is.
         * E722==0 -> 40DA 414d (no load). Do not invent 0xB7A5. */
        /* 0x9607 check_col_clear: CF -> skip place (still consume + idol bump).
         * Peek assemble must still consume the descriptor (count/tiles)
         * but must not spawn or scan occupancy -- restore would leave
         * the entities, and 9B22 during peek is not a real 97e3 place. */
        if (!s_assemble_peek && entity_check_col_clear())
        {
            if (entity_place_ground(type, x, y, dest))
            {
                /* bit7: INC E151 only on successful place (0x9637). */
                if (ctrl & 0x80)
                    nbase++;
            }
        }
        if (ctrl & 0x40)
        {
            s_idol_cur++;
            if (ctrl & 0x20)
                s_idol_cur++;
        }
        ptr = (u16)(ptr + 3);
    }
    if ((ctrl & 0x80) && nbase)
    {
        s_e152 = nbase;
        entity_base_open(nbase);
        /* Scripts never write E156=0 (cmd B values are 0x06..0x14). Leftover
         * 0 after a previous fight: MSX 8f78 DECs 0->255 (255-row wait).
         * Arm now so a mid-stream second group is not idle for 255 rows.
         * Approach DEC still wraps if E150.0 is set without this path. */
        if (!s_e156)
            entity_base_arm();
    }
    }
    st->count = extra;
    st->ptr = ptr;
    *pptr = ptr;
}

/* SUB_ram_93e7: 95ef from ctrl-first ptr, ybase 8; then E150=2, E153=5.
 * 93e4 loads DE=0xBCB2 and falls in. 9251 calls with DE=0xBBF3. */
static void place_ctrl_at(u16 ptr)
{
    StreamSlot st;
    const u8 *p;

    p = blob_at(ptr);
    if (!p || !blob_ok(ptr, 1))
        return;
    /* 95ef starts at ctrl (no extra byte). */
    st.used = 1;
    st.ybase = 8;
    st.count = 0;
    st.delay = 0;
    st.ptr = ptr;
    {
        u8 ctrl = p[0];
        u8 n = (u8)(ctrl & 0x1F);
        u8 i;
        u8 nbase = 0;
        u16 q = (u16)(ptr + 1);

        for (i = 0; i < n; i++)
        {
            const u8 *r = blob_at(q);
            u8 type;
            s16 y;
            s16 x;
            u16 dest;
            const u8 *tbl;
            if (!r || !blob_ok(q, 3))
                break;
            type = r[0];
            y = (s16)r[1];
            x = sat_x_964c(st.ybase, r[2]); /* SAT X, same as 0x964C */
            dest = 0;
            if (s_ms.idol_ptr)
            {
                tbl = blob_at((u16)(s_ms.idol_ptr + s_idol_cur));
                if (tbl && blob_ok((u16)(s_ms.idol_ptr + s_idol_cur), 2))
                    dest = (u16)tbl[0] | ((u16)tbl[1] << 8);
            }
            /* 87b0: table[cursor] as-is. No R7 dest rewrite. */
            if (!s_assemble_peek && entity_check_col_clear())
            {
                if (entity_place_ground(type, x, y, dest))
                {
                    if (ctrl & 0x80)
                        nbase++;
                }
            }
            if (ctrl & 0x40)
            {
                s_idol_cur++;
                if (ctrl & 0x20)
                    s_idol_cur++;
            }
            q = (u16)(q + 3);
        }
        if ((ctrl & 0x80) && nbase)
        {
            s_e152 = nbase;
            entity_base_open(nbase);
            /* Same leftover-0 arm as place_tile_group. 93e7 then E150=2. */
            if (!s_e156)
                entity_base_arm();
        }
    }
    /* 93e7: IY+0 := 0x80 (slot unused; this StreamSlot is local). */
    entity_base_set(2);          /* IX+0x50 */
    s_e153 = 5;                  /* IX+0x53 */
}

static void base_mode_11(void)
{
    place_ctrl_at(0xBCB2);
}

/* Peek stream head like MSX 0x95DD / delay-expiry 0x9A13:
 * first byte 0 -> place_tile_group (returns extra as count);
 * else count = first byte. ptr always lands past the consumed head. */
static void stream_slot_peek(StreamSlot *st, u16 src)
{
    const u8 *p = blob_at(src);

    if (!p || !blob_ok(src, 1))
    {
        st->used = 0;
        st->count = 0;
        return;
    }
    if (p[0] == 0)
    {
        u16 ptr = (u16)(src + 1);
        place_tile_group(st, &ptr);
        st->ptr = ptr;
        st->used = (u8)(st->count != 0);
    }
    else
    {
        st->count = p[0];
        st->ptr = (u16)(src + 1);
        st->used = (u8)(st->count != 0);
    }
}

static void init_stream_slot(u8 slot, u8 ybase, u16 src, u8 delay)
{
    StreamSlot *st;

    slot &= 0x07;
    st = &s_stream[slot];
    st->used = 1;
    st->ybase = ybase;
    st->count = 0;
    st->delay = delay;
    st->ptr = src;
    /* Delayed: keep ptr at stream start; peek on expiry (0x95D7 bit6). */
    if (delay)
        return;
    stream_slot_peek(st, src);
}

/* Bytes consumed by a cmd-5 / nested load_stream_slots body at addr. */
static u16 stream_slots_body_len(u16 addr)
{
    const u8 *p = blob_at(addr);
    u8 n;
    u16 q;
    u8 k;

    if (!p || !blob_ok(addr, 1))
        return 0;
    n = p[0];
    q = (u16)(addr + 1);
    for (k = 0; k < n; k++)
    {
        const u8 *r = blob_at(q);
        if (!r || !blob_ok(q, 1))
            break;
        q = (u16)(q + ((r[0] & 0x08) ? 5 : 4));
    }
    return (u16)(q - addr);
}

/* 0x95A8 load_stream_slots: N records, ybase += yadd (nested passes parent). */
static void load_stream_slots_at(u16 addr, u8 yadd)
{
    const u8 *p = blob_at(addr);
    u8 n;
    u16 q;
    u8 k;

    if (!p || !blob_ok(addr, 1))
        return;
    n = p[0];
    q = (u16)(addr + 1);
    for (k = 0; k < n; k++)
    {
        const u8 *r = blob_at(q);
        u8 b0;
        u8 slot;
        u8 ybase;
        u16 ptr;

        if (!r || !blob_ok(q, 1))
            break;
        b0 = r[0];
        slot = (u8)(b0 & 0x07);
        if (b0 & 0x08)
        {
            if (!blob_ok(q, 5))
                break;
            ybase = (u8)(r[1] + yadd);
            ptr = (u16)r[3] | ((u16)r[4] << 8);
            init_stream_slot(slot, ybase, ptr, r[2]);
            q = (u16)(q + 5);
        }
        else
        {
            if (!blob_ok(q, 4))
                break;
            ybase = (u8)(r[1] + yadd);
            ptr = (u16)r[2] | ((u16)r[3] << 8);
            init_stream_slot(slot, ybase, ptr, 0);
            q = (u16)(q + 4);
        }
    }
}

/* 0x99F7 per-frame stream stamp into EA40 work row. */
static void stream_stamp_buf(void)
{
    u8 i;

    for (i = 0; i < STREAM_SLOTS; i++)
    {
        StreamSlot *s = &s_stream[i];
        const u8 *p;
        u8 delta;
        u8 len;
        u8 j;
        u16 sx;

        if (!s->used)
            continue;
        if (s->delay)
        {
            s->delay--;
            if (s->delay)
                continue;
            /* Expiry: peek head then fall through and stamp this frame. */
            stream_slot_peek(s, s->ptr);
            if (!s->used || !s->count)
                continue;
        }
        if (!s->count)
            continue;
        p = blob_at(s->ptr);
        if (!p || !blob_ok(s->ptr, 2))
        {
            s->used = 0;
            continue;
        }
        delta = p[0];
        len = p[1];
        /* len == 0: empty run (still consumes one count). */
        if (len == 0)
        {
            s->ptr = (u16)(s->ptr + 2);
        }
        else if (len >= 0xFE)
        {
            /* 0x9A3E: nested load_stream_slots; C = parent ybase. */
            u16 body = (u16)(s->ptr + 2);
            u16 blen = stream_slots_body_len(body);
            load_stream_slots_at(body, s->ybase);
            s->ptr = (u16)(body + blen);
        }
        else
        {
            if (!blob_ok(s->ptr, (u16)(2 + len)))
            {
                s->used = 0;
                continue;
            }
            /* dest = 0xEA40 + ybase + delta  (32-wide work buffer) */
            sx = (u16)s->ybase + delta;
            for (j = 0; j < len; j++)
                row_put((u16)(sx + j), p[2 + j]);
            s->ptr = (u16)(s->ptr + 2 + len);
        }
        s->count--;
        if (!s->count)
            s->used = 0;
    }
}

/* ---- command handlers ---- */

static void cmd_place_tiles(u8 cmd, const u8 *ops);

static void cmd_spawn_ctrl(u8 cmd, const u8 *ops)
{
    /* 0x97A8: E12D := op. BIT 2 -> JR NZ 0x97B3 (same body as cmd 1). */
    s_ms.spawn_ctrl = ops[0];
    entity_on_spawn_ctrl(ops[0]);
    if (ops[0] & 0x04)
        cmd_place_tiles(cmd, ops + 1);
}

static void cmd_place_tiles(u8 cmd, const u8 *ops)
{
    u8 n = ops[0];
    u8 k;

    (void)cmd;
    /* Each 3-byte record -> type 69 (0x45) + emit, count, interval (0x97CA).
     * 0x97BE check_col_clear: skip place on CF; always consume record.
     * 7a67 then 71c5: not a nametable stamp. */
    for (k = 0; k < n; k++)
    {
        const u8 *r = ops + 1 + k * 3;
        if (entity_check_col_clear())
            entity_place_ground(0x45, (s16)r[1], (s16)r[0], r[2]);
    }
}

static void cmd_col_groups(u8 cmd, const u8 *ops)
{
    u8 n = ops[0];
    u8 k;

    (void)cmd;
    for (k = 0; k < n; k++)
    {
        const u8 *r = ops + 1 + k * 5;
        bind_col_slot(r[0], r[1], r[2], read_le16(r + 3), 0);
    }
}

static void cmd_tile_copy(u8 cmd, const u8 *ops)
{
    u8 n = ops[0];
    u8 k;

    (void)cmd;
    /* N x (src,dst): copy 8-byte slot src -> dst, mark src 0x80 (0x9537). */
    for (k = 0; k < n; k++)
    {
        u8 src = ops[1 + k * 2] & 0x0F;
        u8 dst = ops[2 + k * 2] & 0x0F;

        s_col[dst] = s_col[src];
        s_col[src].pos = 0x80;
    }
}

static void cmd_col_groups_add(u8 cmd, const u8 *ops)
{
    u8 n = ops[0];
    u8 k;

    (void)cmd;
    for (k = 0; k < n; k++)
    {
        const u8 *r = ops + 1 + k * 5;
        bind_col_slot(r[0], r[1], r[2], read_le16(r + 3), 1);
    }
}

static void cmd_stream_slots(u8 cmd, const u8 *ops)
{
    /* 0x95A0: C=0 then load_stream_slots. ops[0]=N lives in the blob image
     * via PC walk; rebuild a synthetic addr by scanning is awkward, so keep
     * the inline walk (yadd=0) matching load_stream_slots_at. */
    u8 n = ops[0];
    u16 q = 1;
    u8 k;

    (void)cmd;
    for (k = 0; k < n; k++)
    {
        u8 b0 = ops[q];
        u8 slot = (u8)(b0 & 0x07);
        u8 ybase;
        u16 ptr;

        if (b0 & 0x08)
        {
            ybase = ops[q + 1];
            ptr = (u16)ops[q + 3] | ((u16)ops[q + 4] << 8);
            init_stream_slot(slot, ybase, ptr, ops[q + 2]);
            q += 5;
        }
        else
        {
            ybase = ops[q + 1];
            ptr = (u16)ops[q + 2] | ((u16)ops[q + 3] << 8);
            q += 4;
            init_stream_slot(slot, ybase, ptr, 0);
        }
    }
}

static void cmd_set_e71c(u8 cmd, const u8 *ops)
{
    (void)cmd;
    s_ms.e71c = ops[0];
}

static void cmd_disable_grps(u8 cmd, const u8 *ops)
{
    u8 n = ops[0];
    u8 k;

    (void)cmd;
    for (k = 0; k < n; k++)
    {
        u8 slot = ops[1 + k] & 0x0F;
        s_col[slot].pos = 0x80;
    }
}

static void cmd_idol_banner(u8 cmd, const u8 *ops)
{
    u8 round = s_ms.round;

    (void)cmd;
    s_ms.idol_ptr = read_le16(ops);
    s_idol_cur = 0;                     /* IX+0x1D := 0 */
    /* E15E := 0x96; SET 4,E102; print " ROUND n " at 0x3948 (row 10 col 8).
     * E180 split (IY+0x0A=8, IY+0x22=0x11) keeps that nametable strip from
     * the 24-col scroll DMA until display_timer_countdown 0x41BA zeros E180.
     * MD stamps on BG_A (does not VSCROLL) for the same 150 frames. */
    s_ms.banner_timer = 0x96;
    s_ms.banner[0] = ' ';
    s_ms.banner[1] = 'R';
    s_ms.banner[2] = 'O';
    s_ms.banner[3] = 'U';
    s_ms.banner[4] = 'N';
    s_ms.banner[5] = 'D';
    s_ms.banner[6] = ' ';
    s_ms.banner[7] = (char)('0' + (round % 10));
    s_ms.banner[8] = ' ';
    s_ms.banner[9] = 0;
    player_e102_set(0x10);
    if (mode_get() == MODE_ORIGINAL)
        hud_draw_str(BG_A, 8, mode_text_row(10), s_ms.banner);
    /* MSX 0x9044 plays ev25 but stop_all kills the ev7->ev1 chain; keep BGM. */
    s_banner_bgm_arm = 1;
}

static void load_trigger_from_pc(void);

static void cmd_script_jump(u8 cmd, const u8 *ops)
{
    u16 dest = read_le16(ops);

    (void)cmd;
    /* 96de JP 9433 RET: this map_script_step does not 97d5/precompute. */
    s_skip_precompute = 1;
    /* dest 0xA6F4 is an in-stream jump (ending self-loop at 0xA74C row
     * 650). 9433 resolve -> 0, 4C68, JP 941b. LAB_92af (SET 5+3) / R8
     * 0xFFFF / warp dest 0xA6F4 arm credits separately — cmd 9 never
     * SET 3 and never alc_reset. */
    /* dest is an MSX address. Halt only if it is outside the loaded blob. */
    if (!blob_ok(dest, 3))
    {
        if (s_ms.round == 8 && !s_cred_on)
            arm_ending_stream();
        else
            s_ms.running = FALSE;
        return;
    }
    s_ms.round = resolve_round_from_ptr(dest);
    if (s_ms.round >= 1 && s_ms.round <= 8)
        s_continue_round = s_ms.round;
    s_ms.pc = dest;
    /* 96de JP 9433 / 941b: reload trigger/row/PC only. MSX never writes
     * E12E/E12F/E131/E132 here — firing + cmd 12 survive the jump. */
    load_trigger_from_pc();
    /* LAB_941b: E702 = trigger-1. Do not reset E714 / E800 -- MSX keeps
     * the circular nametable. Cmd 9 RETs without 97d5/precompute. Keep
     * VSCROLL continuous: rebase so (row-base)*8 matches current pixels. */
    s_ms.row = (u16)(s_ms.trigger - 1);
    s_scroll_base = (u16)(s_ms.row - (s_scroll_px >> 3));
}

/* Rebuild one charset tile from occupancy + 8 SCREEN2 CT bytes (FG<<4|BG). */
static void recolor_charset_tile(u8 tid, const u8 *ct8)
{
    const u32 *src;
    u32 dst[8];
    u8 r, px;
    u8 ct, fg, bg;

    src = (const u32 *)charset_tiles + (u16)tid * 8;
    for (r = 0; r < 8; r++)
    {
        u32 row;
        u32 out;

        ct = ct8[r];
        fg = (u8)(ct >> 4);
        bg = (u8)(ct & 0x0F);
        row = src[r];
        out = 0;
        for (px = 0; px < 8; px++)
        {
            u8 n = (u8)((row >> ((7 - px) * 4)) & 0x0F);
            out = (out << 4) | (u32)(n ? fg : bg);
        }
        dst[r] = out;
    }
    VDP_loadTileData(dst, (u16)(s_bg_base + tid), 1, CPU);
}

static void recolor_charset_tile_fill(u8 tid, u8 ct)
{
    u8 ct8[8];
    u8 r;

    for (r = 0; r < 8; r++)
        ct8[r] = ct;
    recolor_charset_tile(tid, ct8);
}

#if MAP_HAS_CHARSET
static void apply_hud_charset_ct(void)
{
    u8 tid;

    /* gfx_charset_colors 0x64D3, decompress_block 0x5CCF, one 2048-byte bank.
     * load_charset_sprites 0x5CA5 writes that stream to VRAM 0x2000/0x2800/0x3000
     * (three identical banks). WINDOW HUD and the 0x96c2 " ROUND n " banner
     * (SETWRT 0x3948, BG_A col 8) share these ids. Tile 0x20 CT is 70
     * (cyan on 0). SCREEN2 bg 0 is transparent to R7 -- keep that.
     * Do not map bg 0 -> PAL3[1] here: that painted opaque black blocks
     * in the banner spaces (PR #40 regression). HUD stripe punch-through
     * is BG_B cols 24-31 (hud_fill_bar_backing), not a global CT change. */
    recolor_charset_tile(0x01, charset_ct + 0x01 * 8);
    recolor_charset_tile(0x02, charset_ct + 0x02 * 8);
    recolor_charset_tile(0x03, charset_ct + 0x03 * 8);
    recolor_charset_tile(0x20, charset_ct + 0x20 * 8);
    for (tid = 0x30; tid <= 0x39; tid++)
        recolor_charset_tile(tid, charset_ct + (u16)tid * 8);
    for (tid = 0x41; tid <= 0x5A; tid++)
        recolor_charset_tile(tid, charset_ct + (u16)tid * 8);
}
#endif

static void cmd_vram_glyph(u8 cmd, const u8 *ops)
{
    /* 0x96E5: operand -> E723 fill. Solid 5-col CT @0x21D0 (tiles 0x3A-0x3E),
     * 4-col glyph 00 00 70 50 | fill_nibble @0x2538 (tiles 0xA7-0xAA).
     * Do not touch HUD 01-03 / space / digits / A-Z. */
    u8 fill = ops[0];
    u8 i;
    static const u8 k_glyph[4] = { 0x00, 0x00, 0x70, 0x50 };

    (void)cmd;
#if MAP_HAS_CHARSET
    for (i = 0; i < 5; i++)
        recolor_charset_tile_fill((u8)(0x3A + i), fill);
    for (i = 0; i < 4; i++)
        recolor_charset_tile_fill((u8)(0xA7 + i),
                                  (u8)(k_glyph[i] | (fill & 0x0F)));
#else
    (void)fill;
    (void)i;
#endif
}

static void cmd_wide_slot(u8 cmd, const u8 *ops)
{
    /* 0x9742: 4 bytes -> E155..E158; init_stream_slot consumes last 3 (E=0). */
    u8 ybase = ops[4];
    u16 ptr = read_le16(ops + 5);

    (void)cmd;
    s_e155 = ops[0];
    s_e156 = ops[1];
    s_e157 = ops[2];
    s_e158 = ops[3];
    s_e154 = 0;                 /* 0x974b: clear E154; E155 is MM BCD */
    s_e159 = 0;
    s_e15a = 0;
    s_time_on = 0;
    {
        u8 idx = (u8)(s_e157 & 0x1F);
        s_e153 = (idx < 17) ? k_e153[idx] : 0;
    }
    init_stream_slot(0, ybase, ptr, 0);
}

static void cmd_spawn_pace(u8 cmd, const u8 *ops)
{
    u8 v = ops[0];

    (void)cmd;
    s_ms.last_nudge = (s8)((v & 0x80) ? (s16)v - 256 : v);
    entity_on_spawn_pace(s_ms.last_nudge);
}

static const MapCmdFn s_jump[13] = {
    cmd_spawn_ctrl,
    cmd_place_tiles,
    cmd_col_groups,
    cmd_tile_copy,
    cmd_col_groups_add,
    cmd_stream_slots,
    cmd_set_e71c,
    cmd_disable_grps,
    cmd_idol_banner,
    cmd_script_jump,
    cmd_vram_glyph,
    cmd_wide_slot,
    cmd_spawn_pace
};

static void load_trigger_from_pc(void)
{
    const u8 *p;

    if (!blob_ok(s_ms.pc, 3))
    {
        if (s_ms.round == 8 && !s_cred_on)
            arm_ending_stream();
        else
            s_ms.running = FALSE;
        return;
    }
    p = blob_at(s_ms.pc);
    s_ms.trigger = read_le16(p);
    if (s_ms.trigger >= 0x8000)
    {
        /* R8 has no cmd 9: next word is 0xFFFF, then ending_setup. */
        if (s_ms.round == 8 && !s_cred_on)
            arm_ending_stream();
        else
            s_ms.running = FALSE;
    }
}

static void fire_pending(void)
{
    u8 fired = 0;

    /* 94C3 command path. Never inherit wrap-peek; cmd 1 / cmd B place. */
    s_assemble_peek = 0;

    while (s_ms.running && fired < MAX_FIRE)
    {
        u8 cmd;
        u8 nib;
        const u8 *ops;
        const u8 *p;
        u16 oplen;

        if (s_ms.row != s_ms.trigger)
            return;
        if (!blob_ok(s_ms.pc, 3))
        {
            s_ms.running = FALSE;
            return;
        }
        p = blob_at(s_ms.pc);
        cmd = p[2];
        nib = cmd & 0x0F;
        s_ms.param = (u8)(cmd >> 4);
        ops = p + 3;
        if (!blob_ok((u16)(s_ms.pc + 3), 1))
        {
            s_ms.running = FALSE;
            return;
        }
        oplen = op_len(cmd, ops);
        if (!blob_ok(s_ms.pc, (u16)(3 + oplen)))
        {
            s_ms.running = FALSE;
            return;
        }

        if (nib < 13)
        {
            s_ms.last_cmd = s_cmd_name[nib];
            s_jump[nib](cmd, ops);
        }
        else
        {
            s_ms.last_cmd = "?";
        }

        fired++;

        /* 941b RET: leave PC/trigger as jump wrote them; no 97d5. */
        if (nib == MAPCMD_SCRIPT_JUMP)
            return;

        s_ms.pc += (u16)(3 + oplen);
        load_trigger_from_pc();
    }
}

static void cred_clear_page(void)
{
    const ModeAssets *a = mode_assets();
    u16 cols = a->screen_width / 8;
    u16 y0 = mode_text_row(CRED_ROW0);
    u8 y;

    /* Do not wipe the right bar or letterbox. */
    if (mode_get() == MODE_ORIGINAL)
        cols = MODE_BAR_COL;
    for (y = 0; y < 16; y++)
    {
        if (mode_get() == MODE_ORIGINAL)
            hud_fill_tile(BG_A, 0, (u16)(y0 + y), 0, cols);
        else
            VDP_clearText(0, (u16)(y0 + y), cols);
    }
}

static void cred_enter(void)
{
    s_cred_on = 1;
    s_cred_exit = 0;
    s_cred_idx = 0;
    s_cred_wait = CRED_WAIT_PAGE;
    s_cred_settle = 0;
    s_cred_age = 0;
    s_cred_dirty = 1;
    s_ms.credits = 1;
}

static void cred_advance(void)
{
    u16 i = s_cred_idx;

    while (i < sizeof(k_cred_ctrl) && k_cred_ctrl[i] != 0xFF)
        i++;
    i++;
    if (i >= sizeof(k_cred_ctrl) || k_cred_ctrl[i] == 0xFF)
    {
        s_cred_idx = 0;
        s_cred_wait = CRED_WAIT_LAST;
    }
    else
    {
        s_cred_idx = (u8)i;
        s_cred_wait = CRED_WAIT_PAGE;
    }
    s_cred_settle = 0;
    s_cred_dirty = 1;
}

static void cred_tick(void)
{
    u16 joy = JOY_readJoypad(JOY_1);

    if (!s_cred_on)
        return;

    if (s_cred_age < 0xFFFF)
        s_cred_age++;

    /* START maps to MSX ESC after the 80-frame settle window. */
    if ((joy & BUTTON_START) && s_cred_age > CRED_SETTLE)
        s_cred_exit = 1;

    if (s_cred_settle)
    {
        s_cred_settle--;
        if (!s_cred_settle)
            cred_advance();
        return;
    }

    /* wait_fire_or_timeout: fire restarts the page timer (holds the page). */
    if (joy & (BUTTON_A | BUTTON_C))
        return;

    if (s_cred_wait)
        s_cred_wait--;
    if (!s_cred_wait)
        s_cred_settle = CRED_SETTLE;
}

/* TMS nametable row r is always screen row r (no VSCROLL). MD maps that
 * onto the currently visible 24-row window: the 8px tile at SAT Y 0,
 * then +r. Same Y as sat_to_nt (tile_wrap + Y/8). Do not use wrap(raw)
 * — at leftover E711 frac 1-7 that is the peek sliver, one row north
 * of 97e3's tile. */
static u8 vis_nt_row(u8 tms_row)
{
    return (u8)((tile_wrap_nt_at(s_scroll_px) + tms_row) & 31);
}

/* scroll_sync 0x9AE4: wait E700.0 clear, RES bit 3, E714=0, copy 24x24
 * from nametable 0x3800 (stride 32, 24 playfield cols) into E800.
 * Does not rewrite VRAM -- TMS NT 0-23 IS the screen. */
static void scroll_sync(void)
{
    u8 r;
    u8 c;

    s_e700 &= (u8)~8;
    s_e714 = 0;
    for (r = 0; r < BOOT_ROWS; r++)
    {
        u8 nr = vis_nt_row(r);

        for (c = 0; c < PF_COLS; c++)
            s_e800[r][c] = s_nt[nr][c];
    }
}

/* scroll_vram_write 0x9A79 with E714==0: dump E800[0..23] to NT 0-23 and
 * put NT 0 at the top of the 192. TMS writes VRAM 0x3800 with no VSCROLL. */
static void e800_flush_linear(void)
{
    u8 r;

    s_row_tm = DMA;
    for (r = 0; r < BOOT_ROWS; r++)
        dma_nt_row(r, s_e800[r], DMA);
    fill_letterbox_b();
    s_row_tm = DMA_QUEUE;
    s_scroll_px = 0;
    s_scroll_base = s_ms.row;
    s_end_snapped = 1;
    s_e700 &= (u8)~1;
    /* Plane is linear NT 0-23. Park VSCROLL at -y_off now -- the register
     * still held the live wrap offset until this point. */
    bg_set_vscroll();
}

/* copy_tile_column 0x986E: EB00 col C -> E800 col C, 24 rows stride 24. */
static void copy_tile_column(u8 col)
{
    u8 r;

    if (col >= PF_COLS)
        return;
    for (r = 0; r < BOOT_ROWS; r++)
        s_e800[r][col] = s_eb00[r][col];
}

/* 982c overlapping LDIR dest=src+1 and LDDR dest=src-1, BC=n after DEC. */
static void e800_squeeze(u8 n)
{
    u8 r;
    u8 i;

    if (!n)
        return;
    for (r = 0; r < BOOT_ROWS; r++)
    {
        for (i = 0; i < n; i++)
            s_e800[r][(u8)(i + 1)] = s_e800[r][i];
        for (i = 0; i < n; i++)
            s_e800[r][(u8)(22 - i)] = s_e800[r][(u8)(23 - i)];
    }
}

/* LAB_980e: E700 bit2 path. Bit3 -> scroll_sync + E70D=0x0C. E70D==0 RET Z
 * (no bit1, so 8f5e / Y+=8 stop). Else DEC, squeeze unless old==1, stamp
 * EB00 columns C and (~C+0x18), SET bits 0+1. */
static void lab_980e(void)
{
    u8 old;
    u8 c;
    u8 mirrored;

    if (s_e700 & 8)
    {
        scroll_sync();
        s_e70d = 0x0C;
    }
    if (!s_e70d)
        return;
    old = s_e70d;
    s_e70d--;
    if (old != 1)
        e800_squeeze(s_e70d);
    c = s_e70d;
    copy_tile_column(c);
    mirrored = (u8)((u8)~c + 0x18);
    copy_tile_column(mirrored);
    s_e700 |= 3;
    s_row_carry = 1;
    e800_flush_linear();
}

static void tms_nt_put(u8 col, u8 tms_row, u8 tid)
{
    nt_put(col, vis_nt_row(tms_row), tid);
}

/* ending_setup 0x91FD. TMS LDIRVM 0x3C00 is RAM-mapped. BBB4 assemble is
 * ram-only so the live nametable is not flashed. Stream/PC stay on BBB4. */
static void ending_setup_91fd(void)
{
    u16 i;
    u8 saved_ram;

    sound_stop_all();
    memcpy(s_3c00, s_e800, sizeof(s_e800));

    s_ms.round = resolve_round_from_ptr(0xBBB4);
    s_ms.pc = 0xBBB4;
    s_ms.running = TRUE;
    s_ms.last_cmd = "91fd";
    load_trigger_from_pc();
    s_ms.row = (u16)(s_ms.trigger - 1);

    saved_ram = s_ram_only;
    s_ram_only = 1;
    for (i = 0; i < BOOT_ROWS; i++)
    {
        s_skip_precompute = 0;
        s_ms.row++;
        fire_pending();
        if (!s_skip_precompute)
            scroll_precompute(s_ms.row);
    }
    s_ram_only = saved_ram;

    memcpy(s_eb00, s_e800, sizeof(s_e800));
    memcpy(s_e800, s_3c00, sizeof(s_e800));
    /* 24 dummy E702 INCs must not move MD VSCROLL; TMS has none.
     * Rebase keeps (row-base)*8 + (E711>>5) at the pre-dummy pixel.
     * Dummy assemble is ram-only: the 32-row MD plane is not rewritten.
     * NT 24-31 stay the wrap/prefetch buffer; do not fill_letterbox_b
     * here (that would wipe the 1-7px peek row). BG_A letterbox still
     * clips wrap pixels that VSCROLL parks in the 16px bars. */
    s_scroll_base = (u16)(s_ms.row - (s_scroll_px >> 3));

    s_e157 = 0xD1;
    s_e156 = 0x0C;
    entity_base_set(1);
    s_e700 = 0x0C;
    s_e710 = 0x20;
    s_e70d = 0;
    s_end_snapped = 0;
    s_end_phase = 0;
    sound_play_event(SND_EV_BOSS);      /* 0x924B ev12 */
    player_e102_res(0x04);              /* 0x92CA RES 2,E102 */
}

static void lab_9251_start(void)
{
    /* 9254 B=2 gameplay_frame_loop, then 9x (92f3 + 17 tiles + wait 6). */
    s_end_phase = 1;
    s_end_wait = 2;
    s_end_rows = 9;
    s_end_y = 0x4C;
    s_end_tms_row = 9;                  /* 0x3924 = row 9 col 4 */
}

static void lab_9251_tick(void)
{
    const u8 *src;
    u8 i;

    if (!s_end_phase)
        return;
    if (s_end_wait)
    {
        s_end_wait--;
        return;
    }

    if (s_end_rows)
    {
        /* 92f3: D=7, 8bca with HL=0x80<<8|C, BC=0x7F07. */
        entity_scatter_8bca(0x80, (s16)s_end_y, 0x7F, 0x07, 7);
        src = blob_at((u16)(0xBBFD + (u16)(9 - s_end_rows) * 17));
        if (src && blob_ok((u16)(0xBBFD + (u16)(9 - s_end_rows) * 17), 17))
        {
            for (i = 0; i < 17; i++)
                tms_nt_put((u8)(4 + i), s_end_tms_row, src[i]);
        }
        s_end_tms_row--;
        s_end_y = (u8)(s_end_y - 8);
        s_end_rows--;
        s_end_wait = 6;                 /* 9285 B=6, including after last */
        return;
    }

    if (s_end_phase == 1)
    {
        scroll_sync();
        place_ctrl_at(0xBBF3);          /* 93e7; ctrl 0x83 -> 3x type 79 */
        s_e157 = 0xB2;
        s_end_wait = 10;                /* 92A4 B=0x0A */
        s_end_phase = 2;
        return;
    }

    player_e102_res(0x04);              /* clear_credits_busy */
    entity_base_arm();                  /* JP 8fca */
    s_end_phase = 0;
}

static void arm_ending_stream(void)
{
    /* LAB_92af: HL=0xA6F4 -> E722, SET 5+3 E102, wait 0x3C, E700=0,
     * E712=0x80, clear_credits_busy. 91FD / 9251 / 980e are separate
     * award paths (E157&0x1F == 0x10 / 0x11 / >= 0x12). */
    s_e700 = 0;
    s_e70d = 0;
    s_end_snapped = 0;
    s_end_phase = 0;
    s_ms.round = 0;
    s_ms.pc = MAP_ENDING_STREAM;
    s_ms.row = 0;
    s_ms.running = TRUE;
    s_ms.last_cmd = "ending";
    entity_alc_reset();
    load_trigger_from_pc();
    s_e712 = SCROLL_SPEED_CRED;
    if (!s_cred_on)
    {
        cred_enter();
        /* 0x924B ev12. Orb warp uses 0x40EA ev11 then 0x4133 ev10 instead. */
        if (!s_boot_quiet)
            sound_play_event(SND_EV_BOSS);
        player_e102_res(0x04);          /* 0x924E -> clear_credits_busy RES 2 */
    }
}

void map_script_start_ending(void)
{
    u8 i;

    memset(&s_ms, 0, sizeof(s_ms));
    for (i = 0; i < COL_SLOTS; i++)
        s_col[i].pos = 0x80;
    for (i = 0; i < STREAM_SLOTS; i++)
        s_stream[i].used = 0;
    s_idol_cur = 0;
    s_assemble_peek = 0;
    s_cred_on = s_cred_exit = 0;
    entity_clear_enemies();
    scroll_speed_reset(SCROLL_SPEED_CRED);
    arm_ending_stream();
    /* LAB_941b: E702 = trigger-1, then build_tile_screen x24. */
    s_ms.row = (u16)(s_ms.trigger - 1);
    bg_init();
}

static void scroll_speed_reset(u8 target)
{
    s_e710 = 0;
    s_e711 = 0;
    s_e712 = target;
    s_e713 = 0;
    s_e152 = s_e153 = s_e154 = s_e155 = s_e156 = s_e157 = s_e158 = s_e159 = 0;
    s_e15a = 0;
    s_time_on = 0;
    s_clr_phase = 0;
    s_clr_wait = 0;
    s_clr_mode = 0;
    s_warp_jingle = 0;
    s_warp_jwait = 0;
    s_warp_dest = 0;
    s_dump_left = 0;
    s_dump_phase = 0;
    s_scroll_px = 0;
    s_scroll_delta = 0;
    s_wrap_pending = 0;
    s_row_carry = 0;
    s_scroll_base = 0;
    s_ram_only = 0;
    s_dma_flip = 0;
    s_e700 = 0;
    s_e70d = 0;
    s_end_snapped = 0;
    s_end_phase = 0;
    s_end_wait = 0;
    s_end_rows = 0;
}

void map_script_resume_scroll(void)
{
    /* After clear/timeout: restore target. E150 is already 0; ramp stays
     * frozen while s_clr_phase != 0 (MSX gameplay_frame_loop skips 9480). */
    if (!s_cred_on)
        s_e712 = SCROLL_SPEED_TGT;
}

/* SUB_ram_8f5e: while E150 bit0, each E700-bit1 row DECs E156 and clamps E710.
 * 8f78 always DECs (0 wraps to 255, then 8f7e JR Z is not taken). countdown
 * after DEC ==0 -> E710=0, E157 extras, E15A=0xC0, E150:=2 (hold + SET 7). */
static void base_approach(u8 row_adv)
{
    u8 flags = entity_base_flags();
    u8 mode;

    if (flags & 4)
        return;
    if (flags & 2)
        return;
    if (!(flags & 1))
        return;
    if (!row_adv)
        return;

    s_e156--;
    if (!s_e156)
    {
        s_e710 = 0;
        /* 8fa6: E157 bit5 + !E102.7 -> 5211 fade into hold music bed. */
        if ((s_e157 & 0x20) && !(player_e102() & 0x80))
            sound_fade();
        s_e15a = 0x00C0;
        mode = (u8)(s_e157 & 0x1F);
        if (mode == 0x10)
            s_e712 = 0;
        if (mode == 0x11)
            base_mode_11();
        entity_base_arm();
        if (!(s_e157 & 0x10))
            s_time_on = 1;      /* 9014: write TIME at 0x3AB9 */
        if (!(s_e158 & 2))
        {
            /* 8fd4 SET 3,(E12D) -- OR bit1 so stream bit survives. */
            s_ms.spawn_ctrl = (u8)(s_ms.spawn_ctrl | 0x0A);
            entity_on_spawn_ctrl(s_ms.spawn_ctrl);
            s_e159 = s_e155;
        }
        return;
    }
    if (s_e156 < 10 && (u8)(s_e157 & 0x1F) < 0x11)
    {
        u8 cap = k_approach[s_e156];

        if (s_e710 > cap)
            s_e710 = cap;
    }
}

static u8 daa_sub1(u8 a, u8 *carry)
{
    u8 c = (u8)(a == 0);
    u8 hc = (u8)((a & 0x0F) == 0);

    a--;
    if (hc || ((a & 0x0F) > 9))
        a = (u8)(a - 6);
    if (c || ((a >> 4) > 9))
        a = (u8)(a - 0x60);
    *carry = c;
    return a;
}

/* 9061: SUB 3 / DAA on E159. Triple daa_sub1 loses CF at 0x00/0x01
 * so bit3 never RES'd when the BCD minute gate expires. */
static u8 daa_sub3(u8 a, u8 *carry)
{
    u8 c = (u8)(a < 3);
    u8 hc = (u8)((a & 0x0F) < 3);

    a = (u8)(a - 3);
    if (hc || ((a & 0x0F) > 9))
        a = (u8)(a - 6);
    if (c || (a > 0x9F))
        a = (u8)(a - 0x60);
    *carry = c;
    return a;
}

/* LAB_ram_9325: timer hit 00:00. No award. ALC bump, E150 := 0x0E. */
static void base_timeout(void)
{
    /* RES 3,E12D then bfbf / E12E+0x10 / bfab while bit1 still set. */
    s_ms.spawn_ctrl = (u8)((s_ms.spawn_ctrl & (u8)~0x08) | 0x02);
    entity_spawn_res3();
    entity_on_spawn_ctrl(s_ms.spawn_ctrl);
    entity_dec_encounter_b();
    entity_timeout_alc();
    if ((s_e157 & 0x20) && !(player_e102() & 0x80))
        sound_fade();
    s_e154 = 0;
    s_e155 = 0;
    s_time_on = 0;
    entity_base_set(0x0E);
}

/* 90a6 / 91a6: E152==0 during hold. ALC ease + dec_encounter_a +
 * RES 3,E12D then E150=0, 90dc, then 90fe sweep. */
static void base_clear_full(void)
{
    u8 mode = (u8)(s_e157 & 0x1F);

    entity_alc_ease();
    entity_dec_encounter_a();
    /* 90c2 SUB_bfc8: E150 bit1 still set, so E130 is not incremented --
     * HUD refresh of E12E/E132/E130 only. E150=0 follows at 90c9. */
    entity_inc_encounter_b();
    /* 90c5: RES 3,E12D before E150=0. Keep SET 0 from dec_encounter_a.
     * Do not push s_ms.spawn_ctrl through entity_on_spawn_ctrl -- R1 never
     * sends cmd 0 so that copy may lack bit1. */
    entity_spawn_res3();
    s_ms.spawn_ctrl = (u8)((s_ms.spawn_ctrl | 0x01) & (u8)~0x08);
    entity_base_set(0);
    s_time_on = 0;
    entity_convert_clear_types();
    s_clr_mode = mode;
    /* E157 bit7 skips the nametable sweep (90fe -> 914e) but still explodes. */
    if (s_e157 & 0x80)
    {
        entity_explode_airborne();
        s_clr_phase = 4;
        s_clr_wait = 4;
    }
    else
    {
        s_clr_phase = 1;
        s_clr_wait = 3;
        /* 90fe: WRTVDP R7=0x0F then gameplay_frame_loop B=3. */
        mode_backdrop_flash(1);
    }
}

static void base_clear_finish(void)
{
    u8 mode = s_clr_mode;

    s_clr_phase = 0;
    /* 91ea: SUB 0x0F on E157&0x1F. C -> 4163; Z -> B7A5; DEC Z -> 91FD;
     * DEC Z -> 9251; else 92af. */
    if (mode == 0x0F)
    {
        /* 91F1: E722=0xB7A5, SET 5,E102 → 40DA (ev11 + wait 0x64 + 940c). */
        map_script_warp(map_script_ptrs[0]);
        return;
    }
    if (mode == 0x10)
    {
        ending_setup_91fd();
        return;
    }
    if (mode == 0x11)
    {
        lab_9251_start();
        return;
    }
    if (mode >= 0x12)
    {
        /* LAB_92af: E722=0xA6F4, SET 5+3 → 40DA → LAB_414d. */
        if (!s_cred_on)
            map_script_warp(MAP_ENDING_STREAM);
        return;
    }
    /* SUB_ram_4163: ev1, or ev2 if round%8==0. Attract (E102.7) skips.
     * GAME OVER already played ev4 (0x4679); do not restart stage BGM. */
    if (player_is_over())
        return;
    if (player_e102() & 0x80)
        return;
    if ((s_ms.round & 7) == 0)
        sound_play_event(SND_EV_ROUND8);
    else
        sound_play_event(SND_EV_THEME);
}

static void base_clear_tick(void)
{
    if (!s_clr_phase)
        return;

    /* phase 5 = SUB_ram_92d0: wait while clear/state jingle occupies slot 2/3. */
    if (s_clr_phase == 5)
    {
        if (sound_jingle_waiting())
            return;
    }
    else if (s_clr_wait)
    {
        s_clr_wait--;
        if (s_clr_wait)
            return;
    }

    if (s_clr_phase == 1)
    {
        /* D=2: A0 -> E7 / A7-AA -> E3-E6, then explode_enemies + 4 frames. */
        sweep_nametable(2);
        entity_explode_airborne();
        s_clr_phase = 2;
        s_clr_wait = 4;
        return;
    }
    if (s_clr_phase == 2)
    {
        s_clr_phase = 3;
        s_clr_wait = 3;
        return;
    }
    if (s_clr_phase == 3)
    {
        /* D=1: E3-E7 -> 3E / E3-E6 -> 3A-3D. */
        sweep_nametable(1);
        entity_explode_airborne();
        s_clr_phase = 4;
        s_clr_wait = 4;
        return;
    }
    if (s_clr_phase == 4)
    {
        if (s_clr_mode < 0x10)
        {
            sound_stop_all();
            sound_play_event((s_e157 & 0x20) ? SND_EV_CLEAR_A : SND_EV_CLEAR_B);
            s_clr_phase = 5;
            return;
        }
        s_clr_phase = 6;
    }
    if (s_clr_phase == 5)
    {
        if (s_clr_mode < 0x10)
            sound_stop_all();
        s_clr_phase = 6;
    }
    if (s_clr_phase == 6)
    {
        /* LAB_ram_91a6: award + resume, then 100 (or 1 if mode&0x1E==0x10). */
        map_script_base_cleared();
        s_clr_phase = 7;
        s_clr_wait = ((s_clr_mode & 0x1E) == 0x10) ? 1 : 100;
        return;
    }
    if (s_clr_phase == 7)
    {
        s_clr_phase = 8;
        s_clr_wait = 40;
        return;
    }
    base_clear_finish();
}

static void base_timer_tick(void)
{
    u8 l = s_e154;
    u8 h = s_e155;
    u8 c;

    l = daa_sub1(l, &c);
    if (c)
    {
        l = 0x59;
        h = daa_sub1(h, &c);
        /* 9061 SUB 3,DAA -- CF => E159 BCD underflow -> RES 3,E12D. */
        s_e159 = daa_sub3(s_e159, &c);
        if (c && (s_e158 & 1))
        {
            /* Keep stream bit1 (R1 never re-sends cmd 0). */
            s_ms.spawn_ctrl = (u8)((s_ms.spawn_ctrl & (u8)~0x08) | 0x02);
            entity_on_spawn_ctrl(s_ms.spawn_ctrl);
        }
    }
    s_e154 = l;
    s_e155 = h;
    if (!l && !h)
        base_timeout();
}

/* 8f5e hold (E150 bit1): DEC E15A; E154 BCD; E152==0 -> 90a6. */
static void base_hold(void)
{
    u8 flags = entity_base_flags();

    if (flags & 4)
    {
        /* 934d: timeout residue. Last live segment gone -> drop E150. */
        if (!s_e152)
        {
            if (flags & 2)
            {
                entity_base_set(0x0C);
                /* 9380: bit5 -> stop + 4163 (E102.7 gated). */
                if ((s_e157 & 0x20) && !(player_e102() & 0x80)
                    && !player_is_over())
                {
                    sound_stop_all();
                    if ((s_ms.round & 7) == 0)
                        sound_play_event(SND_EV_ROUND8);
                    else
                        sound_play_event(SND_EV_THEME);
                }
            }
            else
            {
                entity_base_set(0);
                map_script_resume_scroll();
            }
        }
        return;
    }
    if (!(flags & 2))
        return;
    if (s_e15a)
    {
        s_e15a--;
        if (!s_e15a && (s_e157 & 0x20) && !(player_e102() & 0x80)
            && !player_is_over())
            sound_play_event(SND_EV_FANFARE);
    }
    /* 9047: E157 bit4 skips the BCD timer / TIME HUD. */
    if (!(s_e157 & 0x10))
        base_timer_tick();
    flags = entity_base_flags();
    if (flags & 4)
        return;
    /* 908a: E152==0 -> 90a6 full clear. */
    if (!s_e152)
    {
        base_clear_full();
        return;
    }
    /* E152<=E153 -> E150 bit3 (SLA fire). */
    if (s_e152 && s_e153 && s_e152 <= s_e153)
        entity_base_or_flags(8);
}

void map_script_base_cleared(void)
{
    u8 idx = (u8)(s_e157 & 0x1F);

    /* 0x91A4: E157&0x1F >= 0x10 -> SET 2,E102 (mute ev8/ev9). */
    if (idx >= 0x10)
        player_e102_set(0x04);
    if (idx < 19 && k_clear_award[idx])
        player_add_score(k_clear_award[idx]);
    map_script_resume_scroll();
}

static void script_boot(u8 round, u16 pc)
{
    u8 i;

    if (round > 8)
        round = 8;

    /* 0x4119 AND 7 / 0x411E AND 7: the late background is loaded only when the
     * round being entered is a multiple of 8 and the one being left is not.
     * s_prev_round is E701 before 0x4118 writes it; 0 at cold boot, which is
     * the !(old&7) arm and therefore the plain charset. */
    s_bg_late_on = (u8)(!(round & 7) && (s_prev_round & 7));
    s_prev_round = round;

    memset(&s_ms, 0, sizeof(s_ms));
    for (i = 0; i < COL_SLOTS; i++)
        s_col[i].pos = 0x80;
    for (i = 0; i < STREAM_SLOTS; i++)
        s_stream[i].used = 0;
    s_idol_cur = 0;
    s_assemble_peek = 0;
    s_cred_on = s_cred_exit = 0;
    entity_clear_enemies();

    s_ms.round = round;
    s_ms.pc = pc;
    s_ms.running = TRUE;
    if (round >= 1 && round <= 8)
        s_continue_round = round;
    /* MSX 0x4225: E12D := 3 (bit0 sticky + bit1 stream). alc_recompute
     * already ran; keep bit1 so cmd-B hold SET3 (8fd4) cannot wipe the
     * R1 stream -- R1 never sends cmd 0 to re-arm bit1. */
    s_ms.spawn_ctrl = 0x02;
    entity_on_spawn_ctrl(s_ms.spawn_ctrl);
    entity_alc_reset();
    s_ms.last_cmd = "-";
    load_trigger_from_pc();
    /* LAB_941b: E702 = first trigger - 1 so step 1 fires immediately. */
    s_ms.row = (u16)(s_ms.trigger - 1);
    s_scroll_px = 0;
    s_scroll_delta = 0;

    bg_init();
    /* Title / 0x4065 and mode-0x0F R8 boot play ev7/ev2. Warp is quiet. */
    if (!s_boot_quiet)
        sound_play_round(s_ms.round);
}

void map_script_init_round(u8 round)
{
    u8 idx;

    if (round > 8)
        round = 8;
    idx = (u8)(8 - round);
    scroll_speed_reset(SCROLL_SPEED_TGT);
    script_boot(round, map_script_ptrs[idx]);
}

void map_script_init(void)
{
    map_script_init_round(MAP_DEFAULT_ROUND);
}

u8 map_script_continue_round(void)
{
    return s_continue_round;
}

void map_script_update(void)
{
    if (s_ms.banner_timer)
    {
        s_ms.banner_timer--;
        if (!s_ms.banner_timer)
        {
            player_e102_res(0x10);
            if (mode_get() == MODE_ORIGINAL && s_ms.banner[0])
                hud_fill_tile(BG_A, 8, mode_text_row(10), 0, 9);
            if (s_banner_bgm_arm)
            {
                s_banner_bgm_arm = 0;
                /* SUB_ram_4163 after round banner: restore main theme if fanfare
                 * or other SFX cleared the ev7->ev1 chain. */
                if (s_ms.running && !s_cred_on && !player_is_over()
                    && !sound_bgm_active())
                {
                    if ((s_ms.round & 7) == 0)
                        sound_play_event(SND_EV_ROUND8);
                    else
                        sound_play_event(SND_EV_THEME);
                }
            }
        }
    }

    s_scroll_delta = 0;
    s_row_carry = 0;
    if (s_ms.running)
    {
        u16 sum;
        u16 prev_px;

        /* 9480 BIT 5 RET NZ + 40DA wait_frames(0x64): no ramp, no 97e3,
         * no 9393. Load happens when the jingle wait hits 0, then JP 4074. */
        if (s_warp_jingle)
        {
            warp_jingle_tick();
            cred_tick();
            bg_update();
            return;
        }

        /* scroll_velocity_ctrl 0x9480: ramp E710 toward E712 every 4 frames.
         * E150 bits 0-1 skip the ramp. Clear ceremony freezes E710=0 -- MSX
         * 90a6 runs inside gameplay_frame_loop which never calls 9480.
         * 9251 also uses gameplay_frame_loop (9393: wait/pause/score/
         * entity_dispatch/player_hit only). Do not assemble rows or move
         * VSCROLL while letters write fixed TMS VRAM 0x3924.. */
        if (s_clr_phase || s_end_phase)
            s_e710 = 0;
        else if (!(entity_base_flags() & 3) && s_e710 != s_e712)
        {
            s_e713++;
            if ((s_e713 & 3) == 0)
            {
                if (s_e710 < s_e712)
                    s_e710++;
                else
                    s_e710--;
            }
        }
        /* E711 += E710; carry -> map_script_step, or 980e if E700 bit2. */
        sum = (u16)s_e711 + s_e710;
        s_e711 = (u8)sum;
        if (sum > 255)
        {
            if (s_e700 & 4)
            {
                /* 94bc BIT 2 -> JP 980e. No E702++, no fire, no 97e3. */
                lab_980e();
                if (s_row_carry)
                    base_approach(1);
            }
            else
            {
                s_skip_precompute = 0;
                s_ms.row++;
                fire_pending();
                /* Cmd 9 JP 9433 RETs without 97d5/precompute. Japan has
                 * no peek (TMS nametable has no VSCROLL). A peek here
                 * assembled the jumped-to row with the old columns
                 * (often a full 0x28 sky line) into the next wrap slot
                 * -- a hard blue cut through live green. */
                if (!s_skip_precompute)
                {
                    /* 97e3 / peek must use the pre-carry pixel. VSCROLL is
                     * still that value; wrap(pre) RAW is the 8px tile being
                     * revealed. PR #91 set scroll_px before 97e3 so DMA hit
                     * wrap(post). leftover E711 at cruise E710=0x34 makes
                     * wrap(post) the peek sliver (letterbox), one NT row
                     * north of wrap(pre). #95 then bound sat_to_nt to
                     * wrap(raw)+Y/8, so entity stamps (after this update
                     * sets POST scroll) also hit peek: missing 87e2 digits,
                     * 88ed dest leftover on the live cell, sky/green cut.
                     * Stamps use tile_wrap (scroll&~7); 97e3 DMA stays
                     * wrap(pre) RAW. Japan has no VSCROLL; 9a79 dumps 24
                     * rows. Do not move s_scroll_px until end of tick. */
                    /* 97e3: assemble once, DMA one nametable row at the wrap
                     * edge, then peek row+1 (restored) so subpixel VSCROLL is
                     * never stale/green. Peek stays inside this block so
                     * cmd 9 cannot DMA a 0x28 sky line into wrap(scroll+8). */
                    scroll_precompute(s_ms.row);
                    s_row_carry = 1;
                    peek_next_row((u16)(s_ms.row + 1));
                }
                base_approach(1);
            }
        }
        lab_9251_tick();
        /* 8f5e is CALL 0x4077 (main loop), not 0x46A8. GO wait is
         * 9480 + 9393 only — 90a6 / hold must not keep ticking.
         * base_clear_tick phase 4/5 sound_stop_all would kill ev4. */
        if (!player_is_over())
        {
            base_hold();
            base_clear_tick();
        }
        prev_px = s_scroll_px;
        if (s_end_snapped)
            s_scroll_px = 0;
        else
            s_scroll_px = (u16)(((u16)(s_ms.row - s_scroll_base) << 3)
                                + (s_e711 >> 5));
        s_scroll_delta = (u8)(s_scroll_px - prev_px);
    }
    cred_tick();
    bg_update();
}

u8 map_script_scroll_delta(void)
{
    return s_scroll_delta;
}

u8 map_script_scroll_frac(void)
{
    return (u8)(s_scroll_px & 7);
}

u8 map_script_row_carry(void)
{
    return s_row_carry;
}

u8 map_script_scroll_speed(void)
{
    return s_e710;
}

void map_script_draw_hud(void)
{
    const ModeAssets *a = mode_assets();
    u16 cols = a->screen_width / 8;

    if (mode_get() == MODE_ORIGINAL)
    {
        hud_draw_alc();
        hud_draw_round(s_ms.round);
        hud_draw_time(s_time_on, s_e155);
        return;
    }

    VDP_setTextPalette(PAL0);

    if (s_ms.banner_timer && s_ms.banner[0])
    {
        u16 len = (u16)strlen(s_ms.banner);
        u16 x = (cols > len) ? (u16)((cols - len) / 2) : 0;
        VDP_setTextPalette(PAL1);
        VDP_drawText(s_ms.banner, x, mode_text_row(4));
    }
    else
    {
        VDP_clearText(0, mode_text_row(4), cols);
    }

    VDP_drawText(a->name, 1, 1);
}

const MapScript *map_script_state(void)
{
    return &s_ms;
}

u8 map_script_credits_active(void)
{
    return s_cred_on;
}

u8 map_script_credits_exit(void)
{
    return s_cred_exit;
}

void map_script_draw_credits(void)
{
    const ModeAssets *a = mode_assets();
    u16 cols = a->screen_width / 8;
    u16 i;
    u16 row;

    if (!s_cred_on)
        return;
    if (!s_cred_dirty)
        return;
    s_cred_dirty = 0;
    cred_clear_page();

    i = s_cred_idx;
    row = mode_text_row(CRED_ROW0);
    VDP_setTextPalette(PAL1);
    while (i < sizeof(k_cred_ctrl) && k_cred_ctrl[i] != 0xFF)
    {
        u8 id = k_cred_ctrl[i++];
        if (id < CRED_NSTR)
        {
            const char *s = k_cred_str[id];
            u16 len = (u16)strlen(s);
            u16 vis = (mode_get() == MODE_ORIGINAL) ? MODE_BAR_COL : cols;
            u16 x = (vis > len) ? (u16)((vis - len) / 2) : 0;
            if (mode_get() == MODE_ORIGINAL)
                hud_draw_str(BG_A, x, row, s);
            else
                VDP_drawText(s, x, row);
        }
        row++;
        if (row > mode_text_row(20))
            break;
    }
}

/* 0x40EA: ev11, wait_frames(0x64), then 940c load, then 0x4133 ev10 or 0x4163. */
#define DUMP4177_CELLS      0x240   /* 24x24, Japan BC at 417c */
#define DUMP4177_PER_FRAME  192     /* ~3 frames; Z80+VDP walk budget */

static void dump4177_begin(u8 phase)
{
    s_dump_h = 0;
    s_dump_l = 0;
    s_dump_left = DUMP4177_CELLS;
    s_dump_phase = phase;
}

static void dump4177_advance(void)
{
    /* 41a3 DEC H / JP P / H=0x17 / DEC L, then L -= 5 wrap 24. */
    if (s_dump_h == 0)
    {
        s_dump_h = 0x17;
        s_dump_l--;
    }
    else
        s_dump_h--;
    {
        u8 a = (u8)(s_dump_l - 5);

        if ((s8)a < 0)
            a = (u8)(a + 0x18);
        s_dump_l = a;
    }
}

static void dump4177_step(u16 n)
{
    while (n-- && s_dump_left)
    {
        u8 col = s_dump_h;
        u8 row = s_dump_l;
        u8 tid;

        if (col < PF_COLS && row < BOOT_ROWS)
        {
            tid = s_e800[(u8)((s_e714 + row) % BOOT_ROWS)][col];
            /* 4177 CALL 8948 then SETWRT one byte. punch_cell is that
             * E800-then-VRAM order. Tile 0 is Japan 40FB blank, not
             * letter 0x20 / sky 0x28. */
            punch_cell(col, row, tid);
        }
        dump4177_advance();
        s_dump_left--;
    }
}

static void warp_play_dest_bgm(void)
{
    if (player_is_over())
        return;
    /* load_bg_level: new&7==0 and old&7==0 -> stop + ev10, skip 4163. */
    if (((s_warp_new & 7) == 0) && ((s_warp_old & 7) == 0))
    {
        sound_stop_all();
        sound_play_event(SND_EV_ROUNDVAR);
        return;
    }
    /* LAB_ram_413a / 0x4125: stop again when loading tiles into a *8 dest. */
    if ((s_warp_new & 7) == 0)
        sound_stop_all();
    if ((s_warp_new & 7) == 0)
        sound_play_event(SND_EV_ROUND8);
    else
        sound_play_event(SND_EV_THEME);
}

static void arm_warp_jingle(u8 old_r, u8 new_r)
{
    s_warp_jingle = 1;
    s_warp_jwait = 0x64;
    s_warp_old = old_r;
    s_warp_new = new_r;
}

static void warp_commit_load(void)
{
    u16 dest = s_warp_dest;
    u8 keep_jingle = s_warp_jingle;

    s_warp_dest = 0;
    s_boot_quiet = 1;
    /* Assemble E800 / 946e; 4177 walks it onto VRAM after this returns.
     * init_round's scroll_speed_reset must not drop SET-5. */
    s_defer_nt_flush = 1;
    if (dest == MAP_ENDING_STREAM)
    {
        map_script_start_ending();
        s_boot_quiet = 0;
        s_defer_nt_flush = 0;
        s_warp_jingle = keep_jingle;
        entity_alc_complete();
        return;
    }
    if (blob_ok(dest, 3))
    {
        script_boot(resolve_round_from_ptr(dest), dest);
        s_boot_quiet = 0;
        s_defer_nt_flush = 0;
        s_warp_jingle = keep_jingle;
        entity_alc_complete();
        return;
    }
    map_script_init_round(resolve_round_from_ptr(dest));
    s_boot_quiet = 0;
    s_defer_nt_flush = 0;
    s_warp_jingle = keep_jingle;
    entity_alc_complete();
}

static void warp_jingle_tick(void)
{
    if (!s_warp_jingle)
        return;

    /* 40F8 LDIR E800=0 then 4177 blank, THEN wait_frames(0x64), then
     * 940c / 946e / 4177 reveal. 9393 stays skipped for the whole
     * ceremony (KEEP #93). */
    if (s_dump_left)
    {
        dump4177_step(DUMP4177_PER_FRAME);
        if (s_dump_left)
            return;
        if (s_dump_phase == 1)
        {
            s_dump_phase = 0;
            s_warp_jwait = 0x64;
            return;
        }
        /* Reveal finished: 4163 / ev10 after 940c. */
        s_dump_phase = 0;
        s_warp_jingle = 0;
        warp_play_dest_bgm();
        return;
    }
    if (s_warp_jwait)
    {
        s_warp_jwait--;
        return;
    }
    /* 40DA: wait_frames returned; 940c / 946e now, then 4177, then 4163. */
    warp_commit_load();
    dump4177_begin(2);
    /* SND_EV_THEME / 4163 runs after this load (warp_play_dest_bgm). */
}

u8 map_script_warp_waiting(void)
{
    return s_warp_jingle;
}

void map_script_warp(u16 dest)
{
    u8 old_round = s_ms.round;

    /* Type-72 black orb: dest is +0x1c/+0x1d from 87bb (table word).
     * E722==0 skips stop/ev11/load (40E2 JP 414d). Do not invent R8. */

    /* 40BA: clear live slots + E150=0. Do not write type 0x28 (totem punch). */
    entity_clear_enemies();

    /* level_complete_handler: E722==0 skips stop/ev11 and the load. */
    if (!dest)
    {
        entity_alc_complete();
        return;
    }

    sound_stop_all();
    sound_play_event(SND_EV_CLEARJING);
    s_boot_quiet = 1;
    s_warp_dest = dest;
    /* MAP_ENDING_STREAM 0xA6F4 still arms credits — after the 0x64 wait. */
    if (dest == MAP_ENDING_STREAM)
        s_warp_new = 0;
    else
        s_warp_new = resolve_round_from_ptr(dest);
    arm_warp_jingle(old_round, s_warp_new);
    /* 40FB: LD (E800),0 / LDIR BC=0x23F, then 4177. Wait starts after. */
    memset(s_e800, 0, sizeof(s_e800));
    s_warp_jwait = 0;
    dump4177_begin(1);
}
