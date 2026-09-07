#ifndef MAP_SCRIPT_H
#define MAP_SCRIPT_H

#include <genesis.h>

/* TMS9918A colour 12 (0x21B03B) as a Mega Drive colour, written out instead of
 * built with RGB24_TO_VDPCOLOR. The macro rounds each channel up before masking
 * to 3 bits and lands colour 12 on the same value as colour 2 (0x21C842), and
 * those two greens ARE the ground texture -- charset tiles 0x25/0x26/0x27 are a
 * 2/12 stipple and nothing else. Collapsed, every land tile renders flat.
 * Nearest-level rounding collides too; the pair has to be separated on purpose.
 * See the derivation above s_tms_pal in src/map_script.c. */
#define TMS_DARK_GREEN  0x04A2

/*
 * MSX map-script interpreter.
 *
 * Live MSX state in the scroll_state block at 0xE700:
 *   round   = 0xE701
 *   row     = 0xE702
 *   PC      = 0xE704   (MSX address into the script blob)
 *   trigger = 0xE706
 *
 * Record: [row : 2 LE] [cmd : 1] [operands ...]
 * Low nibble of cmd indexes the 13 handlers @0x94EB.
 * Operand lengths match zanac-re/tools/decode_mapscript2.py.
 *
 * Scripts + tile-column data live in res/map_blob.bin (MSX 0x9B64-0xBE26).
 * PC is an MSX address, not a byte offset into a demo array.
 */

typedef enum {
    MAPCMD_SPAWN_CTRL    = 0x0,
    MAPCMD_PLACE_TILES   = 0x1,
    MAPCMD_COL_GROUPS    = 0x2,
    MAPCMD_TILE_COPY     = 0x3,
    MAPCMD_COL_GROUPS_ADD= 0x4,
    MAPCMD_STREAM_SLOTS  = 0x5,
    MAPCMD_SET_E71C      = 0x6,
    MAPCMD_DISABLE_GRPS  = 0x7,
    MAPCMD_IDOL_BANNER   = 0x8,
    MAPCMD_SCRIPT_JUMP   = 0x9,
    MAPCMD_VRAM_GLYPH    = 0xA,
    MAPCMD_WIDE_SLOT     = 0xB,
    MAPCMD_SPAWN_PACE    = 0xC
} MapCmd;

typedef struct {
    u16 pc;          /* MSX address (0xE704) */
    u16 row;         /* scroll row     (0xE702) */
    u16 trigger;     /* next cmd row   (0xE706) */
    u8  round;       /* E701 */
    u8  running;
    u8  param;       /* high nibble of last cmd */
    u8  spawn_ctrl;  /* E12D, cmd 0 */
    u8  e71c;        /* cmd 6 */
    s8  last_nudge;  /* cmd C */
    u16 idol_ptr;    /* cmd 8 operand */
    u16 banner_timer;
    u8  credits;     /* E102 bit 3: staff roll active */
    const char *last_cmd;
    char banner[16];
} MapScript;

void map_script_init(void);
void map_script_init_round(u8 round);
/* Last round reached (MSX E701 continue). Title START+C uses this. */
u8   map_script_continue_round(void);
void map_script_update(void);
/* Japan 9a79 is vblank after 87e2/88ed write E800. Queue wrap NT at 97e3
 * (pre-carry RAW) and DMA the e800 row after entity_update punches. */
void map_script_commit_wrap(void);
void map_script_draw_hud(void);
void map_script_reset_scroll(void);
const MapScript *map_script_state(void);

/* Pixels the nametable advanced this frame (E711>>5 + row*8). SAT Y for
 * 8f25-class ground is +8 per E700.1, not this value. */
u8   map_script_scroll_delta(void);
/* E711>>5 subpixel of MD VSCROLL (0-7). TMS nametable has none.
 * Draw-only for 8f45-class sprites. Collision / SAT stay on the 8px grid. */
