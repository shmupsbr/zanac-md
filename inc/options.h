#ifndef OPTIONS_H
#define OPTIONS_H

#include <genesis.h>

/*
 * Session options (RAM only). Defaults match current 1:1 play:
 * Normal skill, Normal autofire (SHOT_PERIOD), 3 lives, A/B/C fire split.
 *
 * ALC_HALF_RANK 0x50 is 50% of max ALC: alc_recompute clamps the
 * E12E+E132 rank at 0xA0 → 0x9F, so half of that 0xA0 threshold is
 * 0x50 (~half of the 0x9F range). Easy caps effective rank here.
 * Hard seeds E12E to this value on alc_reset so the first spawn table
 * is ~half rank; later inc/ease paths are free to move it. Normal
 * starts at 0 and has no cap.
 */
#define ALC_HALF_RANK           0x50

#define SKILL_EASY              0
#define SKILL_NORMAL            1
#define SKILL_HARD              2

#define AUTOFIRE_NORMAL         0
#define AUTOFIRE_X2             1
#define AUTOFIRE_X3             2
#define AUTOFIRE_X4             3
#define AUTOFIRE_X5             4

#define FIRE_ROLE_BOTH          0   /* primary + secondary / ammo */
#define FIRE_ROLE_PRIMARY       1
#define FIRE_ROLE_SECONDARY     2

#define OPTIONS_BTN_A           0
#define OPTIONS_BTN_B           1
#define OPTIONS_BTN_C           2

#define OPTIONS_SHIPS_MIN       1
#define OPTIONS_SHIPS_MAX       5

/*
 * PLAYER EXTEND. First stock threshold is title_screen_init
 * E111=0, E112=0x20, E113=0 → 2000 in E103-E105 units. HUD 0x49B5
 * prints those 6 digits plus a trailing 0, so the placar reads 20000.
 * Call that displayed first extra  X. Modes control extra_life_check
 * (when / how often lives are granted). The % is a score bonus on
 * every placar add — compensation for a harder extend schedule, not
 * a substitute for the life rules. ONCE > TWICE at each tier.
 * NO EXTENDS is +100% plus EXTEND_NONE_START at player_init
 * (50000 internal → 500000 on the HUD trailing-0 placar).
 * Default EVERY X = stock lives + 0%.
 */
#define EXTEND_X_POINTS         2000UL
#define EXTEND_X_DISPLAY        20000UL
/* NO EXTENDS: +100% on every placar add, plus this flat grant at
 * player_init / game start (not doubled by the %). Same units as
 * EXTEND_X_POINTS / extra_life_check: HUD 0x49B5 appends a trailing
 * 0, so 50000 internal reads as 500000 on the placar. */
#define EXTEND_NONE_START         50000UL
#define EXTEND_NONE_START_DISPLAY 500000UL

#define EXTEND_EVERY_X          0
#define EXTEND_EVERY_2X         1
#define EXTEND_EVERY_3X         2
#define EXTEND_X_ONCE           3
#define EXTEND_X_TWICE          4
#define EXTEND_2X_ONCE          5
#define EXTEND_2X_TWICE         6
#define EXTEND_3X_ONCE          7
#define EXTEND_3X_TWICE         8
#define EXTEND_NONE             9
#define EXTEND_MODE_MAX         EXTEND_NONE

/*
 * BULLET VISIBILITY. Zero relationship with SKILL LEVEL / ALC.
 * Easy / Normal / Hard must never change bolinha colour. The only
 * switch is this option, for every enemy and every boss, whole game:
 *   NORMAL (default) = Japan white (0x8F / nibble 15), no 8659.
 *   HIGH = #136 PAL2[4] 8659 colour-walk on the same shots.
 * Scope: FRAME_LEAD 20/37/38/41/42/43, FRAME_LIGHT_BAR 21, type 45
 * bar/med, k_gun 48/49/52-55, box-4 3x38 volleys, edge spawners,
 * type-73..79 base_fire. SGDK-packed FRAME_LEAD nibble 4 must not
 * sit on PAL2[4] when NORMAL.
 */
#define BULLET_VIS_NORMAL       0
#define BULLET_VIS_HIGH         1

u8   options_skill(void);
u8   options_autofire(void);
u8   options_player_ships(void);
u8   options_extend(void);
u8   options_bullet_vis(void);
u8   options_bullet_high(void);
u8   options_bind(u8 btn);

void options_nudge_skill(s8 dir);
void options_nudge_autofire(s8 dir);
void options_nudge_ships(s8 dir);
void options_nudge_extend(s8 dir);
void options_nudge_bullet_vis(s8 dir);
void options_cycle_bind(u8 btn, s8 dir);

/* Easy: cap effective pos at ALC_HALF_RANK. Hard/Normal: unchanged. */
u16  options_alc_effective(u16 pos);
/* Hard: 0x50. Easy/Normal: 0 (title_screen_init / 40DA zero). */
u8   options_alc_start_e12e(void);

/* Primary reload. Normal = SHOT_PERIOD (0x14). x2=10 x3=7 x4=5 x5=4. */
u8   options_shot_period(void);

/* Scale armed boss TIME (E155 BCD minutes). Easy ×1.5, Hard ×0.5
 * (min 1 if the script value was non-zero). Normal unchanged. */
u8   options_scale_time(u8 e155);

/* Boss/base clear / TIME-window 0x9302 awards only (not per-kill 4a6a).
 * Easy 50% of Normal, Hard +100% (double). Normal unchanged. */
u32  options_scale_clear_bonus(u32 pts);

/* PLAYER EXTEND score bonus, applied to every placar add. */
u8   options_extend_bonus_pct(void);
u32  options_apply_score_bonus(u32 pts);

/* 1 if this mode still uses stock E111-E113 bump after a grant. */
u8   options_extend_uses_stock_bump(void);
/* Next extra-life score (E103 units), or 0 if no further extends.
 * stock_thresh is the current E111-E113 decode; grants is how many
 * finite-mode lives this run already awarded. */
u32  options_extend_threshold(u32 stock_thresh, u8 grants);

/* Physical A/B/C → fire roles. Defaults: A both, B primary, C secondary. */
u16  options_primary_buttons(void);
u16  options_secondary_buttons(void);

#endif
