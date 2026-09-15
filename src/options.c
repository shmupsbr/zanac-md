#include "options.h"
#include "player.h"
#include "entity.h"

/* Session RAM. Not wiped on title return; no SRAM. */
static u8 s_skill = SKILL_NORMAL;
static u8 s_autofire = AUTOFIRE_NORMAL;
static u8 s_ships = PLAYER_LIVES_INIT;
static u8 s_extend = EXTEND_EVERY_X;
static u8 s_bind[3] = {
    FIRE_ROLE_BOTH,
    FIRE_ROLE_PRIMARY,
    FIRE_ROLE_SECONDARY
};

/* Filipe: fewer/harder extends => higher score bonus. */
static const u8 k_extend_bonus[10] = {
    0,   /* EVERY X, stock */
    20,  /* EVERY two-X */
    30,  /* EVERY three-X */
    60,  /* X once (harder than twice) */
    50,  /* X twice */
    80,  /* two-X once */
    70,  /* two-X twice */
    100, /* three-X once */
    90,  /* three-X twice */
    100  /* none; plus 50000 internal (500000 HUD) at player_init */
};

static const u16 k_pad[3] = { BUTTON_A, BUTTON_B, BUTTON_C };

/* Normal = SHOT_PERIOD 0x14 (20 frames @60Hz ≈ 3 shots/sec). */
static const u8 k_shot_period[5] = {
    SHOT_PERIOD,            /* Normal */
    SHOT_PERIOD / 2,        /* x2 → 10 */
    (SHOT_PERIOD + 2) / 3,  /* x3 → 7 (20/3) */
    SHOT_PERIOD / 4,        /* x4 → 5 */
    4                       /* x5 */
};

static u8 wrap_u8(s16 v, u8 lo, u8 hi)
{
    if (v < (s16)lo)
        return hi;
    if (v > (s16)hi)
        return lo;
    return (u8)v;
}

u8 options_skill(void)
{
    return s_skill;
}

u8 options_autofire(void)
{
    return s_autofire;
}

u8 options_player_ships(void)
{
    if (s_ships < OPTIONS_SHIPS_MIN)
        return OPTIONS_SHIPS_MIN;
    if (s_ships > OPTIONS_SHIPS_MAX)
        return OPTIONS_SHIPS_MAX;
    return s_ships;
}

u8 options_extend(void)
{
    if (s_extend > EXTEND_MODE_MAX)
        return EXTEND_EVERY_X;
    return s_extend;
}

u8 options_bind(u8 btn)
{
    if (btn > OPTIONS_BTN_C)
        return FIRE_ROLE_BOTH;
    return s_bind[btn];
}

void options_nudge_skill(s8 dir)
{
    s_skill = wrap_u8((s16)s_skill + dir, SKILL_EASY, SKILL_HARD);
}

void options_nudge_autofire(s8 dir)
{
    s_autofire = wrap_u8((s16)s_autofire + dir, AUTOFIRE_NORMAL, AUTOFIRE_X5);
}

void options_nudge_ships(s8 dir)
{
    s_ships = wrap_u8((s16)s_ships + dir, OPTIONS_SHIPS_MIN, OPTIONS_SHIPS_MAX);
}

void options_nudge_extend(s8 dir)
{
    s_extend = wrap_u8((s16)s_extend + dir, EXTEND_EVERY_X, EXTEND_NONE);
}

void options_cycle_bind(u8 btn, s8 dir)
{
    u8 next;
    u8 i;

    if (btn > OPTIONS_BTN_C)
        return;
    next = wrap_u8((s16)s_bind[btn] + dir, FIRE_ROLE_BOTH, FIRE_ROLE_SECONDARY);
    for (i = 0; i < 3; i++)
    {
        if (i != btn && s_bind[i] == next)
        {
            s_bind[i] = s_bind[btn];
            break;
        }
    }
    s_bind[btn] = next;
}

