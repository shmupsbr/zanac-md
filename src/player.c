#include "player.h"
#include "mode.h"
#include "entity.h"
#include "resources.h"
#include "sound.h"
#include "hud.h"
#include "vel_dir.h"

#ifndef SPR_FLAG_AUTO_DEPTH
#define SPR_FLAG_AUTO_DEPTH 0x0200
#endif

/* fire_init_table 0x751F: E14D ammo/time, E14E mode. Indexed by fire_num 0-7. */
static const u8 k_fire_init[8][2] = {
    { 0x00, 0x02 },
    { 0x64, 0x03 },
    { 0x64, 0x01 },
    { 0xC8, 0x01 },
    { 0x1E, 0x01 },
    { 0x64, 0x03 },
    { 0x0F, 0x03 },
    { 0xFA, 0x03 },
};

static Sprite *s_spr;
static Sprite *s_cspr;      /* pat 15 black; Japan 0x7735 Y+2, same X, under white */
static s16 s_x;             /* MSX SAT X (+02). Original draw: mode_draw_x 0x8F. */
static s16 s_y;
static u8  s_sat_col;       /* MSX SAT colour (+04); ship is 0x8F (EC). */
/* Sub-pixel halves of the position: MSX keeps X as (IX+0x02, IX+0x07) and Y as
 * (IX+0x01, IX+0x06), integer byte first, so the ship moves in 8.8 steps. */
static u8  s_xfrac;
static u8  s_yfrac;
static u8  s_shot_cd;
static u8  s_alc_cadence;
static u8  s_lives;
static u8  s_shot_level;
static u8  s_fire_num;
static u8  s_fire_counter;
static u8  s_fire_mode;
static u8  s_fire_timer;
static u8  s_xvel_sel;
static u8  s_invuln;        /* IX+0x1B i-frame timer */
static u8  s_if_latch;      /* IX+0x05 bit7; type60 86a4 cancel */
static u8  s_dead;
static u8  s_dead_timer;
static u8  s_over;
static u16 s_over_timer;
static u32 s_score;
/* Extra-life threshold E111-E113 (title_screen_init 0x4218). */
static u8  s_e111;
static u8  s_e112;
static u8  s_e113;
/* Gameplay flags E102. Bit2 mutes ev8/ev9 (0x4A5D / 0x4A1C). */
static u8  s_e102;
/* E106-E108 top score. cold_start seeds E107=0x10 -> 100000.
 * title_screen_init zeroes E103-E105 / E102, not E106-E108 or E114. */
static u32 s_hiscore = 100000UL;
/* E114 score_milestone_flags: bit6 flash, bit7 already-announced. */
static u8  s_e114;
/* E148/E14F: chip overflow past max shot (78df). */
static u8  s_e148;
static u8  s_e14f;

/* score_award_table 0x4AEA: 21 x 3-byte little-endian BCD (E103/E104/E105).
 * 4a74: A*3 + 0x4AEA. 4a6a and 91c1 both land here.
 * idx 20 is 00 00 20 = 200000 (does not fit u16). 9251 writes E157=0xB2
 * so E157&0x1F==0x12 -> base_clear_award_index_table[18]==0x14. */
static const u32 k_award[21] = {
    0UL, 1UL, 6UL, 10UL, 17UL, 20UL, 30UL, 50UL, 80UL, 100UL,
    200UL, 400UL, 800UL, 1000UL, 1500UL, 2000UL, 3000UL, 4000UL, 5000UL,
    10000UL, 200000UL
};

static void place_start(void)
{
    /* 0x75E3 SAT X = 0x78, 0x75DF SAT Y = 0xA0. MD mode keeps a centered
     * visual spawn on the wider playfield (no EC). */
    if (mode_get() == MODE_ORIGINAL)
    {
        s_x = 0x78;
        s_y = 0xA0;
    }
    else
    {
        const ModeAssets *a = mode_assets();

        s_x = (s16)((a->playfield_w - SHIP_W) / 2);
        s_y = (s16)(a->playfield_h - SHIP_H - 16);
    }
    s_xfrac = 0;
    s_yfrac = 0;
    s_sat_col = 0x8F;
}