u8   map_script_scroll_frac(void);
/* E700 bit 1 this frame: 97e3 ran, or 980e SET bit1. */
u8   map_script_row_carry(void);
/* E710 current_scroll_speed. Type 85 8efc: NZ -> dir C, Z -> dir B. */
u8   map_script_scroll_speed(void);

/* Last base segment died: E712 := 0x34 so scroll_velocity_ctrl ramps E710 back. */
void map_script_resume_scroll(void);
/* Last segment: clear-award 0x9302[E157&0x1F] then resume_scroll. */
void map_script_base_cleared(void);
/* 8baa/8ca2: DEC E152 and punch destroyed tiles at live SAT x,y.
 * 8ca2 origin is per-type (75: X-0x1C Y-0x0C; 76: X-0x20 Y-0x0C;
 * 77: X-0x1C Y-0x10; 73/74/78: X-0x20 Y-0x10), not a flat -0x20/-0x10. */
void map_script_base_seg_down(s16 x, s16 y, u8 variant);
/* Last live KIND_BASE died: E152 := 0 so 8f5e hold can 90a6. */
void map_script_base_no_segments(void);
/* 8c15: paint from 8948 bind SAT (post Y+0x10, pre table xo/yo), not live SAT.
 * 8c39 uses IX+06/+07 from 8a95; 8ac7 xo/yo is hitbox only. */
void map_script_base_8c15(s16 x, s16 y, u8 variant, u8 phase);
/* 8948 once at arm: L=SAT_Y pre +0x10, H=SAT_X-0x20 (unsigned).
 * SAT X itself is 964C 8-bit (ybase*8 + blob_X - 0x20). Store NT cell
 * like IX+06/+07 so later 8c15 does not re-bind against live VSCROLL. */
int  map_script_8948_cell(s16 sat_x, s16 sat_y_pre, u8 *col, u8 *row);
void map_script_base_8c15_at(u8 col, u8 row, u8 variant, u8 phase);
/* 8c80: type 79 88ed stages. HP>=0x15 -> 8ced; NZ -> 8cfa; 0 -> 8d07. */
void map_script_punch_79_hp(s16 x, s16 y, u8 hp);
/* 8854/88ed: punch 0x88ab destroyed-tile desc for types 84-86 at SAT x,y. */
void map_script_punch_88ab(s16 x, s16 y, u8 type);
/* 880d family: 88ed punches at SAT x,y with per-branch origin SUB. */
void map_script_punch_88b1(s16 x, s16 y); /* 8892 type 87: X-0x20 Y-0x10 */
void map_script_punch_88c2(s16 x, s16 y); /* 8824 type 81: X-0x24 Y-0x10 */
void map_script_punch_88cb(s16 x, s16 y); /* 8892 type 88: X-0x20 Y-0x10 */
void map_script_punch_88d8(s16 x, s16 y); /* 8874 type 82/89: X-0x28 Y-0x18 */
/* 87e2 type 82: stamp digit glyph 0x30+fire# (X-0x28 Y-0x10); no SAT. */
void map_script_stamp_82_digit(s16 x, s16 y, u8 fire_num);
/* Type-72 black orb: dest is a stream pointer. Boots that PC + resolved round. */
void map_script_warp(u16 dest);
/* 40DA 4177 blank + wait_frames(0x64) + load + 4177 reveal. SET 5. */
u8   map_script_warp_waiting(void);

/* LAB_92af / init_credits_stream: arm stream 0xA6F4 and credits_display.
 * Award E157&0x1F==0x10 is 91FD, ==0x11 is 9251; this is >=0x12 only. */
void map_script_start_ending(void);
u8   map_script_credits_active(void);
u8   map_script_credits_exit(void);
void map_script_draw_credits(void);
/* type62 every-16f LDIRVM 0x1800: poke row0 24-col (ROM 876b/878b). */
void map_script_type62_poke(u8 phase);

#endif