u16 options_alc_effective(u16 pos)
{
    /* Easy only: never exceed 50% rank. Hard is a start seed, not a floor. */
    if (s_skill == SKILL_EASY && pos > ALC_HALF_RANK)
        return ALC_HALF_RANK;
    return pos;
}

u8 options_alc_start_e12e(void)
{
    return (s_skill == SKILL_HARD) ? ALC_HALF_RANK : 0;
}

u8 options_shot_period(void)
{
    if (s_autofire > AUTOFIRE_X5)
        return SHOT_PERIOD;
    return k_shot_period[s_autofire];
}

static u8 bcd_to_bin(u8 b)
{
    return (u8)(((b >> 4) * 10) + (b & 0x0F));
}

static u8 bin_to_bcd(u16 n)
{
    if (n > 99)
        n = 99;
    return (u8)(((n / 10) << 4) | (n % 10));
}

u8 options_scale_time(u8 e155)
{
    u16 bin;

    if (s_skill == SKILL_NORMAL)
        return e155;
    if (!e155)
        return 0;
    bin = bcd_to_bin(e155);
    if (s_skill == SKILL_EASY)
    {
        /* ×1.5 via u16 so u8 * 3 cannot wrap. */
        bin = (u16)((bin * 3u) / 2u);
    }
    else
    {
        bin = (u16)(bin / 2u);
        if (!bin)
            bin = 1;
    }
    return bin_to_bcd(bin);
}

u32 options_scale_clear_bonus(u32 pts)
{
    /* 0x9302 / 0x91C1 boss-base clear only. Easy half, Hard double. */
    if (s_skill == SKILL_EASY)
        return pts / 2UL;
    if (s_skill == SKILL_HARD)
        return pts * 2UL;
    return pts;
}

u8 options_extend_bonus_pct(void)
{
    u8 mode = options_extend();

    return k_extend_bonus[mode];
}

u32 options_apply_score_bonus(u32 pts)
{
    u8 pct = options_extend_bonus_pct();

    if (!pct)
        return pts;
    return pts + (pts * (u32)pct) / 100UL;
}

u8 options_extend_uses_stock_bump(void)
{
    u8 mode = options_extend();

    return (u8)(mode == EXTEND_EVERY_X
        || mode == EXTEND_EVERY_2X
        || mode == EXTEND_EVERY_3X);
}

u32 options_extend_threshold(u32 stock_thresh, u8 grants)
{
    u8 mode = options_extend();
    u32 x = EXTEND_X_POINTS;
    u32 span;

    switch (mode)
    {
    case EXTEND_EVERY_X:
        return stock_thresh;
    case EXTEND_EVERY_2X:
        return stock_thresh * 2UL;
    case EXTEND_EVERY_3X:
        return stock_thresh * 3UL;
    case EXTEND_X_ONCE:
        return (grants >= 1) ? 0UL : x;
    case EXTEND_X_TWICE:
        return (grants >= 2) ? 0UL : (x * (u32)(grants + 1));
    case EXTEND_2X_ONCE:
        return (grants >= 1) ? 0UL : (x * 2UL);
    case EXTEND_2X_TWICE:
        span = x * 2UL;
        return (grants >= 2) ? 0UL : (span * (u32)(grants + 1));
    case EXTEND_3X_ONCE:
        return (grants >= 1) ? 0UL : (x * 3UL);
    case EXTEND_3X_TWICE:
        span = x * 3UL;
        return (grants >= 2) ? 0UL : (span * (u32)(grants + 1));
    case EXTEND_NONE:
    default:
        return 0UL;
    }
}

static u16 mask_roles(u8 a, u8 b)
{
    u16 m = 0;
    u8 i;

    for (i = 0; i < 3; i++)
    {
        if (s_bind[i] == a || s_bind[i] == b)
            m |= k_pad[i];
    }
    return m;
}

u16 options_primary_buttons(void)
{
    return mask_roles(FIRE_ROLE_BOTH, FIRE_ROLE_PRIMARY);
}

u16 options_secondary_buttons(void)
{
    return mask_roles(FIRE_ROLE_BOTH, FIRE_ROLE_SECONDARY);
}