static s16 ship_draw_x(void)
{
    return mode_draw_x(s_x, s_sat_col);
}

/* Japan v1 0x772F after sprite_sat_write:
 *   SAT Y = (IX+01)+0xF1   (ADD 0xF1 = entity Y-15)
 *   SAT X = (IX+02)        (same as white)
 *   name  0x3C  color 0x81
 * sprite_sat_write 0x48C0 is SUB 0x11 (entity Y-17). Complement hardware
 * Y is therefore 2px below the white hull. Pats 14/15 overlap:
 *   same-X same-Y = 29 (black eats the hull — "desconjuntado")
 *   X+1           = 35 (PR #85, worse)
 *   same-X Y+2    =  0 (Japan SAT). Draw-only; collision stays SAT 0x38. */
static s16 ship_compl_draw_x(void)
{
    return mode_draw_x(s_x, 0x81);
}

static s16 ship_compl_draw_y(void)
{
    return (s16)(mode_draw_y(s_y) + 2);
}

/* player_ship_update 0x7634 / 0x765A: add the 8.8 velocity to the position,
 * then clamp the integer part and zero the fraction (0x763C / 0x7662). */
static s16 step_axis(s16 pos, u8 *frac, s16 vel, s16 lo, s16 hi)
{
    s32 acc = ((s32)pos << 8) | *frac;

    acc += vel;
    pos = (s16)(acc >> 8);
    if (pos < lo)
    {
        pos = lo;
        *frac = 0;
    }
    else if (pos > hi)
    {
        pos = hi;
        *frac = 0;
    }
    else
        *frac = (u8)acc;
    return pos;
}

static void show_ship(int vis)
{
    s16 dx;
    s16 cx;
    s16 dy;
    s16 cdy;

    if (!s_spr)
        return;
    dx = ship_draw_x();
    cx = ship_compl_draw_x();
    dy = mode_draw_y(s_y);
    cdy = ship_compl_draw_y();
    if (mode_hud_overlap(dx, MODE_SPR_W))
        vis = 0;
    if (mode_get() == MODE_ORIGINAL)
    {
        s16 y0 = (s16)mode_y_off();
        s16 y1 = (s16)(y0 + 192);

        /* Japan 0x7640 clamps IX+01 to 0xB8 (KEEP). 0x48C0 SUB 0x11
         * then parks SAT Y at 0xA7 — hull stays in the 192. MD skips
         * that SAT offset so ship/shots/enemies share stored Y.
         * Stored 0xB8 draws at 200-215, through the bottom letterbox
         * at 208. Draw-only: sit the white hull on the bar. Collision
         * / 7640 stay 0xB8 (no invented 0xB0 stored wall). Complement
         * stays white Y+2 (7735) after the draw clamp. */
        if (dy + SHIP_H > y1)
            dy = (s16)(y1 - SHIP_H);
        if (dy < y0)
            dy = y0;
        cdy = (s16)(dy + 2);
        if (dy + SHIP_H <= y0 || dy >= y1)
            vis = 0;
    }
    SPR_setVisibility(s_spr, vis ? VISIBLE : HIDDEN);
    if (s_cspr)
        SPR_setVisibility(s_cspr, vis ? VISIBLE : HIDDEN);
    if (vis)
    {
        SPR_setPosition(s_spr, dx, dy);
        SPR_setPriority(s_spr, FALSE);
        s_spr->status &= (u16)~SPR_FLAG_AUTO_DEPTH;
        SPR_setDepth(s_spr, 0);
        if (s_cspr)
        {
            SPR_setPosition(s_cspr, cx, cdy);
            SPR_setPriority(s_cspr, FALSE);
            s_cspr->status &= (u16)~SPR_FLAG_AUTO_DEPTH;
            /* 0x772F appends after 4898; later SAT is behind. */
            SPR_setDepth(s_cspr, 1);
        }
    }
}

