#ifndef ENTITY_H
#define ENTITY_H

#include <genesis.h>

#define SHOT_SLOTS      4
#define ENEMY_SLOTS     24
#define SHOT_PERIOD     20  /* E110 reload 0x14 frames */

void entity_init(void);
void entity_update(void);
void entity_release(void);

/* Map-script cmd 0: store E12D. Bit1 = spawn stream active. */
void entity_on_spawn_ctrl(u8 ctrl);
/* Map-script cmd C: signed spawn-pace nudge into E132/E12E (ALC family 2). */
void entity_on_spawn_pace(s8 nudge);
/* First boot / warp / credits: zero E12E/E12F/E131/E132.
 * Cmd 9 (0x96E2 JP 0x9433) does not wipe them.
 * Do not bake LAB_414d's E132+=0x20 in here — first boot never enters 40DA. */
void entity_alc_reset(void);
/* reset_entities 0x40D6: zero E132 only. Dest-0 40E2 uses this before 414d. */
void entity_alc_zero_e132(void);
/* LAB_414d after reset_entities: E132 += 0x20, sat 0xFF.
 * Warp / award 0x0F / LAB_92af SET 5, not title script_boot. */
void entity_alc_complete(void);

/* Per fire-tick ALC family 1: E13F cadence -> E12F/E131/E141 (76a7/76b0/76bc).
 * Runs when E110 expires even if shot pool full; E140 is spawn-only (76e5). */
void entity_on_shot_fired(u8 cadence);

/* Spawn a type-2 player shot at MD top-left. Returns FALSE if pool full. */
bool entity_spawn_shot(s16 x, s16 y);
/* Type-3 fire-weapon (E380). No-op if live. Fire 6 is SAT 0x10 + 4898. */
void entity_try_spawn_fire(s16 x, s16 y, u8 xvel_sel);
void entity_kill_fire(void);
/* fire_select A==2: 97bc type 69 from fire2_special_table 0x752F. */
void entity_fire2_special(void);
/* Type60 player death FX at (x,y); SRL E132/E12E; clear -> E102 bit0. */
void entity_spawn_pdeath(s16 x, s16 y);
/* SUB_ram_8bca: n type-23 at (x,y). B=xmask C=ymask; offset (R&mask)-(mask>>1). */
void entity_scatter_8bca(s16 x, s16 y, u8 xmask, u8 ymask, u8 n);

u8   entity_shot_count(void);
u8   entity_enemy_count(void);

/* check_col_clear 0x9B22: 1 = ok to place (NC), 0 = occupancy conflict (CF). */
u8   entity_check_col_clear(void);
/* Cmd 1 / place_tile_group: stamp a ground structure (44/69/70/71/82).
 * dest = idol-table word (warp ptr) or fire# for type 82.
 * Returns 1 if a slot was claimed. */
u8   entity_place_ground(u8 type, s16 x, s16 y, u16 dest);
void entity_clear_enemies(void);
/* place_tile_group ctrl bit7: reset E780/E151 then collect placed bodies. */
void entity_attack_list_begin(void);
/* place_tile_group ctrl bit7: add N base segments to the live count. */
void entity_base_open(u8 n);
/* 8f5e stop: E150 := 2 (bit1 hold + arm fire). SET 7 in base_step.
 * 8fde: rebind 0x93AB patterns onto E780 bodies (+0F/+10), clear +0E. */
void entity_base_arm(void);
void entity_base_or_flags(u8 bits);
void entity_base_set(u8 v);
/* E150: bit0 approach, bit1 hold/fire, bit2 timeout, bit3 rage. */
u8   entity_base_flags(void);
/* 90a6 explode_enemies: types < 0x46 become explosions (keep 70+). */
void entity_explode_airborne(void);
/* 90a6 prefix: E12E -= E12E/4, E132 -= 8 sat 0 (BE27 via sticky bit0). */
void entity_alc_ease(void);
/* 90a6: extra E12E-- if nonzero + SET 0,E12D (sticky BE27). */
void entity_dec_encounter_a(void);
/* 9329 timeout: DEC E130 if nonzero. */
void entity_dec_encounter_b(void);
/* 932c: E12E += 0x10 then sticky bit0 (inc_a gated by E150 bit1). */
void entity_timeout_alc(void);
/* 90a6: RES 3,E12D (stream-block) immediately before E150=0. */
void entity_spawn_res3(void);
/* 90dc: variant&0x7F in {82,84,85,86} -> type 80, +0x18=0; 8e14 next. */
void entity_convert_clear_types(void);
/* 90c2 / 0x76b5: SUB_bfc8. E130++ unless E150 bit1 (HUD-only at clear). */
void entity_inc_encounter_b(void);
u8   entity_e12e(void);
u8   entity_e132(void);
u8   entity_e130(void);
/* player_ship_handler 0x7606: zero E130 on every ship spawn (incl. respawn). */
void entity_zero_e130(void);

#endif
