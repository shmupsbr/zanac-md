#ifndef PLAYER_H
#define PLAYER_H

#include <genesis.h>

#define SHIP_W              16
#define SHIP_H              16
#define PLAYER_LIVES_INIT   3     /* title_screen_init: (IX+0x0A)=3 at E10A */
#define PLAYER_IFRAMES      64    /* ship spawn blink IX+0x1B = 0x40 */
#define PLAYER_DEATH_WAIT   64    /* main-loop respawn wait */
#define PLAYER_OVER_WAIT    0x320 /* game_over_handler 0x469F BC=0x320 */

void player_init(void);
void player_update(void);
void player_release(void);
void player_draw_hud(void);
void player_draw_over(void);

s16  player_x(void);
s16  player_y(void);
u8   player_lives(void);
u8   player_shot_level(void);
u8   player_fire_num(void);
/* fire_init_table 0x751F byte 1 → E14E. 44D4 AND 1 / 44F9 BIT 1. */
u8   player_fire_mode(void);
u8   player_invincible(void);
u8   player_dead(void);
u8   player_is_over(void);
u8   player_over_ready(void);

void player_hit(void);
void player_add_shot_level(void);
/* handler_type63 78d0: LD (IY+0x1B),0x40. Type 60 86a4 cancels death
 * while +05 bit7 is set; player_ship_update 771f DECs the timer. */
void player_grant_iframes(void);
/* Type 83 8e92 +1B=0 + 8e9f SET 7 +05. Next 7710 DEC wraps 0→255. */
void player_fireup_latch(void);
/* Type62 clear 875a: INC E10A + ev8 + status (no E102 mute). */
void player_grant_life(void);
/* E103 BCD score_lo for type61 gate (alc_shots&0x3F). */
u8   player_score_lo(void);
/* E104 / E105 BCD bytes (proto_box 77ea / 7808 index). */
u8   player_score_mid(void);
u8   player_score_hi(void);
/* E148 chip-overflow counter (type61 -> fire83 if >=5). */
u8   player_e148(void);
void player_e148_sub5(void);
void player_fire_select(u8 n);
/* fire_reset 0x7544: E14F=0 then fire_select(0). Not 7548. */
void player_fire_reset(void);
void player_fire_dec_ammo(void);
u8   player_fire_ammo(void);
/* fire_life_timer 0x730B. 1 if E14D underflow -> fire_reset. */
u8   player_fire_life_tick(void);
void player_skip_over(void);
void player_add_score(u8 award_idx);
/* 0x9302 / 0x91C1 boss-base clear: skill scale then extend bonus. */
void player_add_clear_bonus(u8 award_idx);
/* score_award_table 0x4AEA decoded. 0x49B5 prints this then a trailing 0. */
u32  player_award_points(u8 idx);
/* Clear bonus after skill + extend (placar / BONUS banner). */
u32  player_clear_bonus_points(u8 idx);
/* E106-E108 top score. Persists across title_screen_init. */
u32  player_hiscore(void);
u32  player_score(void);
u32  player_top_display(void);
u8   player_top_flash_blank(void);
u8   player_top_flash_active(void);
void player_top_flash_tick(void);
/* compare_save_hiscore 0x4ACE: copy score if >= top. Game-over / credits. */
void player_save_hiscore(void);
/* E102: bit2 mutes ev8/ev9; bit7 skips fade/4163 (attract). */
void player_e102_set(u8 bits);
void player_e102_res(u8 bits);
u8   player_e102(void);

#endif