static void fire_select(u8 n)
{
    u8 old = s_fire_num;

    if (n > 7)
        n = 7;
    s_fire_num = n;
    s_fire_timer = 0x3C;
    s_fire_counter = k_fire_init[n][0];
    s_fire_mode = k_fire_init[n][1];
    /* Switching weapon despawns the live type-3 (E380 := type 40). */
    if (old != n)
        entity_kill_fire();
    /* fire_select A==2 writes E380=3: Field Shutter is auto, not button-gated.
     * Then 97bc type 69 from fire2_special_table (every select, even re-pick). */
    if (n == 2)
    {
        entity_try_spawn_fire(s_x, s_y, s_xvel_sel);
        entity_fire2_special();
    }
}

/* 0x7544: SUB A / LD (E14F),A / fall into fire_select with A=0.
 * 7548 (fire_select) does not touch E14F — chip overflow 78f2 and
 * type 83 8eaf stay on that path. */
static void fire_reset(void)
{
    s_e14f = 0;
    fire_select(0);
}

static void respawn(void)
{
    place_start();
    s_dead = 0;
    s_dead_timer = 0;
    s_invuln = PLAYER_IFRAMES;
    s_if_latch = 1;         /* 0x75fb SET 7,(IX+0x05) */
    s_shot_level = 0;       /* player_ship_handler 0x7603 zeroes E10B on spawn */
    s_shot_cd = 0;
    s_alc_cadence = 0;
    entity_zero_e130();     /* 0x7606 SUB A / LD (E130),A (HUD tail omitted) */
    s_xvel_sel = 4;
    entity_kill_fire();
    fire_reset();           /* 0x75ff CALL 7544 */
    show_ship(1);
}

void player_init(void)
{
    const ModeAssets *a = mode_assets();

    place_start();
    s_shot_cd = 0;
    s_alc_cadence = 0;
    s_lives = PLAYER_LIVES_INIT;
    s_shot_level = 0;
    s_fire_num = 0;
    s_fire_counter = k_fire_init[0][0];
    s_fire_mode = k_fire_init[0][1];
    s_fire_timer = 0x3C;
    s_xvel_sel = 4;
    s_invuln = PLAYER_IFRAMES;
    s_if_latch = 1;         /* 0x75fb SET 7,(IX+0x05) */
    s_dead = 0;
    s_dead_timer = 0;
    s_over = 0;
    s_over_timer = 0;
    s_score = 0;
    /* title_screen_init: E111=0, E112=0x20, E113=0, E102=0. */
    s_e111 = 0;
    s_e112 = 0x20;
    s_e113 = 0;
    s_e102 = 0;
    s_e114 = 0;
    s_e148 = 0;
    s_e14f = 0;

    PAL_setPalette(PAL2, a->ship->palette->data, CPU);
    s_sat_col = 0x8F;
    /* EC before first frame: 0x75EB SAT colour 0x8F, hardware X = SAT-32.
     * ship.png is 32x16: frame 0 = pat 14 white, frame 1 = pat 15 black. */
    s_spr = SPR_addSprite(a->ship, ship_draw_x(), mode_draw_y(s_y),
                          TILE_ATTR(PAL2, FALSE, FALSE, FALSE));
    s_cspr = SPR_addSprite(a->ship, ship_compl_draw_x(), ship_compl_draw_y(),
                           TILE_ATTR(PAL2, FALSE, FALSE, FALSE));
    if (s_spr)
    {
        SPR_setPriority(s_spr, FALSE);
        SPR_setAnimAndFrame(s_spr, 0, 0);
        /* entity_dispatch 0x445F: E300 writes SAT first (on top).
         * Depth 0 beats leftover Y if SGDK still Y-sorts. */
        s_spr->status &= (u16)~SPR_FLAG_AUTO_DEPTH;
        SPR_setDepth(s_spr, 0);
    }
    if (s_cspr)
    {
        SPR_setPriority(s_cspr, FALSE);
        SPR_setAnimAndFrame(s_cspr, 0, 1);
        s_cspr->status &= (u16)~SPR_FLAG_AUTO_DEPTH;
        SPR_setDepth(s_cspr, 1);
    }
}

s16 player_x(void)
{
    return s_x;
}

s16 player_y(void)
{
    return s_y;
}

u8 player_lives(void)
{
    return s_lives;
}

u8 player_shot_level(void)
{
    return s_shot_level;
}

