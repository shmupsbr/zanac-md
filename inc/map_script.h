#ifndef MAP_SCRIPT_H
#define MAP_SCRIPT_H

#include <genesis.h>

/* Title-only (k_tms in src/title.c). Lord-Nightmare 0x21C842 / 0x21B03B
 * collapse through RGB24_TO_VDPCOLOR; this word keeps title charset 12 off
 * colour 2. In-game PAL3[12] uses TMS_GAME_RGB_12 instead — do not retarget
 * title opening / title_md_palette here. */
#define TMS_DARK_GREEN  0x04A2

/* In-game TMS→MD RGB24. WebMSX / original-MSX look = V9938 default 3-bit
 * triples, each channel n*32 so RGB24_TO_VDPCOLOR (+0x10, top 3 bits) keeps
 * the triple. Not title branding. Lord-Nightmare 0x21C842/0x21B03B washed
 * the playfield and mapped 2 and 12 onto one CRAM word. */
#define TMS_GAME_RGB_0   0x000000  /* (0,0,0) */
#define TMS_GAME_RGB_1   0x000000  /* (0,0,0) */
#define TMS_GAME_RGB_2   0x20C020  /* (1,6,1) medium green */
#define TMS_GAME_RGB_3   0x60E060  /* (3,7,3) light green */
#define TMS_GAME_RGB_4   0x2020E0  /* (1,1,7) dark blue */
#define TMS_GAME_RGB_5   0x4060E0  /* (2,3,7) light blue */
#define TMS_GAME_RGB_6   0xA02020  /* (5,1,1) dark red */
#define TMS_GAME_RGB_7   0x40C0E0  /* (2,6,7) cyan */
#define TMS_GAME_RGB_8   0xE02020  /* (7,1,1) medium red */
#define TMS_GAME_RGB_9   0xE06060  /* (7,3,3) light red */
#define TMS_GAME_RGB_10  0xC0C020  /* (6,6,1) dark yellow */
#define TMS_GAME_RGB_11  0xC0C080  /* (6,6,4) light yellow */
#define TMS_GAME_RGB_12  0x208020  /* (1,4,1) dark green — must ≠ 2 */
#define TMS_GAME_RGB_13  0xC040A0  /* (6,2,5) magenta */
#define TMS_GAME_RGB_14  0xA0A0A0  /* (5,5,5) gray */
#define TMS_GAME_RGB_15  0xE0E0E0  /* (7,7,7) white */

/* Intentional MD diverge (Filipe, #116): PAL3[8] only. TMS 8 is the bright
 * half of the red-pink ground (charset 0x17/0x18/0x19 are a 6/8 stipple).
 * Recomputed from the V9938 medium-red base, not the old washed CRAM:
 * TMS_GAME_RGB_8 0xE02020 * 0.8 = 0xB41919 → (6,1,1) = 0x022C.
 * PAL2[8] (k_tms_vdp) stays the full (7,1,1) so asteroids/flyers read;
 * PAL3[9] BONUS digits use TMS_GAME_RGB_9. */
#define TMS_DARK_RED_PINK  0x022C

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
/* Last E701 (0 after 92af). Title START+C boots ptrs[8-E701]. */
u8   map_script_continue_round(void);
void map_script_update(void);
/* Japan 9a79 is vblank after 87e2/88ed write E800. Queue wrap NT at 97e3
 * (pre-carry RAW) and DMA the e800 row after entity_update punches. */
void map_script_commit_wrap(void);
void map_script_draw_hud(void);
void map_script_reset_scroll(void);
const MapScript *map_script_state(void);

/* Pixels the plane camera advanced this frame. SAT Y for 8f25-class
 * ground is still +8 per E700.1 (gameplay grid), not this value. */
u8   map_script_scroll_delta(void);
/* Camera pixel & 7. TMS nametable has no fine scroll. Draw-only for
 * 8f45-class sprites so they track VSRAM. Collision / SAT stay on the
 * 8px grid; stamps stay tile_wrap. */
u8   map_script_scroll_frac(void);
/* VInt: write latched plane VSRAM (BG_A 0, BG_B camera). Title leaves
 * this disarmed so swirl / groove are not overwritten. */
void map_script_apply_vscroll(void);
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
/* type62 every-16f LDIRVM VRAM 0x1800: SGT pattern 0 (ROM 876b/878b).
 * Not a nametable poke. Packed 4bpp 16x16 (4 tiles, nibble 7 cyan). */
void map_script_type62_poke(u8 phase);
const u32 *map_script_type62_sgt(void);
u8   map_script_type62_sgt_phase(void);

#endif
