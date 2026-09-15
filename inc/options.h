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

u8   options_skill(void);
u8   options_autofire(void);
u8   options_player_ships(void);
u8   options_bind(u8 btn);

void options_nudge_skill(s8 dir);
void options_nudge_autofire(s8 dir);
void options_nudge_ships(s8 dir);
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

/* Physical A/B/C → fire roles. Defaults: A both, B primary, C secondary. */
u16  options_primary_buttons(void);
u16  options_secondary_buttons(void);

#endif