u8 player_fire_num(void)
{
    return s_fire_num;
}

u8 player_fire_mode(void)
{
    /* E14E. fire_select writes k_fire_init[n][1]. */
    return s_fire_mode;
}

u8 player_invincible(void)
{
    return (u8)(s_if_latch || (s_invuln != 0) || s_dead || s_over);
}

u8 player_dead(void)
{
    return s_dead;
}

u8 player_is_over(void)
{
    return s_over;
}

u8 player_over_ready(void)
{
    return (u8)(s_over && s_over_timer == 0);
}

void player_skip_over(void)
{
    if (s_over)
        s_over_timer = 0;
}

void player_hit(void)
{
    /* 86a4 BIT 7,(IX+0x05): latch cancels death even when +1B is 0. */
    if (s_dead || s_over || s_invuln || s_if_latch)
        return;

    /* collision_response: player type1 -> type60. Lives/DEC wait until
     * type60 clear SETs E102 bit0 (death->continue), then player_hit_handler. */
    s_dead = 1;
    s_dead_timer = 0;
    show_ship(0);
    entity_kill_fire();
    fire_reset();               /* 0x7544: E14F=0 then fire_select(0) */
    entity_spawn_pdeath(s_x, s_y);  /* SRL E132/E12E + ev16 + 86F3 arm */
}

void player_add_shot_level(void)
{
    /* handler_type63_power_chip 78d7: INC E10B, CP 6 / JR C -> store.
     * At max: INC E148 + INC E14F; E14F>=5 -> E14F=0 fire_select(E14B).
     * 78cc/78d0/78d4 (i-frames + bfc8) stay at the KIND_CHIP call site. */
    if (s_shot_level < 5)
    {
        s_shot_level++;
        return;
    }
    s_e148++;
    s_e14f++;
    if (s_e14f >= 5)
    {
        s_e14f = 0;
        fire_select(s_fire_num);
    }
}

void player_grant_iframes(void)
{
    /* 78d0 LD (IY+0x1B),0x40 — assign, do not add. 78cc SET 7,(IY+0x05)
     * is the type60 86a4 cancel latch: player_hit() no-ops while set.
     * 44ea still CP 0x81, so collide_player must not skip 44B0/453E. */
    s_invuln = PLAYER_IFRAMES;
    s_if_latch = 1;
}

void player_fireup_latch(void)
{
    /* 8e92 SUB A / LD (IY+0x1B),A — assign 0, not 0x40.
     * 8e9f SET 7,(IY+0x05) — 86a4 cancel. Next 7710 DEC wraps 0→255. */
    s_invuln = 0;
    s_if_latch = 1;
}

void player_grant_life(void)
{
    /* type62 clear 875a: INC E10A, ev8, update_status_bar. No E102 bit2 mute. */
    s_lives++;
    sound_play_event(SND_EV_EXTRA);
}

u8 player_score_lo(void)
{
    /* E103 BCD low byte of 6-digit score. */
    u8 n = (u8)(s_score % 100UL);
    return (u8)(((n / 10u) << 4) | (n % 10u));
}

u8 player_score_mid(void)
{
    /* E104 BCD middle byte. */
    u8 n = (u8)((s_score / 100UL) % 100UL);
    return (u8)(((n / 10u) << 4) | (n % 10u));
}

u8 player_score_hi(void)
{
    /* E105 BCD high byte. */
    u8 n = (u8)((s_score / 10000UL) % 100UL);
    return (u8)(((n / 10u) << 4) | (n % 10u));
}

u8 player_e148(void)
{
    return s_e148;
}

void player_e148_sub5(void)
{
    /* fireup collect 8e95: E148 -= 5 saturating at 0. */
    if (s_e148 >= 5)
        s_e148 = (u8)(s_e148 - 5);
    else
        s_e148 = 0;
}

void player_fire_select(u8 n)
{
    fire_select(n);
}

void player_fire_reset(void)
{
    fire_reset();
}

void player_fire_dec_ammo(void)
{
    /* fire_dec_ammo 0x732A: DEC E14D. Caller decides expiry. */
    s_fire_counter--;
}

u8 player_fire_ammo(void)
{
    return s_fire_counter;
}

u8 player_fire_life_tick(void)
{
    /* 0x730B: DEC E14C; RET NZ; LD 0x3C; DEC E14D; CP 0xFF; RET NZ;
     * POP; JP 0x7544. Only CALLed from live type-3 (728f / 7306 / 73c2). */
    s_fire_timer--;
    if (s_fire_timer)
        return 0;
    s_fire_timer = 0x3C;
    s_fire_counter--;
    if (s_fire_counter != 0xFF)
        return 0;
    fire_reset();
    return 1;
}

void player_e102_set(u8 bits)
{
    s_e102 |= bits;
}

void player_e102_res(u8 bits)
{
    s_e102 = (u8)(s_e102 & (u8)~bits);
}

u8 player_e102(void)
{
    return s_e102;
}

/* BCD 00-99 -> 0-99. Threshold bytes are kept valid BCD. */
static u8 bcd_bin(u8 b)
{
    return (u8)(((b >> 4) * 10) + (b & 0x0F));
}

/* Z80 DAA after ADD. half/carry are the ADD flags. */
static u8 daa_add(u8 res, u8 half, u8 cry, u8 *out_c)
{
    u16 t = res;

    if (half || ((t & 0x0F) > 9))
        t += 0x06;
    if (cry || (t > 0x99))
    {
        t += 0x60;
        *out_c = 1;
    }
    else
        *out_c = 0;
    return (u8)t;
}

/* 0x4A36: first 0x20 -> 0x60, else E112 += 0x60 DAA, E113 ADC 0 DAA. */
static void bump_extra_life_threshold(void)
{
    u16 raw;
    u8 c_add;
    u8 c_daa;
    u8 h;

    if (s_e113 == 0 && s_e112 == 0x20)
    {
        s_e112 = 0x60;
        return;
    }
    raw = (u16)s_e112 + 0x60;
    c_add = (u8)(raw > 0xFF);
    s_e112 = daa_add((u8)raw, 0, c_add, &c_daa);
    raw = (u16)s_e113 + c_daa;
    c_add = (u8)(raw > 0xFF);
    h = (u8)(((s_e113 & 0x0F) + c_daa) > 0x0F);
    s_e113 = daa_add((u8)raw, h, c_add, &c_daa);
    (void)c_daa;
}

/* 0x4A26: 3-byte BCD score >= E111/E112/E113, then 0x4A52 extra life. */
static void extra_life_check(void)
{
    u32 thresh;

    for (;;)
    {
        thresh = (u32)bcd_bin(s_e111)
               + (u32)bcd_bin(s_e112) * 100UL
               + (u32)bcd_bin(s_e113) * 10000UL;
        if (s_score < thresh)
            return;
        bump_extra_life_threshold();
        /* INC E10A; wrap -> DEC and RET (no ev8, no re-loop). */
        s_lives++;
        if (s_lives == 0)
        {
            s_lives = 255;
            return;
        }
        /* ev8 if E102 bit2 clear (0x4A5D). */
        if ((s_e102 & 0x04) == 0)
            sound_play_event(SND_EV_EXTRA);
    }
}

/* 0x49F0: if score >= stored top, arm E114 flash + ev9 (unless already
 * announced or E102 bit2). Does NOT copy E106; that is 0x4ACE. */
static void hiscore_check(void)
{
    if (s_score < s_hiscore)
        return;
    if (s_e114 & 0x40)
        return;
    if (s_e114 & 0x80)
        return;
    s_e114 |= 0x40;
    if ((s_e102 & 0x04) == 0)
        sound_play_event(SND_EV_HISCORE);
}

u32 player_hiscore(void)
{
    return s_hiscore;
}

u32 player_score(void)
{
    return s_score;
}

u32 player_top_display(void)
{
    return (s_score >= s_hiscore) ? s_score : s_hiscore;
}

u8 player_top_flash_blank(void)
{
    return (u8)((s_e114 & 0x40) && ((s_e114 & 0x04) == 0));
}

u8 player_top_flash_active(void)
{
    return (u8)(s_e114 & 0x40);
}

void player_top_flash_tick(void)
{
    if (s_e114 & 0x40)
        s_e114++;
}

void player_save_hiscore(void)
{
    /* compare_save_hiscore 0x4ACE: score >= top -> copy. */
    if (s_score >= s_hiscore)
        s_hiscore = s_score;
}

void player_add_score(u8 award_idx)
{
    if (award_idx > 20)
        award_idx = 20;
    s_score += k_award[award_idx];
    if (s_score > 999999UL)
        s_score = 999999UL;
    extra_life_check();
    hiscore_check();
}

void player_update(void)
{
    const ModeAssets *a = mode_assets();
    u16 joy;
    s16 vx;
    s16 vy;
    s16 min_x;
    s16 min_y;
    s16 max_x;
    s16 max_y;
    u8 sel;

    if (s_over)
    {
        if (s_over_timer)
            s_over_timer--;
        return;
    }

    if (s_dead)
    {
        /* Type60 clear -> E102 bit0. player_hit_handler 0x4649: RES0, DEC
         * E10A; NZ -> SET6 + status; Z -> SET1 game_over. */
        if (s_e102 & 0x01)
        {
            s_e102 = (u8)(s_e102 & (u8)~0x01);
            if (s_lives)
                s_lives--;
            if (!s_lives)
            {
                s_over = 1;
                s_over_timer = PLAYER_OVER_WAIT;
                s_e102 = (u8)(s_e102 | 0x80);   /* game_over_handler SET 7 */
                player_save_hiscore();          /* 0x4672 compare_save_hiscore */
            }
            else
            {
                s_e102 = (u8)(s_e102 | 0x40);   /* respawn wait bit6 */
                s_dead_timer = PLAYER_DEATH_WAIT;
            }
        }
        if (s_over)
            return;
        if (s_dead_timer)
            s_dead_timer--;
        /* Main loop bit6: 64f scroll then LAB_4068 reinit ship. */
        if (!s_dead_timer && s_lives && (s_e102 & 0x40))
        {
            s_e102 = (u8)(s_e102 & (u8)~0x40);
            respawn();
        }
        return;
    }

    joy = JOY_readJoypad(JOY_1);

    /* E10C from joystick bits (keyboard-input.md): base 4,
     * UP +1, DOWN -1, LEFT -3, RIGHT +3. xvel_table[4/5] = dir 12 = forward. */
    {
        s16 s = 4;
        if (joy & BUTTON_UP)    s += 1;
        if (joy & BUTTON_DOWN)  s -= 1;
        if (joy & BUTTON_LEFT)  s -= 3;
        if (joy & BUTTON_RIGHT) s += 3;
        if (s < 0) s = 0;
        if (s > 8) s = 8;
        sel = (u8)s;
    }
    s_xvel_sel = sel;

    /* MSX player_ship_update 0x7612: X clamp 0x28..0xC8, Y 0x1E..0xB8.
     * Those are SAT coordinates. Original EC draw keeps the sprite in 0-191. */
    if (mode_get() == MODE_ORIGINAL)
    {
        min_x = MODE_SHIP_MIN_X;
        min_y = 0x1E;
        max_x = MODE_SHIP_MAX_X;
        max_y = 0xB8;
    }
    else
    {
        min_x = 0;
        min_y = 0;
        max_x = (s16)(a->playfield_w - SHIP_W);
        max_y = (s16)(a->playfield_h - SHIP_H);
    }

    /* 0x7618: E10C == 4 is "nothing held", which skips the move entirely.
     * Otherwise xvel_table picks a 16-dir unit vector and set_velocity_from_dir
     * scales it by the ship speed byte, so diagonals are not faster. */
    if (sel != 4)
    {
        u8 dir = vel_sel_dir[sel];

        vy = (s16)(vel_dir_y[dir] * SHIP_SPEED_BYTE);
        vx = (s16)(vel_dir_x[dir] * SHIP_SPEED_BYTE);
    }
    else
    {
        vy = 0;
        vx = 0;
    }

    s_y = step_axis(s_y, &s_yfrac, vy, min_y, max_y);
    s_x = step_axis(s_x, &s_xfrac, vx, min_x, max_x);

    /* E13F ++ every frame, reset on shot. Fire rate is E110 = 20 frames. */
    if (s_alc_cadence < 255)
        s_alc_cadence++;

    /* A/C = SPACE: MSX E100 bit4 clear = fire held (active-low joystick).
     * 767e: fire NOT held -> force E110=1 and skip ALC/shot (76e9).
     * Held: DEC E110; on 0 reload 0x14, run 76a7/76b0/76bc, try spawn.
     * Release->repress fires next frame so E13F can index shot_rate_table. */
    if (joy & (BUTTON_A | BUTTON_C))
    {
        if (s_shot_cd)
            s_shot_cd--;
        if (!s_shot_cd)
        {
            entity_on_shot_fired(s_alc_cadence);
            s_shot_cd = SHOT_PERIOD;
            s_alc_cadence = 0;
            if (entity_spawn_shot(s_x, s_y))
                sound_play_shot();
        }
    }
    else
        s_shot_cd = 1;      /* 7682-7684: LD (E110),1 while fire released */

    /* bit5 held AND E380==0 -> spawn type 3. Fire 2 is also forced live on select. */
    if ((joy & (BUTTON_A | BUTTON_C)) || s_fire_num == 2)
        entity_try_spawn_fire(s_x, s_y, s_xvel_sel);

    /* 7710: BIT 7 +05; XOR +04 0x0E; DEC +1B; Z → RES 7 + restore 0x8F.
     * Fire-up 8e92 +1B=0 + 8e9f SET 7: DEC wraps 0→255 (256-frame blink). */
    if (s_if_latch || s_invuln)
    {
        s_invuln--;
        /* MSX XOR sat_color 0x0E (0x8F <-> 0x81) each frame of the count.
         * Both values keep TMS EC bit7, so draw X stays SAT-32. */
        s_sat_col = (u8)(s_sat_col ^ 0x0E);
        show_ship((s_invuln & 2) == 0);
        if (!s_invuln)
        {
            s_if_latch = 0;
            s_sat_col = 0x8F;
            show_ship(1);
        }
    }
    else if (s_spr)
        show_ship(1);
}

void player_draw_hud(void)
{
    if (mode_get() == MODE_ORIGINAL)
    {
        hud_draw_player();
        return;
    }

    {
        char buf[24];
        u8 i = 0;
        u32 n;
        u8 d;

        buf[i++] = 'L';
        buf[i++] = (char)('0' + (s_lives % 10));
        buf[i++] = ' ';
        buf[i++] = 'S';
        buf[i++] = (char)('0' + (s_shot_level % 10));
        buf[i++] = ' ';
        buf[i++] = 'F';
        buf[i++] = (char)('0' + (s_fire_num % 10));
        buf[i++] = ' ';
        n = s_score;
        for (d = 0; d < 6; d++)
        {
            u32 div = 1;
            u8 k;
            for (k = 0; k < (u8)(5 - d); k++)
                div *= 10;
            buf[i++] = (char)('0' + (u8)((n / div) % 10));
        }
        buf[i] = 0;

        VDP_setTextPalette(PAL0);
        VDP_drawText(buf, 1, 25);
    }
}

void player_draw_over(void)
{
    /* game_over_handler 0x468A: " GAME OVER " (lead+trail space) at
     * nametable 0x3987 (row 12 col 7), charset tiles via 0x5C25. */
    if (mode_get() == MODE_ORIGINAL)
    {
                hud_draw_str(BG_A, 7, mode_text_row(12), " GAME OVER ");
        return;
    }

    {
        const ModeAssets *a = mode_assets();
        u16 cols = a->screen_width / 8;
        u16 x = (cols > 9) ? (u16)((cols - 9) / 2) : 0;

        VDP_setTextPalette(PAL1);
        VDP_drawText("GAME OVER", x, mode_text_row(12));
    }
}

void player_release(void)
{
    if (s_cspr)
    {
        SPR_releaseSprite(s_cspr);
        s_cspr = NULL;
    }
    if (s_spr)
    {
        SPR_releaseSprite(s_spr);
        s_spr = NULL;
    }
}
