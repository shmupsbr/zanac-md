#include "entity.h"
#include "player.h"
#include "mode.h"
#include "spawn_table.h"
#include "map_script.h"
#include "resources.h"
#include "sound.h"
#include <string.h>

/*
 * Entity slots + spawn ticker.
 *
 * Shots: type 2, Y-only. 7243 CPL E10E -> Yvel high = ~(n) = -(n+1),
 *           +0c=1 then 4898. Port: bind=(u8)~n<<8, step_88_y_4898.
 *           7221 BIT 7: init 7228-7252 RET (no 4898). Next frame JP 4898.
 *           Port spawn is player_update; skip first update_shots step.
 * Fire:  type 3, E380.
 *   0 All-Range  - xvel_table[E10C] dir, 4cf7 speed 0xC2 8.8
 *           (bit6*3 * bit7*4 * count2 = *24 -> 12 px cardinal),
 *           +0c=3 then 72de + 4898. Port: apply_dir_4cf7(..., 0xC2).
 *           Type19 expire 74be entity_clear (not piercing).
 *   1 Straight   - +0c=1 Y-only, Yvel 0xFE00, fire_dec_ammo per spawn,
 *           72ea -> 72de + 4898. Port: bind=0xFE00, step_88_y_4898.
 *           Type19 expire 72ea (update): piercing.
 *   2 Field      - auto (fire_select writes E380=3), Y=player_Y-8, persist hits
 *           74c1: DEC E14D, ammo 0x14 SAT 0x20 (pat 8).
 *           fire_select also 97bc type 69 from 0x752F (E10B*3, +3 if round>=5).
 *   3 Circular   - snowflake/orb, 16-dir orbit, +17=0xC3 4cf7 every frame,
 *           fire_life_timer 0x730B from live type-3 only (73c2).
 *           Port: apply_dir_4cf7(..., 0xC3) into off 8.8.
 *           7396/73be ADD A,H is u8 (seed 0xC000/0xF600); not signed s16.
 *           Type19 expire 735d (update): piercing.
 *   4 Vibrator   - lg_circle, rise + X bang-bang around anchor.
 *           +1b=0x3C at 7435. Type19 expire 74e2 DECs +1b per hit
 *           (not per frame); SAT 0x20 at 0x1E, color 0x81 at 0x0F;
 *           Z -> 7507. ev24 every 74e2 is AY leave-alone (one-shot).
 *   5 Rewinder   - SAT 0x0C, Yvel 8.8 0xFE00 then +4/frame, X=player_X,
 *           Y>=0x10, die if Y > player_Y+0x10, 4898 Y-only. Ammo shots.
 *           Type19 expire 7464 (update): piercing.
 *   6 Plasma     - 73ce SAT 0x10 color 0x8F, Yvel 0xFE00 +0c=1, fire_dec_ammo,
 *           update 7494 -> 4898. Type19 expire 7511 explode+ev19+48d0.
 *           Not an instant no-entity nuke (that was invented).
 *   7 High Speed - comet, fire0_dir_table, +17=0xC3 4cf7
 *           (bit6*3 * bit7*4 * count3 = *36 -> 18 px cardinal),
 *           7253 BIT 7: init 728f XOR update 7306 (each CALL 730B once).
 *           Port: apply_dir_4cf7; spawn-frame skip so 730B is not 2x.
 *           Type19 expire 7306 (update): piercing.
 * Enemies: G group-1 airborne + round-1 pickups that the spawn_table emits
 *   4-6     box     - 7826: DEC +03 SAT countdown (0 wraps 255f) then
 *           reveal SAT 0xD4 color 0x8F HP5 Yvel 8.8 00C0; not vis/hit
 *           until SET 7. 7878 (7904 Z): no 4a6a. type 5 RET (stay 0x23,
 *           849c next tick); type 4 in-place 38 + 2x8ddb; else type 63.
 *           proto_box 77a1: X=(H&3F)+0x38 +0x20/child; types 77ea;
 *           SAT countdown 7808. Port: dest/bind/script/timer 8.8.
 *           784d CALL 4898 +0c=1: unsigned Y>=0xD0 (not playfield max_y).
 *   10      duster  - 7a2a: Yvel 8.8 0300, +0c=0x13 (Y|X|X-homing),
 *           x_accel +16=8 tgt +14 (X<0x88?FF:00), +17=1; random_x 71c5.
 *           Port: dest/bind/script/timer 8.8 (like type20/26); aux=+14 tgt.
 *           4898 u8 wrap-cull Y>=0xD0 / X>=0xD1.
 *   12-15   teruzo  - 7b07: +0c=3 +17=4 set_velocity_from_dir 8.8;
 *           teruzo_motion_tables dir every 8f (+1f). Port: apply_dir_88
 *           speed 4; aux=+18 idx, clock=+1f; dest/bind/script/timer 8.8.
 *           4898 u8 wrap-cull Y>=0xD0 / X>=0xD1.
 *   16-18   luster  - 7beb/7c8a/7cb3: Yvel 8.8 0200; 16 +0c=1 Y-only
 *           sides 40/B0; 17 +0c=0x13 Xvel FC00 X-home accel 40 iters 4
 *           tgt=spawn X sides 30/B0; 18 +0c=0x13 Xvel +/-0300 X-home
 *           accel 0e iters 2 tgt FF/00 sides 60/90 fire +1d=30->37.
 *           Port: dest/bind/script/timer 8.8 u8 wrap; aux=+14; clock=+1d.
 *           16/17->38 (dir +1d) 8ddb parent XY; 18->37 aim.
 *           SAT 0x74 start; 16/17 0x18-band 0x74, 0x10-band 0x78+38;
 *           18 fire 0x74+37, +1d==8 -> 0x78. 4898 Y>=0xD0 / X>=0xD1.
 *   56      sig     - 819d: 71c5 (Y=0, X=0x28..0xC6), E=4, join 81a8
 *           speed 5 set_velocity_from_dir 8.8 +0c=3; SAT 0x70. Dir 4 = down.
 *           4898 u8 wrap-cull Y>=0xD0 / X>=0xD1.
 *   59      sideways 8269: +0x1a&0x0F dir, join 81a8 speed 5
 *           set_velocity_from_dir 8.8 +0c=3; SAT 0x70. From pairdesc 57/58,
 *           stealth 66 (808a x5), swoop28 8ddb C=4. Port: KIND_SIG variant 59
 *           + apply_dir_88(...,5) + 8.8 step (shares 81a8 with type56).
 *           4898 u8 wrap-cull Y>=0xD0 / X>=0xD1.
 *   63      chip    - pickup, raises shot_level. 7882 SAT 0x04 (pat 1),
 *           color 0x8F. 4560 half 3,3 => 10x10 (not SAT 0 / 0x40 14x12).
 *           Collect 78cc/78d0: +05 bit7 + +1B=0x40 (type60 86a4 cancel);
 *           78d4 bfc8. Shot INC is 78d7.
 *           78af CALL 4898 +0c=1: unsigned Y>=0xD0 (box-6 keeps 00C0).
 *   68      proto_box -> 3 boxes (types 4/5/6)
 *   80      husk    - 8e14: bfb3+ev18+849c first frame (84d1 + 4912 + 84bc E124), then 8f45 / clear
 *   83      fire-up - 8e3a: Yvel FFE0 8.8; SAT 0x24/0x81 blank vs 0x04/8eaf[+1c];
 *           4898 +0c=1 unsigned Y>=0xD0; collect: +1B=0 + SET 7 +05
 *           (86a4 cancel; 7710 DEC wraps 0→255), fire_select, bfc8
 *   44      ground  - 82d0: 71c5 (Y=0, X=(H&7F)+(L&1F)+0x28), then
 *           aim_4c91+set_vel 8.8 speed (R&3)+1, +0c=3, 3 hp;
 *           SAT 0x40 plane / col-marker 0x44 plane_compl (cyan 0x83);
 *           spr FRAME_PLANE + FRAME_PLANE_C (type39, unfolded).
 *           82f9 CALL 4898: u8 wrap-cull Y>=0xD0 / X>=0xD1
 *           (not playfield max_y / max_x+16).
 *   64      proto   - 8279: spawn_type_list[E130/2+R&3], write +00, RET.
 *           Table has 0x40 at idx 0/23/51; a 64 result retries next frame.
 *           Port has no type-64 slot, so re-roll until the byte is not 64
 *           (eventual MSX type). Do not invent force-44 on a 64 lookup.
 *   70/71   idol    - nametable totem (no SAT); HP 6; -> type 72 orb + bfc8 + type-81 child
 *           8f25: unsigned Y+=8 per E700.1 until wrap, SET 7, Y+=0x10; then 8f45
 *           Y+=8 per E700.1 until Y>=0xD0.
 *   72      orb     - 8983: Yvel 8.8 0xFFF8 (yel) / 0xFFF0 (blk); +0x1e=4;
 *           70 expires; 71 black warp. 4898 +0c=5 Y_motion: unsigned
 *           Y>=0xD0 clears. Port: bind/timer 8.8; clock=+0x1b;
 *           script=+0x1e; aux=anim. 8a16 SAT 1C/20/24/20 colors 8F/83/8A/8B;
 *           mid 0x83 uploads PAL2[7] cyan (PAL2[3] is dim flyer green).
 *           Pixels: Japan pats 7/8/9 in a 16x16 FRAME_CIRCLE vehicle
 *           (FRAME_LEAD is an 8x8 UL shard). 8a1e same names color 81.
 *           yellow 8a26+ev19 / black map_script_warp
 *   81      husk-src- nametable (no SAT); HP 4; 880d->8824 type-80 husk + 88c2
 *   82      firebox - nametable digit 0x30+fire# (87e2, no SAT); HP 4; 880d->8874 type 83 + 88d8
 *   84-86   wide_var - nametable (no SAT); 8EB7 wave-spawner; HP 4; death 8854 type-80 husk + 88ab tiles
 *   87      wide    - nametable (no SAT); HP 3; 880d->8892 type-80 husk + 88b1
 *   88      wide    - nametable (no SAT); HP 3; 880d->8892 type-80 husk + 88cb
 *   89      wide    - nametable (no SAT); HP 3; 880d->8892 then 8874:
 *           4a6a (k_struct_award[89]=8) + ev18 + R&7 fire-up + 88d8
 *   46-55   gun     - 8094 ground-gun pairs; Y leftover 0 (no +01 write),
 *           X=0x30/0xC0; Yvel 8.8 0150 (bflags Y-only),
 *           fire 38/21 via 816d/8ddb. SAT 0x48 loga_A / fire 0x4c compl;
 *           spawn_col_marker. Port: dest/bind/script/timer 8.8;
 *           aux=ang|side|latch, clock=+0x18 period. Osc bit5 pauses bind=0;
 *           spr FRAME_LOGA + FRAME_LOGA_B (pats 18/20); fire 0x4C/0x54.
 *   61      descender - 8302: X=0x40/0xB0, Y leftover 0 (no +01 write);
 *           Yvel 8.8 0200 (+0c=1), halt Y=0x60
 *           (+1e=0x20, +0c=0), then rise Yvel FC00. 4898 unsigned
 *           Y>=0xD0 clears (rise wrap). Port: dest/bind/script/timer 8.8;
 *           clock=+1e.
 *   65-66   stealth - 7f99 writes X from 807c, never +01: stream leftover
 *           Y=0 (top). 4/7 hp, +17=1 set_vel 8.8 +0c=3; volley 8084/8087/
 *           808a (20/59). +04 sat_col 0x85 (65) / 0x8b (66); SAT 0xCC solid
 *           (no XOR, no vis). +0D/+1D=0x30; type 65 7ff0 +0D=0x20 reload
 *           only (+1D stays 0x30). Port: dest/bind/script/timer; clock=+1d.
 *           4898 u8 wrap-cull Y>=0xD0 / X>=0xD1.
 *   67      med_circle - 839f: writes Y/X, +04=0x86, SAT 0x20 pat 8;
 *           +0c=3 +17=3 HP5; +1b=0x78 +1c=0x1e. 83d8: SAT XOR 0x34/0x0c
 *           (0x20 pat 8 <-> 0x14 pat 5 small star). First +1b Z:
 *           SET +05.0, aim_4c91+set_vel speed 3, +04=0x8d, reload
 *           +1b=0x32+(R&0x1e); +05.1 stops reaim. 83ee idle: JP 48b8
 *           (no 4898). Armed 8424 JP NZ 4898 +0c=3: u8 wrap-cull
 *           Y>=0xD0 / X>=0xD1 (not signed s32 / playfield max_y).
 *           Port: sat_col 0x86, idle XOR not vis; clock=+1b;
 *           aux=phase|mot|stop; step_88_4898;
 *           spr FRAME_MED_CIRCLE / FRAME_SMALL_STAR from SAT.
 *   73-79   base    - nametable-only (sat_col=0 like MSX); HP from base_segment_table
 *           8a5a: until BIT 7, Y+=8 per E700.1, RET until E150.1; then SET 7,
 *           Y+=0x10, table xo/yo, 8948. 8c15 paints live tiles from phase.
 *           Timeout 8afa BIT 2 -> 8f45. Type 79 last hit: 8ba1 SET +05.1,
 *           8bb6 255-frame countdown + scatter, then 8baa. HP 0x32/0x14 stamp 8c80.
 *   7-9     umber   - 791d: X=0x78, Y leftover 0 (top); Yvel 8.8 0300,
 *           +0c=0x09 (Y|Y-homing), +15=0x10 iters +17=1, tgt +13 unset (0).
 *           795d types 7/8: Yvel.hi 0 -> SAT 0xE0/0xE8, 0xFF -> 0xDC/0xE4
 *           (hitbox 0xDC 12x14 vs 0xE0 14x16). Type 9 active is 7a12, no morph.
 *           Burst at Yvel==0: 7x38 / 2x41 at parent XY (7 writes IX+01/+02;
 *           8 copies both; 9 8ddb type20); type9 +1d=8 -> type20.
 *           79ae CALL 4898 +0c=0x09: unsigned Y>=0xD0 (rise wrap
 *           0+0xFD00 -> 0xFD), not signed s32 / playfield max_y.
 *           Port: dest/bind/script/timer 8.8; clock=+1d. Stream Y=0.
 *   11/69   spawner - 7ad4 writes type 0x45 SAT 0x28 (interval) then
 *           7a67; 97bc LDIR emit/count/interval into +01/+02/+03.
 *           +04 never written (color 0 = TMS invisible). No FRAME_FIRE.
 *           Drift on fire +/-2 bounce u8 X>=0xC0, 8ddb C=3/5, E12D.bit3.
 *   22-25   veybar  - 7d0f/7db4: Yvel 8.8 0400, +15=0x14 iters 1, tgt 0;
 *           shared active 7d4c: morph fire @clock 0x20 -> type37 (7d8c)
 *           via 8ddb parent XY (no +4/+8). 22/23 +0c=0x09 (Xvel armed,
 *           motion off until morph): 7d95 +17=4, 4c91, set_velocity_from_dir,
 *           then +17=1 / +15=0x0c / SET +0c.1 before type37 (parent re-aim;
 *           drops spawn +/-1 Xvel). 24/25 +0c=0x1b X-home accel 0x10 clock
 *           0x58, morph spawns type37 only (no re-aim / X-arm; already on).
 *           Morph SAT telegraph 7d73: when clock<0x40 and (RRCA x2) only
 *           bits 2-3 set, (IX+03)=0x94-E and marker +0x14; fire @0xa0.
 *           7d83 CALL 4898: Y-only until SET +0c.1; 24/25 already X|Y.
 *           Unsigned Y>=0xD0 / X>=0xD1 (when bit1), not signed s32 /
 *           playfield max_y. Port: dest/bind/script/timer 8.8; clock=+1d;
 *           aux=flags(22/23) or X-tgt(24/25); spr FRAME_VEYBAR_0..4 +
 *           FRAME_VEYBAR_C*.
 *   26-29   swooper 7de2/7e78: 8.8 Xvel (FF40/00C0/FE00/0200), Yvel 0280,
 *           +0c=0x0F (Y|X motion|anim|Y_homing), accel +15=07 iters +17=1,
 *           Y tgt +13 unset (0); fire +1e (18/18/04/04)->20; child +1d 37/20/59/41
 *           via 8ddb C=0x04 parent XY (no +4/+8), like luster/veybar.
 *           29->41 C=0x04 heading base+4 may still read offset. Anim table
 *           0x7E68/0x7E70 pats 43-46 (+0d/+0e=4, +0x10=4); 71f6 marker
 *           SAT=parent+0x10 (pats 47-50).
 *           7e55 CALL 4898: unsigned Y>=0xD0 / X>=0xD1 (not signed s32 /
 *           playfield max_y). +04 body: A 0x8E (7e68), B 0x87 (7e70)
 *           via sat_col remap. Port: dest/bind/script/timer 8.8; aux=child,
 *           clock=fire; spr FRAME_SPINNER_0..3 + FRAME_SPINNER_C* (71f6).
 *   30/32   gswoop 7e9c: 8.8 Yvel 0180 (32: FF00 + Y=D0 sense), Xvel 0180
 *           (32 flip 0100); +0c=1 Y then 2 X; pair child type+1 at X=C0
 *           Xvel FE80 (32: FF00). Port: dest/bind/script/timer 8.8; aux=sib,
 *           clock=+0c|sense|lock|xor. +04^=0x06/frame (sat_col); merge
 *           unsigned (pair.X-own.X)<0x0B (7f54 SUB/CP/JR NC, not abs):
 *           +03=0xf4, sib->type40, X+5, +0c=1, SET lock (7f5b-7f78).
 *           7f73 then 7f7b CALL 4898: +0c=1 Y>=0xD0 / +0c=2 X>=0xD1
 *           (not signed s32 / playfield max_x+16). Type30 parent
 *           X=0x30+0x0180 reaches 0xD1 when the pair is gone;
 *           signed s32 kept X=0xD1..0xFF (playfield X>256 does not).
 *   31/33   tracker - 7f84 run (no +01 write): leftover Y=0. Y-then-X
 *           (playerY CP + bit6 CCF); +04^=0x06 @ 7f73; pat 51 sat 0xCC.
 *           Stream ~7f99/807c X+dir, no volley, Y leftover 0 (top).
 *           Also gswoop 30/32 child (own+1) pre-init sat 0xf0 degid_right.
 *           7f7b CALL 4898: +0c=1 Y>=0xD0 / +0c=2 X>=0xD1 (not signed
 *           s32 / playfield max_y). Type32 child Y=0xD0+0xFF00 -> 0xCF
 *           stays live; left-wrap X=0+FE80 -> 0xFE clears.
 *   34      stealth - 7f99 shared 65/66: 807c X, leftover Y=0 (top);
 *           cruise 8.8 speed 1; 3x38 volley; +04 sat_col 0x88; SAT 0xCC solid.
 *           4898 u8 wrap-cull Y>=0xD0 / X>=0xD1.
 *   62      invisible_riser 8709: Yvel 8.8 FF80, every-16f NT poke;
 *           type61 death gate (E140&3F)==(E103&3F) -> 62; else E148>=5
 *           -> 83. Ship touch: INC lives + ev8. 8709 BIT 7: init
 *           870f-8723 SET 7 then 8727 RET (no 8728 poke, no 4898).
 *           8385 writes 0x3E and RETs; next dispatch is that init RET.
 *           Port become_riser is the 8385 write (collide after updates);
 *           skip first riser_step so 8728+4898 start the following frame.
 *           Armed 874a: 4898 +0c=1 unsigned Y>=0xD0 (top wrap).
 *           Port: bind/timer 8.8; clock=+0d.
 *   36      flash   - 8296: Yvel 8.8 0080 (+0c=1), attr XOR 0x0e
 *           each frame, then entity_update + 7904 (HP16). SAT 0x34
 *           pat 13. 4898 Y-only: unsigned Y>=0xD0 (not playfield max_y).
 *           Port: dest/bind/script/timer 8.8; spr FRAME_BOLT;
 *           vis toggle ~ XOR.
 *   57-58   pairdesc- 81d1/8247: 71c5 (Y=0, X=0x28..0xC6), E=4, JP 81ac
 *           (speed 5 dir 4, +0c=3, +1f=0x20) then 8207 ev21 + type 59.
 *           820c 4c91 → E=aim; 8214 DEC E self +1A; 822E INC A child1
 *           +1A; type 58 8244 DEC A child2 +1A. 8269 AND 0x0F speed 5.
 *           SAT 0x6C pat27 (57) / 0x68 pat26 (58); color 0x8F.
 *           Port: apply_dir_88 dir4 spd5; clock=+1f; FRAME_SIG_DOUBLE/TRIPLE.
 *   20      lead_homing 8668: +0c=0x0B Y-home tgt 0xFF accel 0x0C iters 1;
 *           Xvel 8.8: hi=(R&3)-2, lo=L (same prng); dest/script like other leads.
 *           Stream-capable (is_port_type): random_x 71c5 Y=0 + type20_init_vel;
 *           also child of umber-9 / stealth-65.
 *           4898 u8 wrap-cull Y>=0xD0 / X>=0xD1 (no s32 X).
 *   37      lead_bullet 84dd/84e3: +0c=3 +17=3, player_pos_snapshot 4c8b
 *           (= aim_4c91 + set_velocity_from_dir 8.8 speed 3). Plain 37 no XOR.
 *           84f6 SET 7 / 84fa RET (no 4898). Armed 84fb CALL 4898 / 44a6.
 *           Port: dest/bind/script/timer; apply_dir_88; skip first step;
 *           then 4898 u8 Y>=0xD0/X>=0xD1.
 *   42      proto_bullet 85cc: CALL 84e3 (type37 init), type:=0xA5, XOR R into
 *           X/Y vel low (8.8), RET 85ed (no 4898). Next visit is type 0xA5
 *           (37 armed) 84fb. Port keeps variant 42; skip first 4898 then
 *           8.8 step. Type 79 every-4th. 4898 u8 wrap-cull like 37.
 *   43      proto_fragment 85d6: CALL 8507 (type38 init), type:=0xA6, same XOR
 *           then 85ed RET (no 4898). Next visit is type 0xA6 (38 armed) 84fb.
 *           Port keeps variant 43; skip first 4898 then 8.8 step.
 *           Base fire 74/76/77/78 via 8dd9; 74/77 C from +0x13 (vx),
 *           76 DEC+mirror, 79 INC+&3 (ROM cadence). 4898 u8 wrap-cull like 38.
 *   21      light_bar 863b: +0x17=4, dir=+0x1a&0x0F, set_vel 8.8, SFX ev0x16;
 *           SAT 0x18 pat 6. Init writes no +04. 8650 SET 7 / 8656 JP 5189
 *           (no 8659, no 4898). Active 8659: R-nibble|0x80 then 4898 / 44ba
 *           (EC bit7 so mode_draw_x is SAT-32). Port: spr FRAME_LIGHT_BAR;
 *           skip first step; 8659 then 4898 u8 wrap-cull.
 *           Child of guns 46-55 / type 85-86. Not in spawn_type_list 0xBECC;
 *           stream path (is_port_type) uses 71c5 + leftover +0x1a=0.
 *   38      burst_fragment 8507: +0x17=3, dir=+0x1a&0x0F, set_vel 8.8 (42/43 path sans XOR)
 *           8520 SET 7 / 8524 RET (no 4898). Armed JR 84fb. Port: skip first
 *           step; then 4898 u8 wrap-cull.
 *   41      pair_fragment 852f: child of umber-8 / swoop-29. Not in 0xBECC.
 *           Init 4cf7 speed 2, LDIR +08..+0b -> +1c..+1f, +17=4, RET 857e
 *           (no 857f, no 4898). 857f: heading +/-1 every 2f, 4cf7 speed 4,
 *           ADD HL bias, 4898. Port: clock=+0x1a; skip first step so +15
 *           stays 2; dest/bind = speed4 + speed2 on the armed visit;
 *           step_88_4898 (not s32 / invented cull).
 *           Stream path: 71c5 Y=0 then 852f leftover +0x1a=0 (heading 4).
 *   45      light_bar_var 85ee/8608: 3 HP, speed (R&1)+2 via apply_dir_88,
 *           re-aim every 40f (+0x1a += (R&8)-4); aux packs speed|dir, clock=+0x1c;
 *           8625 SAT +03 = 0x18+((clock&1)<<3) bar/med pulse. Port: FRAME_LIGHT_BAR
 *           <-> FRAME_MED_CIRCLE on clock LSB (hitbox 16x6 <-> 14x14); sat_col 0x8F.
 *           4898 u8 wrap-cull so it cannot re-aim past X=0xD1.
 *           Child of base type 79. Not in spawn_type_list 0xBECC;
 *           stream path (is_port_type) uses 71c5 + leftover +0x1a=0.
 *
 * Round 1's map-script never fires cmd 0; the MSX main loop still
 * runs ground_struct_spawn_ctrl with E12D bit1 set at game start.
 * Stream: update_spawn_table_ptr (BE7C->E133 slice + E135/E136 count +
 * timer) and every-16th slot -> type 61 (BF5D/BF94).
 */

#define FRAME_SHOT      0
#define FRAME_DUSTER    1
#define FRAME_TERUZO    2
#define FRAME_LUSTER    3
#define FRAME_BOX       4
#define FRAME_CHIP      5
#define FRAME_LEAD      6
#define FRAME_SIG       7
#define FRAME_SHOT_D    8
#define FRAME_SHOT_T    9
#define FRAME_FIRE      10  /* pat 3 target */
#define FRAME_CIRCLE    11  /* pat 9 lg_circle */
#define FRAME_COMET     12  /* pat 2 comet */
#define FRAME_DEGID_L   13  /* pat 59 degid_left  SAT 0xec */
#define FRAME_DEGID_R   14  /* pat 60 degid_right SAT 0xf0 */
#define FRAME_DEGID     15  /* pat 61 degid_complete SAT 0xf4 */
#define FRAME_VEYBAR_0  16  /* pat 33 SAT 0x84 */
#define FRAME_VEYBAR_1  17  /* pat 34 SAT 0x88 */
#define FRAME_VEYBAR_2  18  /* pat 35 SAT 0x8c */
#define FRAME_VEYBAR_3  19  /* pat 36 SAT 0x90 */
#define FRAME_VEYBAR_4  20  /* pat 37 SAT 0x94 */
/* type39 col-marker complements (SAT primary+0x14); 71f6 dual-SAT sibling */
#define FRAME_VEYBAR_C0 21  /* pat 38 SAT 0x98 */
#define FRAME_VEYBAR_C1 22  /* pat 39 SAT 0x9c */
#define FRAME_VEYBAR_C2 23  /* pat 40 SAT 0xa0 */
#define FRAME_VEYBAR_C3 24  /* pat 41 SAT 0xa4 */
#define FRAME_VEYBAR_C4 25  /* pat 42 SAT 0xa8 */
#define FRAME_DUSTER_C  26  /* pat 23 */
#define FRAME_TERUZO_C  27  /* pat 25 */
#define FRAME_BOX_C     28  /* pat 54 */
#define FRAME_LUSTER_C  29  /* pat 32 */
#define FRAME_UMBER     30  /* pat 55 */
#define FRAME_UMBER_C   31  /* pat 57 */
#define FRAME_STEALTH   32  /* pat 51 SAT 0xCC */
#define FRAME_STEALTH_C 33  /* pat 52 SAT 0xD0 */
/* edge-swooper 26-29: anim table 0x7E68/0x7E70 pats 43-46; compl sat+0x10 */
#define FRAME_SPINNER_0 34  /* pat 43 SAT 0xAC */
#define FRAME_SPINNER_1 35  /* pat 44 SAT 0xB0 */
#define FRAME_SPINNER_2 36  /* pat 45 SAT 0xB4 */
#define FRAME_SPINNER_3 37  /* pat 46 SAT 0xB8 */
#define FRAME_SPINNER_C0 38 /* pat 47 SAT 0xBC */
#define FRAME_SPINNER_C1 39 /* pat 48 SAT 0xC0 */
#define FRAME_SPINNER_C2 40 /* pat 49 SAT 0xC4 */
#define FRAME_SPINNER_C3 41 /* pat 50 SAT 0xC8 */
#define FRAME_SART      42  /* pat 62 sart SAT 0xF8 */
#define FRAME_SART_C    43  /* pat 63 sart_compl SAT 0xFC */
#define FRAME_LOGA      44  /* pat 18 loga_A SAT 0x48 */
#define FRAME_LOGA_C    45  /* pat 19 SAT 0x4C: Japan 816d uses this as PRIMARY */
#define FRAME_PLANE     46  /* pat 16 plane SAT 0x40 */
#define FRAME_PLANE_C   47  /* pat 17 plane_compl SAT 0x44 */
#define FRAME_BOLT      48  /* pat 13 super_hard_bolt SAT 0x34 */
#define FRAME_LIGHT_BAR 49  /* pat 6 light_bar SAT 0x18 */
#define FRAME_SIG_TRIPLE 50 /* pat 26 sig_triple SAT 0x68 type 58 */
#define FRAME_SIG_DOUBLE 51 /* pat 27 sig_double SAT 0x6C type 57 */
#define FRAME_MED_CIRCLE 52 /* pat 8 medium_circle SAT 0x20 type 67 */
#define FRAME_LUSTER_A   53 /* pat 29 luster_A SAT 0x74 type 18 */
#define FRAME_LUSTER_A_C 54 /* pat 31 luster_A_compl SAT 0x7C */
#define FRAME_UMBER_B    55 /* pat 56 umber_B SAT 0xE0 type 9 */
#define FRAME_UMBER_B_C  56 /* pat 58 umber_B_compl SAT 0xE8 */
#define FRAME_LOGA_B    57  /* pat 20 loga_B SAT 0x50 type39 */
#define FRAME_LOGA_D    58  /* pat 21 loga_B fire SAT 0x54 */
#define FRAME_SNOW      59  /* pat 4 SAT 0x10 fire 3 (7331) */
#define FRAME_SMALL_STAR 60 /* pat 5 SAT 0x14 type 67 83d8 XOR */
#define FRAME_N         61

#define KIND_SHOT       2
#define KIND_FIRE       3
#define KIND_BOX        4
#define KIND_DUSTER     10
#define KIND_TERUZO     12
#define KIND_LUSTER     16
#define KIND_EBULLET    37
#define KIND_SIG        56
#define KIND_CHIP       63
#define KIND_GROUND     44
#define KIND_WIDE       70
#define KIND_ORB        72
#define KIND_FIREBOX    82
#define KIND_FIREUP     83
#define KIND_HUSK       80  /* type 0x50; handler_type80 8e14 */
#define KIND_GUN        46
#define KIND_DESCEND    61
#define KIND_RISER      62  /* type 0x3E; handler_type62 8709 */
#define KIND_STEALTH    65
#define KIND_CIRCLE     67
#define KIND_BASE       73
#define KIND_UMBER      7
#define KIND_SPAWNER    69
#define KIND_VEYBAR     22
#define KIND_SWOOP      26
#define KIND_GSWOOP     30
#define KIND_TRACKER    31  /* type 31/33; handler 7f84 / epilogue 7f73 */
#define KIND_FLASH      36
#define KIND_PAIRDESC   57
#define KIND_EXPL       35  /* type 0x23 explosion (8bc1 / explode_enemies) */
#define KIND_PDEAD      60  /* type 0x3C player death FX 0x869E / 0x86F3 */

typedef struct {
    u8  alive;
    u8  kind;
    u8  variant;
    u8  hp;
    u8  timer;
    u8  script;
    s16 x;
    s16 y;
    s8  vx;
    s8  vy;
    u8  ground;     /* 1 = 8f25/8a5a/8f45 class (Y += 8 per E700.1, not VSCROLL) */
    u8  armed;      /* 8f25/8a5a BIT 7: hittable after init */
    u8  aux;        /* type41: (count<<5)|(sense&0x10)|(heading&15)
                     * type45: (speed<<4)|(dir&15); swoop 26-29: child type +0x1d
                     * gswoop 30/32: paired sibling slot index (0xFF=none)
                     * tracker 31/33: paired parent slot (0xFF=stream spawn)
                     * gun 46-55: ang(low4)|side(0x10)|latch(0x40)
                     * teruzo 12-15: +0x18 script index; off 8.8 fracs
                     * type67: +0x1c phase(low5)|mot 0x40|stop 0x80
                     * type36: SAT attr (XOR 0x0e); 8.8 uses dest/bind/script/timer */
    u8  clock;      /* type41: +0x1a spawn dir (bias heading); type45: re-aim +0x1c (0x28); base: 8fde +0x1c idx; swoop: fire +0x1e;
                     * gswoop/tracker: +0c (1/2) | bit2 xor-phase | bit6 sense | bit7 lock;
                     * gun 46-55: fire countdown +0x18; teruzo +0x1f;
                     * pairdesc 57/58: +0x1f descend; descender 61: +0x1e;
                     * type67: +0x1b reaim (0x78 then 0x32+(R&0x1e));
                     * stealth 34/65/66: +0x1d volley period; off 8.8 fracs;
                     * box 4/5/6: 0=782c SAT countdown (hidden), 1=revealed */
    u8  sat;        /* MSX SAT_NAME (+0x03); indexes collision_size_table */
    u8  sat_col;    /* MSX SAT_COLOR (+0x04); TMS ink = low nibble */
    u8  frame;      /* current spr_objs frame (for sat_col remap) */
    u8  vram_fr;    /* last DMA'd frame; 0xFF = none */
    u8  vram_nib;   /* last DMA'd color nibble; 0xFF = none */
    u8  mvram_fr;   /* last DMA'd complement frame; 0xFF = none */
    u16 dest;       /* idol warp ptr or fire# */
    u16 bind;       /* 8.8 Yvel, or 8948 SAT (X<<8 | Y) after +0x10 pre xo/yo */
    Sprite *spr;
    Sprite *mspr;   /* type39 complement SAT (71f6); NULL if occupancy-only */
    u8  marker;     /* type39 sibling count (71da); 0x27 occupancy */
    u8  mframe;     /* FRAME_* for mspr; 0 if occupancy-only / none */
} Slot;

static Slot s_shot[SHOT_SLOTS];
static Slot s_fire;
/* 7253 BIT 7: 728F init XOR 7306 update. Set when spawn already ran 730B. */
static u8  s_fire7_life_ticked;
static u8  s_fire7_cram;        /* PAL2[13] borrowed for 72de cycle */
static u8  s_fire7_col;         /* 72de SAT colour; INC then AND 0x8F */
/* 7221 BIT 7: init RET, no 4898. Set when entity_spawn_shot already ran
 * 7228-724e this frame (player_update then entity_update). */
static u8  s_shot_init_ret[SHOT_SLOTS];
static Slot s_en[ENEMY_SLOTS];
/* 8709 BIT 7: init 870f-8727 RET, no 8728 / 4898. Armed after
 * become_riser (8385 type 0x3E write). Next riser_step is 8728. */
static u8  s_riser_init_ret[ENEMY_SLOTS];
/* 84fa/8524/857e/8656: types 37/38/41/21 init SET 7 then RET
 * (21: JP 5189). No 4898 / 8659 / 857f on that visit. Armed in
 * init_frag (8ddb / stream / box drop). Next step is the armed path. */
static u8  s_ebullet_init_ret[ENEMY_SLOTS];
/* explode_enemies 0x8A26 wait_frames B=5 with R7 BD=15. */
static u8  s_flash_left;

static u8  s_spawn_ctrl;
static u8  s_spawn_timer;
static u8  s_spawn_reload;
static u8  s_spawn_base;      /* E133 slice offset into spawn_type_list */
static u8  s_e135;            /* spawn_subtable_ctr */
static u8  s_e136;            /* spawn_subtable_max (count) */
static u8  s_stream_slot;     /* E126 stream_slot_ctr; every-16th -> type 61 */
static u8  s_e124;            /* type35 burst counter; title init = 6 */
static u8  s_e125;            /* bit0 -> BFA0 immediate type 44 */
static u16 s_rng;
static u8  s_fireup_seq;

/* ALC accumulators: E12E/E12F spawn_pos, E131 level_seg, E132 cmd-12 bias. */
static u8  s_spawn_pos_hi;
static u8  s_spawn_pos_lo;
static u8  s_e130;          /* SUB_bfc8 encounter B / disp_c */
static u8  s_e131;
static u8  s_e132;
static u8  s_e141;          /* 76bc shot counter; cleared on type35 init */
static u8  s_e142;          /* 8457 rate-table index; cleared on type35 init */
static u8  s_alc_shots;     /* E140: INC wrap on successful shot spawn (76e8) */
static u8  s_alc_events;

/* shot_power_table 0x778F: E10E vy, E10D cap, E10F SAT name.
 * Spawn CPL E10E into Yvel high (level 0: ~4 = 0xFB = -5). */
static const u8 k_shot_power[6][3] = {
    { 4, 2, FRAME_SHOT },
    { 6, 3, FRAME_SHOT },
    { 8, 2, FRAME_SHOT_D },
    { 9, 3, FRAME_SHOT_D },
    { 10, 2, FRAME_SHOT_T },
    { 14, 3, FRAME_SHOT_T },
};

/* shot_rate_table 0x7761: cadence-2 -> spawn-schedule advance.
 * Type35 8457 indexes [E142+1] with E142<0x11, so indices 1..17; bytes
 * 16..17 are the load_shot_params opcodes at 0x7771 (0x21,0x8F). */
static const u8 k_shot_rate[18] = {
    0x20, 0x10, 0x0A, 0x08, 0x06, 0x05, 0x04, 0x04,
    0x03, 0x03, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02,
    0x21, 0x8F
};

/* xvel_table 0x7758: E10C 0-8 -> 16-dir index (fire 0). */
static const u8 k_xvel_dir[9] = {
    0x06, 0x08, 0x0A, 0x04, 0x0C, 0x0C, 0x02, 0x00, 0x0E
};

/* fire2_special_table 0x752F: 3B emit/count/interval. Index = E10B*3,
 * +3 if E701>=5. 97bc writes type 69 then LDIR the 3 bytes. */
static const u8 k_fire2_special[21] = {
    0x38, 0x1E, 0x1E,
    0x42, 0x02, 0x78,
    0x3A, 0x28, 0x3C,
    0x1E, 0x1E, 0x1E,
    0x41, 0x0A, 0xC8,
    0x0A, 0x64, 0x14,
    0x43, 0x0A, 0x50
};

/* fire0_dir_table 0x7321: used by fire 7 (not fire 0). E10C 0-8. */
static const u8 k_fire7_dir[9] = {
    0x0B, 0x0B, 0x0B, 0x0C, 0x0C, 0x0C, 0x0D, 0x0D, 0x0D
};

/* vel_dir_table 0x4D65: two words/dir (mag 128). 4cf7 stores word0 -> IX+08 Yvel,
 * word1 -> IX+0a Xvel, so dir 0 is RIGHT. Arrays keep ROM word order:
 * k_unit_x[] = word0 (Y), k_unit_y[] = word1 (X). Fire 3 reads them that way;
 * apply_dir_88 assigns dest=word1 (X) bind=word0 (Y). */
static const s16 k_unit_x[16] = {
       0,   48,   90,  118,  128,  118,   90,   48,
       0,  -48,  -90, -118, -128, -118,  -90,  -48
};
static const s16 k_unit_y[16] = {
     128,  118,   90,   48,    0,  -48,  -90, -118,
    -128, -118,  -90,  -48,    0,   48,   90,  118
};

/* Fire 3/4/5 8.8 accumulators (single type-3 slot). */
static s16 s_fyoff;
static s16 s_fxoff;
static s16 s_fvy;
static s16 s_fvx;
static s16 s_faccel;
static s16 s_fanchor;
static u8  s_fdir;
static u8  s_fexpire;       /* fire 4: IX+0x1b hits left (7435 / 74e2) */

/* vel_dir_table integer approx (legacy apply_dir); 8.8 uses k_unit_*. */
static const s8 k_dir_vx[16] = {
     0,  1,  1,  2,  2,  2,  1,  1,
     0, -1, -1, -2, -2, -2, -1, -1
};
static const s8 k_dir_vy[16] = {
     2,  2,  1,  1,  0, -1, -1, -2,
    -2, -2, -1, -1,  0,  1,  1,  2
};

/*
 * teruzo_motion_tables 0x7B83/98/AE/CC.
 * Each script is 16-dir indices; bit7 = hold forever.
 */
static const u8 tz_dir0[] = {
    0x08,0x08,0x08,0x08,0x07,0x06,0x05,0x04,
    0x03,0x02,0x01,0x00,0x0F,0x0E,0x0D,0x0C,0x0B,0x8A
};
static const u8 tz_dir1[] = {
    0x00,0x00,0x00,0x00,0x00,0x01,0x02,0x03,
    0x04,0x05,0x06,0x07,0x08,0x09,0x0A,0x0B,0x0C,0x0D,0x8E
};
static const u8 tz_dir2[] = {
    0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,
    0x04,0x02,0x00,0x0E,0x0E,0x0E,0x0E,0x0E,0x0E,0x0E,0x0E,
    0x0D,0x0C,0x0B,0x8A
};
static const u8 tz_dir3[] = {
    0x00,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,
    0x04,0x06,0x08,0x0A,0x0A,0x0A,0x0A,0x0A,0x0A,0x0A,0x0A,
    0x0B,0x0C,0x0D,0x8E
};
static const u8 *const tz_dirs[4] = { tz_dir0, tz_dir1, tz_dir2, tz_dir3 };
static const u8 tz_dir_n[4] = { 18, 19, 27, 27 };
static const s16 tz_yx[4][2] = {
    { 112, 208 }, { 112, 16 }, { 32, 208 }, { 32, 16 }
};
/* Block byte 2: lower 0x8A / upper 0x89. */
static const u8 tz_col[4] = { 0x8A, 0x8A, 0x89, 0x89 };

/* proto_box_type_table 0x77ea: 10 groups of 3 (types 4/5/6). */
static const u8 k_box_types[30] = {
    0x05,0x06,0x05, 0x04,0x05,0x06, 0x05,0x04,0x04, 0x05,0x05,0x05,
    0x04,0x06,0x04, 0x04,0x04,0x04, 0x06,0x05,0x04, 0x04,0x05,0x06,
    0x05,0x04,0x06, 0x04,0x04,0x06
};
/* proto_box_sat_table 0x7808: countdown written to +03 before 782c DEC. */
static const u8 k_box_sat[30] = {
    0x01,0x21,0x01, 0x21,0x01,0x21, 0x01,0x21,0x41, 0x41,0x21,0x01,
    0x11,0x01,0x11, 0x01,0x11,0x01, 0x21,0x01,0x41, 0x41,0x01,0x21,
    0x01,0x11,0x21, 0x21,0x11,0x01
};

/* WINDOW does not occlude MD sprites. Never VISIBLE over cols 24-31
 * (that flicker). Occupancy: draw_x + width > 192, not only draw_x >= 192. */
static s16 slot_draw_y(const Slot *s);
static void marker_place(Slot *s, u16 frame);
static void marker_kill(Slot *s);
static void spr_detach(Slot *s);
static int complement_frame_ok(u16 frame);
static void mspr_upload(Slot *s);
static int step_88_4898(Slot *e);
static int step_88_y_4898(Slot *e);
static void apply_dir_88(Slot *e, u8 dir, u8 speed);
static void apply_dir_4cf7(Slot *e, u8 dir, u8 speed);
static void base_8c15(const Slot *e);
static void flash_begin(void);
static void flash_tick(void);
static void fire4_expire_hit(Slot *f);
static void fire7_cram_restore(void);
static void fire7_bind_cram(Slot *f);
static void fire7_cycle_cram(Slot *f);
static s16 sat_depth_primary(const Slot *s);
static s16 sat_depth_marker(const Slot *s);

/*
 * entity_dispatch 0x445F: SAT ptr E000, walk E300 stride 0x20 (B=0x1A).
 * sprite_sat_write 0x48B8 appends Y-0x11,X,name,color. TMS first SAT
 * index is on top. Slot 0 E300 player, E320+ shots, E380 fire, E3A0+
 * enemies. 71f6 complement appends immediately after its primary.
 * SGDK lower depth = earlier SAT = on top. SPR_MIN_DEPTH is -0x8000;
 * if SPR_update still Y-sorts (AUTO_DEPTH, or unsigned compare of
 * 0x8000 vs draw Y), flyers at Y=50 beat shots at SPR_MIN_DEPTH.
 * Slot depths start at 0 so they stay in front of any leftover Y
 * (16..224) as signed or unsigned. Complement stays primary+1 (71f6).
 * Do not sort by draw Y.
 */
#ifndef SPR_FLAG_AUTO_DEPTH
#define SPR_FLAG_AUTO_DEPTH 0x0200
#endif
/* Slot-walk depths. 0 beats leftover Y in both signed and unsigned sorts. */
#define SAT_DEPTH_PLAYER    0
#define SAT_DEPTH_SHOT      1
#define SAT_DEPTH_FIRE      (SAT_DEPTH_SHOT + SHOT_SLOTS)
#define SAT_DEPTH_ENEMY     (SAT_DEPTH_FIRE + 1)

static void sat_bind_depth(Sprite *sp, s16 depth)
{
    if (!sp)
        return;
    /* SPR_update reapplies Y if this flag stays set. */
    sp->status &= (u16)~SPR_FLAG_AUTO_DEPTH;
    SPR_setDepth(sp, depth);
}

static s16 sat_depth_primary(const Slot *s)
{
    u8 i;

    if (s == &s_fire)
        return SAT_DEPTH_FIRE;
    for (i = 0; i < SHOT_SLOTS; i++)
    {
        if (s == &s_shot[i])
            return (s16)(SAT_DEPTH_SHOT + i);
    }
    for (i = 0; i < ENEMY_SLOTS; i++)
    {
        if (s == &s_en[i])
            return (s16)(SAT_DEPTH_ENEMY + (s16)i * 2);
    }
    return (s16)(SAT_DEPTH_ENEMY + (s16)ENEMY_SLOTS * 2);
}

static s16 sat_depth_marker(const Slot *s)
{
    /* 71f6 writes after the primary SAT; later index is behind. */
    return (s16)(sat_depth_primary(s) + 1);
}

static void spr_vis_playfield(Sprite *sp, s16 dx, s16 dy, int want_vis)
{
    if (!sp)
        return;
    if (mode_get() == MODE_ORIGINAL)
    {
        s16 y0 = (s16)mode_y_off();
        s16 y1 = (s16)(y0 + 192);

        /* TMS 192-line clip. Origin in a letterbox is off-screen.
         * SAT Y 0xB8 draws at 200 and occupies 200-215; the bar is
         * 208-223. Low-pri sprites are clipped by the high-pri bar
         * for the overlapping 8px; hide only when fully past 192. */
        if (dy + (s16)MODE_SPR_W <= y0 || dy >= y1)
            want_vis = 0;
        if (mode_hud_overlap(dx, MODE_SPR_W))
            want_vis = 0;
    }
    SPR_setVisibility(sp, want_vis ? VISIBLE : HIDDEN);
}

/*
 * 8f25/8a5a/8f45 SAT Y is +8 per E700.1 (IX+01). TMS nametable has no
 * VSCROLL, so that Y and the tiles stay aligned. MD VSCROLL also has
 * E711>>5 (s_scroll_px & 7). Draw-only: add the remainder so 8f45-class
 * sprites track the sliding tiles. Collision / SAT stay on the 8px grid.
 * Do not add scroll_delta to SAT Y (rejected vs 8f45).
 * Flyers (ground==0) stay at screen SAT Y -- TMS flyers do not ride a
 * subpixel nametable (sprite_sat_write 0x48C0 is SAT Y-0x11, no E711).
 * Adding frac to flyers would drift idle SAT with VSCROLL; TMS does not.
 * MD tiles slide 0-7px under them (VDP != TMS). Leave that.
 */
static s16 slot_draw_y(const Slot *s)
{
    s16 y = mode_draw_y(s->y);

    if (s->ground)
        y = (s16)(y + (s16)map_script_scroll_frac());
    return y;
}

static void spr_sync(Slot *s)
{
    s16 dx;
    s16 dy;
    s16 mdx;
    s16 mdy;

    dx = mode_draw_x(s->x, s->sat_col);
    dy = slot_draw_y(s);
    if (s->spr)
    {
        SPR_setPosition(s->spr, dx, dy);
        sat_bind_depth(s->spr, sat_depth_primary(s));
        spr_vis_playfield(s->spr, dx, dy, 1);
    }
    /* 71f6: SAT Y = parentY-0x11, X = parent X, color 0x81. Same SUB as
     * sprite_sat_write 0x48C0, so MD draw Y matches the primary (both skip
     * the hardware SAT offset). Later SAT index draws behind on TMS. */
    if (!s->mspr)
        return;
    /* 71f6 X = parent X, color 0x81 (EC). Same draw X/Y as a 0x8x primary
     * (SUB 0x11 == 48C0). Do not add ship X+1 or ship Y+2 -- those
     * mis-seat the green flyer complement. */
    mdx = mode_draw_x(s->x, 0x81);
    mdy = dy;
    SPR_setPosition(s->mspr, mdx, mdy);
    sat_bind_depth(s->mspr, sat_depth_marker(s));
    if (s->spr)
        sat_bind_depth(s->spr, sat_depth_primary(s));
    /* 71f6 always writes the complement SAT. Clip only this EC sprite's
     * own draw box. Do not hide it because the primary overlaps the HUD
     * or because a port line-budget is full -- that left colored halves. */
    spr_vis_playfield(s->mspr, mdx, mdy, 1);
}

/* MSX spawn_col_marker (0x71da): type 0x27 slot, +04=0x81, HL left at +03.
 * 71f6 writes SAT Y=parentY-0x11 (same SUB as sprite_sat_write 0x48C0),
 * X=parent X, then copies marker +03/+04. Second SAT names are immediates:
 *   4 box     LD (HL),0xD8   pat 54 FRAME_BOX_C
 *   7 umber   LD (HL),0xE4   pat 57 FRAME_UMBER_C  (morph IY+03=0xE8)
 *  10 duster  LD (HL),0x5C   pat 23 FRAME_DUSTER_C
 *  12-15      LD (HL),0x64   pat 25 FRAME_TERUZO_C
 *  16-18      LD (HL),0x7C   pat 31 FRAME_LUSTER_A_C
 *  22-25      LD (HL),0x98   pat 38 FRAME_VEYBAR_C0 (morph +0x14)
 *  26-29      7e5f SAT=parent+0x10  pats 47-50 FRAME_SPINNER_C0..3
 *  34/65/66   LD (HL),0xD0   pat 52 FRAME_STEALTH_C
 *  44 plane   LD (HL),0x44   pat 17 FRAME_PLANE_C
 *  46-55 gun  LD (HL),0x50   pat 20 FRAME_LOGA_B
 *             fire 0x8162/817a 0x50/0x54 pats 20/21 FRAME_LOGA_B/D
 *  61 sart    LD (HL),0xFC   pat 63 FRAME_SART_C
 *  57         71da, no LD (HL) -- leftover name 0, occupancy only
 *  58         two 71da; first sibling ptr, second unnamed; occupancy x2
 *  30         71da then LDIR sibling as type 31 -- not a marker
 * gfx_sprite_patterns 0x6976 in zanac.asm (DB, decompress_block 0x5CCF)
 * is enough to unfold: primary_only + FRAME_*_C at the same MD draw
 * (71f6 SUB 0x11 == 48C0). Overlaying a folded primary with FRAME_*_C
 * would paint black. Pairdesc 57/58 stay occupancy-only (no SAT name). */
/* 71da writes type 0x27 + color 0x81 and leaves +03 unread. Leftover SAT
 * name 0 is empty (pat 0), not chip (pat 1 SAT 0x04). SGDK addSprite
 * defaults to frame 0 (shot). Complements must not draw those.
 * Occupancy-only (pairdesc 57/58) never calls this with a SAT name. */
static int complement_frame_ok(u16 frame)
{
    if (frame >= FRAME_N)
        return 0;
    if (frame == FRAME_SHOT || frame == FRAME_CHIP)
        return 0;
    return 1;
}

static void mspr_frame_cb(Sprite *sp)
{
    Slot *s = (Slot *)(u32)sp->data;

    /* Own the upload so addSprite frame 0 (SHOT) cannot AUTO-tile over
     * a flyer complement. */
    sp->status &= (u16)~SPR_FLAG_AUTO_TILE_UPLOAD;
    if (s)
        mspr_upload(s);
}

static void mspr_upload(Slot *s)
{
    Sprite *sp = s->mspr;
    TileSet *ts;
    u16 nbytes;
    u16 vaddr;
    const u8 *src;

    /* Complements have no sat_col remap. Queue the SAT-name tiles
     * before spr_sync so frame 0 (shot) never hits the screen. */
    if (!sp || !sp->frame)
        return;
    ts = sp->frame->tileset;
    if (!ts || !ts->numTile)
        return;
    /* Complements are static black tiles. Re-DMA every marker_place /
     * frame-cb blew the NTSC vblank when many 71f6 pairs were live. */
    if (s->mvram_fr == s->mframe)
        return;
    nbytes = (u16)(ts->numTile * 32);
    vaddr = (u16)((sp->attribut & TILE_INDEX_MASK) * 32);
    src = (const u8 *)FAR_SAFE(ts->tiles, nbytes);
    DMA_queueDma(DMA_VRAM, (void *)src, vaddr, (u16)(nbytes / 2), 2);
    s->mvram_fr = s->mframe;
}

static void marker_place(Slot *s, u16 frame)
{
    s16 mdx;
    s16 mdy;

    if (!s->marker)
        s->marker = 1;
    if (!complement_frame_ok(frame))
        return;
    s->mframe = (u8)frame;
    /* Occupancy stays even if the hardware complement is withheld. */
    if (!s->spr)
        return;
    mdx = mode_draw_x(s->x, 0x81);
    mdy = slot_draw_y(s);
        if (!s->mspr)
        {
            /* 71f6 always writes the complement SAT. Do not refuse on a
             * port hardware-sprite budget -- that left colored halves. */
            s->mvram_fr = 0xFF;
            s->mspr = SPR_addSpriteEx(&spr_objs, mdx, mdy,
                                      TILE_ATTR(PAL2, FALSE, FALSE, FALSE),
                                      SPR_FLAG_AUTO_VRAM_ALLOC);
            if (!s->mspr)
                return;
        /* addSprite starts at frame 0 (shot). Own tiles; hide until
         * the complement SAT name is in VRAM. */
        s->mspr->data = (u32)s;
        SPR_setFrameChangeCallback(s->mspr, mspr_frame_cb);
        s->mspr->status &= (u16)~SPR_FLAG_AUTO_TILE_UPLOAD;
        SPR_setVisibility(s->mspr, HIDDEN);
        SPR_setPriority(s->mspr, FALSE);
        SPR_setAnimAndFrame(s->mspr, 0, (s16)frame);
        mspr_upload(s);
        sat_bind_depth(s->mspr, sat_depth_marker(s));
        sat_bind_depth(s->spr, sat_depth_primary(s));
        spr_sync(s);
        return;
    }
    SPR_setAnimAndFrame(s->mspr, 0, (s16)frame);
    mspr_upload(s);
    spr_sync(s);
}

static void marker_kill(Slot *s)
{
    if (s->mspr)
    {
        SPR_releaseSprite(s->mspr);
        s->mspr = NULL;
    }
    s->marker = 0;
    s->mframe = 0;
    s->mvram_fr = 0xFF;
}

/* spr_objs frame -> MSX SAT_NAME (primary). Complements are separate frames. */
static const u8 k_frame_sat[FRAME_N] = {
    0x28, /* 0  FRAME_SHOT */
    0x58, /* 1  FRAME_DUSTER */
    0x60, /* 2  FRAME_TERUZO */
    0x78, /* 3  FRAME_LUSTER */
    0xD4, /* 4  FRAME_BOX */
    0x04, /* 5  FRAME_CHIP  pat 1; 7882 / 8e5d SAT 0x04 */
    0x1C, /* 6  FRAME_LEAD */
    0x70, /* 7  FRAME_SIG */
    0x2C, /* 8  FRAME_SHOT_D */
    0x30, /* 9  FRAME_SHOT_T */
    0x0C, /* 10 FRAME_FIRE */
    0x24, /* 11 FRAME_CIRCLE */
    0x08, /* 12 FRAME_COMET */
    0xEC, /* 13 FRAME_DEGID_L */
    0xF0, /* 14 FRAME_DEGID_R */
    0xF4, /* 15 FRAME_DEGID */
    0x84, /* 16 FRAME_VEYBAR_0 */
    0x88, /* 17 */
    0x8C, /* 18 */
    0x90, /* 19 */
    0x94, /* 20 */
    0x98, /* 21 FRAME_VEYBAR_C0 */
    0x9C, /* 22 */
    0xA0, /* 23 */
    0xA4, /* 24 */
    0xA8, /* 25 */
    0x5C, /* 26 FRAME_DUSTER_C */
    0x64, /* 27 FRAME_TERUZO_C */
    0xD8, /* 28 FRAME_BOX_C */
    0x80, /* 29 FRAME_LUSTER_C */
    0xDC, /* 30 FRAME_UMBER */
    0xE4, /* 31 FRAME_UMBER_C */
    0xCC, /* 32 FRAME_STEALTH */
    0xD0, /* 33 FRAME_STEALTH_C */
    0xAC, /* 34 FRAME_SPINNER_0 */
    0xB0, /* 35 */
    0xB4, /* 36 */
    0xB8, /* 37 */
    0xBC, /* 38 FRAME_SPINNER_C0 */
    0xC0, /* 39 */
    0xC4, /* 40 */
    0xC8, /* 41 */
    0xF8, /* 42 FRAME_SART */
    0xFC, /* 43 FRAME_SART_C */
    0x48, /* 44 FRAME_LOGA */
    0x4C, /* 45 FRAME_LOGA_C */
    0x40, /* 46 FRAME_PLANE */
    0x44, /* 47 FRAME_PLANE_C */
    0x34, /* 48 FRAME_BOLT */
    0x18, /* 49 FRAME_LIGHT_BAR */
    0x68, /* 50 FRAME_SIG_TRIPLE */
    0x6C, /* 51 FRAME_SIG_DOUBLE */
    0x20, /* 52 FRAME_MED_CIRCLE */
    0x74, /* 53 FRAME_LUSTER_A */
    0x7C, /* 54 FRAME_LUSTER_A_C  pat31 SAT 0x7C */
    0xE0, /* 55 FRAME_UMBER_B */
    0xE8, /* 56 FRAME_UMBER_B_C */
    0x50, /* 57 FRAME_LOGA_B  pat20 SAT 0x50 */
    0x54, /* 58 FRAME_LOGA_D  pat21 SAT 0x54 */
    0x10, /* 59 FRAME_SNOW    pat 4 SAT 0x10 */
    0x14  /* 60 FRAME_SMALL_STAR pat 5 SAT 0x14 type 67 */
};

static u16 frame_from_sat(u8 sat);
static void anim_sub_4912(Slot *e, const u8 *sats, const u8 *cols,
                         u8 nframes, u8 reload);

/* SAT name -> FRAME_*. SAT 0 is empty (pat 0). Do not return FRAME_CHIP
 * or FRAME_SHOT -- leftover name 0 is occupancy. FRAME_CHIP is SAT 0x04. */
static u16 frame_from_sat(u8 sat)
{
    u16 i;

    if (!sat)
        return FRAME_N;
    for (i = 0; i < FRAME_N; i++)
    {
        if (k_frame_sat[i] == sat)
            return i;
    }
    return FRAME_N;
}

/* Frame -> baked TMS body index in objs.png (rebuild_sprites.py). */
static const u8 k_frame_color[FRAME_N] = {
    15, 9, 10, 14, 15, 11, 15, 15, 15, 15, 15, 15, 15,
    15, 15, 15,
    7, 7, 7, 7, 7,
    1, 1, 1, 1, 1,
    1, 1, 1, 1,
    15, 1, 8, 1,
    14, 14, 14, 14, 1, 1, 1, 1,
    7, 1, 15, 1, 7, 1, 15, 4, 15, 15, 15,
    11, 1, 7, 1,
    1, 1,
    15,
    15
};

static void remap_tiles(u8 *dst, const u8 *src, u16 nbytes, u8 from, u8 to)
{
    u16 i;

    for (i = 0; i < nbytes; i++)
    {
        u8 b = src[i];
        u8 hi = (u8)(b >> 4);
        u8 lo = (u8)(b & 0x0F);

        if (hi == from)
            hi = to;
        if (lo == from)
            lo = to;
        dst[i] = (u8)((hi << 4) | lo);
    }
}

/* 8a16 / 84d1 / 86F3 discs: gfx pats 7/8/9 are body bits only (0 or the
 * baked nibble). SGDK rescomp may pack that nibble off 15. Remap every
 * nonzero nibble to sat_col so the pulse is a clean disc, not leftover
 * flyer-blue / shot tiles from a packed index that `from==15` missed. */
/* Every non-zero nibble becomes `want`, zero stays zero.
 *
 * This runs on the whole tileset of a sprite whose SAT colour changed, and the
 * MSX changes that colour a lot: 72de walks the player's fire weapon through
 * all 16 colours one per frame, and several enemies XOR-blink theirs. Measured
 * with a V-counter profiler, update_fire alone was 60 of entity_update's 134
 * scanlines with the byte-at-a-time version below, and 7 without it -- a fifth
 * of an NTSC frame spent remapping nibbles while the fire button is held.
 *
 * The 32-bit form does eight nibbles at a time with no branches:
 *   m = v | v>>1 | v>>2 | v>>3   collects each nibble's bits into its low bit
 *   m &= 0x11111111              leaves 1 in the low bit of every non-zero one
 *   m = (m << 4) - m             is m * 15, so 0xF fills every non-zero nibble
 *                                (15 fits a nibble, so no carry crosses one)
 *   m & (want * 0x11111111)      selects `want` exactly where the mask is set
 * Verified equivalent to the byte loop over every 16-bit pattern and all 16
 * values of `want`, plus 320000 random 32-bit words.
 *
 * The 68000 traps on an unaligned long access, so anything not 4-byte aligned
 * (or a tail of 1-3 bytes) falls back to the original loop. */
static void orb_paint_body_nibbles(u8 *dst, const u8 *src, u16 nbytes, u8 want)
{
    const u8 *sp = src ? src : dst;
    u16 i = 0;

    if (!(((u32)dst | (u32)sp) & 3))
    {
        const u32 w8 = (u32)want * 0x11111111UL;
        u32 *d = (u32 *)dst;
        const u32 *s = (const u32 *)sp;
        u16 n = (u16)(nbytes >> 2);

        while (n--)
        {
            u32 v = *s++;
            u32 m = v | (v >> 1) | (v >> 2) | (v >> 3);

            m &= 0x11111111UL;
            *d++ = ((m << 4) - m) & w8;
        }
        i = (u16)(nbytes & ~3u);
    }

    for (; i < nbytes; i++)
    {
        u8 b = sp[i];
        u8 hi = (u8)(b >> 4);
        u8 lo = (u8)(b & 0x0F);

        if (hi)
            hi = want;
        if (lo)
            lo = want;
        dst[i] = (u8)((hi << 4) | lo);
    }
}

/* Type 72 discs are body 15 remapped to sat_col. A leftover nibble 4/5
 * (flyer blue) or 7 (PAL2 cyan) in an empty UL corner is the playtest
 * speck -- gfx pats 7/8 UL 4x4 are 0 bits; pat 9 UL 4x4 is the disc.
 * Keep 0 and `keep`; drop everything else. Does not invent pixels. */
static void orb_keep_body_nibbles(u8 *dst, u16 nbytes, u8 keep)
{
    u16 i;

    for (i = 0; i < nbytes; i++)
    {
        u8 b = dst[i];
        u8 hi = (u8)(b >> 4);
        u8 lo = (u8)(b & 0x0F);

        if (hi && hi != keep)
            hi = 0;
        if (lo && lo != keep)
            lo = 0;
        dst[i] = (u8)((hi << 4) | lo);
    }
}

/* Type 72 8a16 mid is SAT 0x20 / colour 0x83, which is TMS colour 3
 * (base_core_anim: `1C 8F 20 83 24 8A 20 8B`). It is uploaded on PAL2[7]
 * (cyan) instead, which was introduced to dodge the old half-brightness
 * PAL2[3]. That override is gone now, so this remap is probably stale and
 * the ROM's own colour 3 should be correct -- but the orb is a base-core
 * frame that unattended play does not reach, so it has not been compared
 * against openMSX and is left alone deliberately. */
static const u8 k_orb_mid_pal = 7;

/* zanac-re gfx_sprite_patterns 0x6976 pats 7/8/9 (SAT 0x1C/0x20/0x24).
 * Japan v1 SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2. objs.png
 * FRAME_LEAD/MED/CIRCLE match these bits, but SGDK BALANCED cuts
 * FRAME_LEAD to an 8x8 that shows only the UL tile (4 px shard).
 * Type 72 encodes these bytes into a 16x16 4-tile vehicle. */
static const u8 k_japan_pat7[32] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x03,
    0x02, 0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0xC0,
    0x40, 0xC0, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00
};
static const u8 k_japan_pat8[32] = {
    0x00, 0x00, 0x01, 0x07, 0x0F, 0x1F, 0x1F, 0x3F,
    0x3F, 0x1F, 0x1F, 0x0F, 0x07, 0x01, 0x00, 0x00,
    0x00, 0x00, 0x80, 0xE0, 0xF0, 0xF8, 0xF8, 0xFC,
    0xFC, 0xF8, 0xF8, 0xF0, 0xE0, 0x80, 0x00, 0x00
};
static const u8 k_japan_pat9[32] = {
    0x03, 0x0F, 0x3F, 0x3F, 0x7F, 0x7F, 0xFF, 0xFF,
    0xFF, 0xFF, 0x7F, 0x7F, 0x3F, 0x3F, 0x0F, 0x03,
    0xC0, 0xF0, 0xFC, 0xFC, 0xFE, 0xFE, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFE, 0xFE, 0xFC, 0xFC, 0xF0, 0xC0
};

static const u8 *orb_japan_pat(u8 sat)
{
    switch (sat & 0xFC)
    {
    case 0x1C:
        return k_japan_pat7;
    case 0x20:
        return k_japan_pat8;
    case 0x24:
        return k_japan_pat9;
    default:
        return 0;
    }
}

/* MSX 16x16 1-bit (left 16 rows, right 16 rows) -> 4 Genesis tiles,
 * column-major (TL, BL, TR, BR). Body nibble = want; 0 = transparent. */
/* One MSX pattern byte -> eight 4bpp nibbles, 0xF where the bit is set.
 * Built once; 1 KB of work RAM against a per-pixel loop on every orb frame. */
static u32 k_bits8[256];
static u8  k_bits8_ready;

static void bits8_init(void)
{
    u16 b;

    for (b = 0; b < 256; b++)
    {
        u32 v = 0;
        u8 i;

        for (i = 0; i < 8; i++)
            v |= (u32)(((b >> (7 - i)) & 1) ? 0xF : 0) << (4 * (7 - i));
        k_bits8[b] = v;
    }
    k_bits8_ready = 1;
}

/* A 16x16 MSX sprite stores its left half at pat[0..15] and its right half at
 * pat[16..31], so each 8-pixel Mega Drive tile row comes from exactly ONE
 * source byte -- the old triple loop rediscovered that per pixel, with a
 * variable shift and two branches each, 128 times per call. The type-72 orb
 * animates its SAT colour every frame (base_core_anim 0x8A16), so the cache in
 * orb_upload_japan misses every frame and this ran for every live orb; three
 * on screen at once is the reported "slowdown da porra".
 *
 * Table form: 32 iterations, each a byte load, a table lookup, an AND and two
 * word stores. A Mega Drive DMA source is always word aligned but not always
 * long aligned, so this writes 16 bits at a time -- an earlier long-store
 * version fell back to a per-byte path on most calls and kept the cost. */
static void orb_encode_japan_tiles(u8 *dst, const u8 *pat, u8 want)
{
    const u32 w8 = (u32)want * 0x11111111UL;
    u16 *d = (u16 *)dst;
    u8 t;

    if (!k_bits8_ready)
        bits8_init();

    for (t = 0; t < 4; t++)
    {
        const u8 *src = (t & 2) ? pat + 16 : pat;
        u8 ty = (u8)((t & 1) ? 8 : 0);
        u8 row;

        for (row = 0; row < 8; row++)
        {
            u32 v = k_bits8[src[ty + row]] & w8;

            *d++ = (u16)(v >> 16);
            *d++ = (u16)v;
        }
    }
}

/* Encoded-variant cache for the type-72 orb.
 *
 * base_core_anim 0x8A16 walks the orb through a fixed, tiny set of states:
 * SAT names 0x1C / 0x20 / 0x24 against colours 0x8F, 0x83 (uploaded as
 * k_orb_mid_pal), 0x8A and 0x8B while it is yellow, and 0x81 once it turns
 * black. That is at most 15 distinct (pattern, nibble) pairs for the whole
 * animation, and it repeats every four frames forever.
 *
 * Re-encoding one on every change cost 23 of the 36 scanlines that three live
 * orbs spent in spr_set_sat_col, so keep the encoded bytes instead. 16 slots
 * against 15 reachable pairs means a warm cache never evicts, which also keeps
 * every pointer handed to DMA_queueDma valid until the frame's flush -- a slot
 * cannot be rewritten while a queue entry still points at it.
 *
 * Round-robin replacement is only a safety net for data that never happens. */
#define ORB_CACHE_N     16
#define ORB_TILE_BYTES  128

/* Declared as words on purpose. A u8 array has alignment 1 on m68k, so the
 * linker is free to start it on an odd address -- which it did, and both the
 * encoder's word stores and the DMA source address then take an address
 * error. */
static u16 s_orb_cache[ORB_CACHE_N][ORB_TILE_BYTES / 2];
static u16 s_orb_cache_key[ORB_CACHE_N];
static u8  s_orb_cache_used;
static u8  s_orb_cache_next;

static void orb_cache_reset(void)
{
    s_orb_cache_used = 0;
    s_orb_cache_next = 0;
}

/* (frame, nibble) remap cache for XOR / 72de sprites that still go
 * through spr_upload_color. Fire 0/1/2/7 prefer CRAM (below); this
 * catches type 36/56/59/67 and any leftover sat_col walk. 32 slots
 * of 128 bytes: two nibbles x a handful of frames never evict. */
#define REMAP_CACHE_N       32
#define REMAP_TILE_BYTES    128

static u16 s_remap_cache[REMAP_CACHE_N][REMAP_TILE_BYTES / 2];
static u16 s_remap_key[REMAP_CACHE_N];
static u8  s_remap_used;
static u8  s_remap_next;

static void remap_cache_reset(void)
{
    s_remap_used = 0;
    s_remap_next = 0;
}

static const u8 *remap_cache_get(u8 frame, u8 baked, u8 want,
                                 const u8 *src, u16 nbytes, u8 paint_all)
{
    u16 key = (u16)(((u16)frame << 8) | ((u16)baked << 4) | want);
    u8 i;
    u8 *dst;

    for (i = 0; i < s_remap_used; i++)
        if (s_remap_key[i] == key)
            return (const u8 *)s_remap_cache[i];

    if (s_remap_used < REMAP_CACHE_N)
        i = s_remap_used++;
    else
    {
        i = s_remap_next;
        s_remap_next = (u8)((s_remap_next + 1) & (REMAP_CACHE_N - 1));
    }
    dst = (u8 *)s_remap_cache[i];
    if (nbytes > REMAP_TILE_BYTES)
        nbytes = REMAP_TILE_BYTES;
    if (paint_all)
        orb_paint_body_nibbles(dst, src, nbytes, want);
    else
        remap_tiles(dst, src, nbytes, baked, want);
    s_remap_key[i] = key;
    return dst;
}

static const u8 *orb_cache_get(u8 sat, const u8 *jp, u8 want)
{
    u16 key = (u16)(((u16)sat << 8) | want);
    u8 i;

    for (i = 0; i < s_orb_cache_used; i++)
        if (s_orb_cache_key[i] == key)
            return (const u8 *)s_orb_cache[i];

    if (s_orb_cache_used < ORB_CACHE_N)
        i = s_orb_cache_used++;
    else
    {
        i = s_orb_cache_next;
        s_orb_cache_next = (u8)((s_orb_cache_next + 1) & (ORB_CACHE_N - 1));
    }
    orb_encode_japan_tiles((u8 *)s_orb_cache[i], jp, want);
    s_orb_cache_key[i] = key;
    return (const u8 *)s_orb_cache[i];
}

/* Type 72 only: 4-tile Japan disc. Cache key is SAT name + nibble
 * (FRAME_CIRCLE vehicle stays; 8a16 SAT 1C/20/24 changes the pat). */
static int orb_upload_japan(Slot *s, u8 want)
{
    const u8 *jp;
    u16 vaddr;

    if (s->kind != KIND_ORB)
        return 0;
    jp = orb_japan_pat(s->sat);
    if (!jp || !s->spr)
        return 0;
    if (s->vram_fr == s->sat && s->vram_nib == want)
        return 1;

    vaddr = (u16)((s->spr->attribut & TILE_INDEX_MASK) * 32);
    DMA_queueDma(DMA_VRAM, orb_cache_get(s->sat, jp, want), vaddr, 64, 2);
    s->vram_fr = s->sat;
    s->vram_nib = want;
    return 1;
}

/* Upload spr_objs frame tiles, remapping baked TMS body -> sat_col low nibble.
 * PAL2 indices match rebuild_sprites / TMS low nibble. Complement (1) untouched. */
static void spr_upload_color(Slot *s)
{
    Sprite *sp = s->spr;
    TileSet *ts;
    u8 baked;
    u8 want;
    u16 nbytes;
    u16 vaddr;
    const u8 *src;

    if (!sp || !sp->frame || s->frame >= FRAME_N)
        return;
    ts = sp->frame->tileset;
    if (!ts || !ts->numTile)
        return;

    baked = k_frame_color[s->frame];
    /* Complement-only / blank frames keep verbatim pixels.
     * Exception: 816d writes SAT 0x4C (pat 19) onto the GUN PRIMARY and
     * keeps +04 colour. FRAME_LOGA_C is unfolded as black (marker art),
     * but Japan draws those bits in sat_col. Other 71f6 pairs stay
     * primary+black at the same draw (Y-0x11 / same X). */
    if (s->kind == KIND_GUN && s->frame == FRAME_LOGA_C && s->sat_col)
        want = (u8)(s->sat_col & 0x0F);
    else if (baked <= 1)
        want = baked;
    else if (s->kind == KIND_ORB && (s->sat_col & 0x0F) == 3)
        want = k_orb_mid_pal;   /* 8a16 0x83 off dim PAL2[3] */
    else if (s->sat_col)
        want = (u8)(s->sat_col & 0x0F);
    else
        want = baked;

    /* Type 72: Japan pats 7/8/9 into the 16x16 vehicle. Do not use the
     * SGDK FRAME_LEAD tileset (BALANCED 8x8 UL shard / leftover nibbles). */
    if (orb_upload_japan(s, want))
        return;

    /* Same frame + same nibble: vis/XOR-high-nibble blinks must not DMA. */
    if (s->vram_fr == s->frame && s->vram_nib == want)
        return;

    nbytes = (u16)(ts->numTile * 32);
    vaddr = (u16)((sp->attribut & TILE_INDEX_MASK) * 32);
    src = (const u8 *)FAR_SAFE(ts->tiles, nbytes);

    /* Upload this frame's tileset only. A hardcoded 4-tile pad wrote past
     * a 1-2 tile AUTO_VRAM slot and composited FRAME_SHOT into the next
     * flyer. Disc leftover is orb_paint_body_nibbles, not VRAM pad. */
    {
        u8 disc = (u8)(s->kind == KIND_EXPL || s->kind == KIND_PDEAD
                       || s->kind == KIND_HUSK);

        /* Verbatim tiles: queue ROM/FAR src. Skip the 128-byte copy
         * into a DMA scratch (and do not allocateAndQueue an unused buf). */
        if (!disc && want == baked)
        {
            DMA_queueDma(DMA_VRAM, (void *)src, vaddr, (u16)(nbytes / 2), 2);
            s->vram_fr = s->frame;
            s->vram_nib = want;
            return;
        }

        /* Cache the remapped tiles and DMA from the slot. allocateAndQueue
         * every XOR/72de tick was the leftover 68000 cost after the orb
         * variant cache; a warm (frame,nibble) slot is a plain queue. */
        {
            const u8 *cached = remap_cache_get(s->frame, baked, want, src,
                                               nbytes, disc);
            u16 nq = nbytes;

            if (nq > REMAP_TILE_BYTES)
                nq = REMAP_TILE_BYTES;
            if (disc)
            {
                static u8 s_disc[REMAP_TILE_BYTES];

                memcpy(s_disc, cached, nq);
                orb_keep_body_nibbles(s_disc, nq, want);
                DMA_queueDma(DMA_VRAM, s_disc, vaddr, (u16)(nq / 2), 2);
            }
            else
                DMA_queueDma(DMA_VRAM, (void *)cached, vaddr,
                             (u16)(nq / 2), 2);
        }
        s->vram_fr = s->frame;
        s->vram_nib = want;
    }
}

static void spr_frame_cb(Sprite *sp)
{
    Slot *s = (Slot *)(u32)sp->data;

    /* We own tile upload so sat_col remaps are not overwritten. */
    sp->status &= (u16)~SPR_FLAG_AUTO_TILE_UPLOAD;
    if (s)
        spr_upload_color(s);
}

static void spr_set_sat_col(Slot *s, u8 col)
{
    s->sat_col = col;
    if (s->spr && s->spr->frame)
        spr_upload_color(s);
}

static void spr_place(Slot *s, u16 frame)
{
    s16 prev;

    if (frame < FRAME_N)
        s->sat = k_frame_sat[frame];
    s->frame = (u8)frame;
    /* Reused slot: leftover type39 mspr at FRAME_SHOT/CHIP (addSprite
     * default) stays composited on the new flyer if we only kill when
     * marker==0. Drop a complement whose SAT name is not real; a live
     * 71f6 pair keeps marker + a valid FRAME_*_C and is left alone. */
    if (s->mspr && (!s->marker || !complement_frame_ok(s->mframe)))
        marker_kill(s);
    if (!s->spr)
    {
        s->vram_fr = 0xFF;
        s->vram_nib = 0xFF;
        s->spr = SPR_addSpriteEx(&spr_objs, mode_draw_x(s->x, s->sat_col),
                                 slot_draw_y(s),
                                 TILE_ATTR(PAL2, FALSE, FALSE, FALSE),
                                 SPR_FLAG_AUTO_VRAM_ALLOC);
        if (s->spr)
        {
            s->spr->data = (u32)s;
            SPR_setFrameChangeCallback(s->spr, spr_frame_cb);
            /* addSprite defaults to objs frame 0 (shot). Hide, set SAT
             * name, upload tiles, then spr_sync may show. */
            SPR_setVisibility(s->spr, HIDDEN);
            SPR_setPriority(s->spr, FALSE);
            SPR_setAnimAndFrame(s->spr, 0, frame);
            spr_upload_color(s);
            spr_sync(s);
        }
    }
    else
    {
        prev = s->spr->frameInd;
        /* Disc SAT must re-paint every place: SGDK can pack baked 15
         * off 15 so a cached nibble leaves flyer-blue junk in the disc. */
        if (s->kind == KIND_ORB || s->kind == KIND_EXPL
            || s->kind == KIND_PDEAD || s->kind == KIND_HUSK)
        {
            s->vram_fr = 0xFF;
            s->vram_nib = 0xFF;
        }
        SPR_setAnimAndFrame(s->spr, 0, frame);
        /* Tiles before visible. Same frame skips callback -- push now. */
        if (prev == (s16)frame)
            spr_upload_color(s);
        spr_sync(s);
    }
}

/* Release hardware sprites without clearing the slot. Assigning
 * spr=NULL without SPR_releaseSprite leaks AUTO_VRAM + an SGDK
 * sprite until addSprite returns NULL (invisible type 4/5/6 boxes)
 * and SPR_update walks leftover SAT entries (slowdown). */
static void spr_detach(Slot *s)
{
    marker_kill(s);
    if (s->spr)
    {
        SPR_releaseSprite(s->spr);
        s->spr = NULL;
    }
    s->vram_fr = 0xFF;
    s->vram_nib = 0xFF;
    s->mvram_fr = 0xFF;
}

static void spr_kill(Slot *s)
{
    spr_detach(s);
    s->alive = 0;
    s->kind = 0;
    s->variant = 0;
    s->hp = 0;
    s->timer = 0;
    s->script = 0;
    s->ground = 0;
    s->armed = 0;
    s->aux = 0;
    s->clock = 0;
    s->sat = 0;
    s->sat_col = 0;
    s->frame = 0;
    s->vram_fr = 0xFF;
    s->vram_nib = 0xFF;
    s->dest = 0;
    s->bind = 0;
    s->mspr = NULL;
}

static u8 rnd(void)
{
    s_rng = (u16)(s_rng * 2053 + 13849);
    return (u8)(s_rng >> 8);
}

static Slot *free_enemy(void)
{
    u8 i;
    for (i = 0; i < ENEMY_SLOTS; i++)
        if (!s_en[i].alive)
        {
            /* Do not spr_kill: release+addSprite reallocates VRAM and
             * flashes objs frame 0 (shot) until tiles upload. Death
             * already released. spr_place reuses or adds hidden.
             * Leftover type39 mspr (shot/chip default) must not ride
             * the next flyer -- 71f6 re-adds a real complement. */
            marker_kill(&s_en[i]);
            return &s_en[i];
        }
    return NULL;
}

/* random_x_pos 0x71C5: X=(H&0x7F)+(L&0x1F)+0x28, Y written 0 by the caller. */
static u8 random_x_71c5(void)
{
    u8 r1 = rnd();
    u8 r2 = rnd();

    return (u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28);
}

/* type 0x23 / handler_type35: +0x18=0; first frame arms 84d1 + SFX/score. */
static void spawn_expl(s16 x, s16 y)
{
    Slot *e = free_enemy();

    if (!e)
        return;
    e->alive = 1;
    e->kind = KIND_EXPL;
    e->variant = 0;
    e->hp = 0;
    e->timer = 0;
    e->script = 0;
    e->ground = 0;
    e->aux = 0;
    e->clock = 0;
    e->dest = 0;
    e->bind = 0;
    e->x = x;
    e->y = y;
    e->vx = 0;
    e->vy = 0;
    spr_detach(e);
    e->sat = 0;
    e->sat_col = 0;
    e->frame = 0;
    /* 8446 bit7 clear: first expl_step arms 84d1 and 4912 writes
     * table[1]. Do not spr_place FRAME_LEAD/SHOT here. */
}

/* 0x8BCA: first R -> Y (C), second R -> X (B). 8bc1 BC=0x1F1F; 9251 BC=0x7F07. */
void entity_scatter_8bca(s16 x, s16 y, u8 xmask, u8 ymask, u8 n)
{
    u8 i;
    u8 half_y = (u8)(ymask >> 1);
    u8 half_x = (u8)(xmask >> 1);

    for (i = 0; i < n; i++)
    {
        u8 ry = rnd();
        u8 rx = rnd();

        spawn_expl((s16)(x + (s16)(u8)(rx & xmask) - (s16)half_x),
                   (s16)(y + (s16)(u8)(ry & ymask) - (s16)half_y));
    }
}

/* LAB_ram_8bc1 / SUB_ram_8bca: type 0x23 at (X,Y) +/- (R&0x1F)-0x0F. */
static void scatter_expl(s16 x, s16 y)
{
    entity_scatter_8bca(x, y, 0x1F, 0x1F, 1);
}

/* 0x84D1 type35/80: (sat_name, sat_color) x6. Frame 0 is JP 0x48D0
 * bytes (SAT 0xD0 stealth_compl, 0x48). Init +0F=1 skips it. After
 * frame 5, +0F wraps to 0 and the next 84c9/8e30 clears (no write). */
static const u8 k_t35_sat[6] = { 0xD0, 0x1C, 0x20, 0x24, 0x20, 0x1C };
static const u8 k_t35_col[6] = {
    0x48, 0x8A, 0x8E, 0x8F, 0x8D, 0x89
};

/* 0x86F3 type60 death: 11 pairs. Frame 0 SAT 0x00 empty (RET overlap).
 * +0D=4 so first three 4898 ticks keep leftover SAT; +0F=1 skips 0. */
static const u8 k_t60_sat[11] = {
    0x00, 0x1C, 0x1C, 0x20, 0x20, 0x24, 0x24, 0x20, 0x20, 0x1C, 0x1C
};
static const u8 k_t60_col[11] = {
    0xC9, 0x86, 0x8F, 0x88, 0x8F, 0x89, 0x8F, 0x88, 0x89, 0x86, 0x8F
};

/* anim_sub 0x4912: DEC +0D; NZ keep SAT. Else +0D=+0E, write
 * table[+0F], INC +0F, wrap +0F>=+10 to 0.
 * Port: clock=+0D, aux=+0F. Do not increment before the write
 * (that skipped 84d1[1] lead and landed on med / frame 0 shot). */
static void anim_sub_4912(Slot *e, const u8 *sats, const u8 *cols,
                         u8 nframes, u8 reload)
{
    u16 fr;
    u8 sat;

    if (e->clock)
        e->clock--;
    if (e->clock)
        return;
    e->clock = reload;
    if (e->aux < nframes)
    {
        sat = sats[e->aux];
        e->sat = sat;
        fr = frame_from_sat(sat);
        if (fr < FRAME_N)
        {
            spr_place(e, fr);
            e->sat = sat;
            spr_set_sat_col(e, cols[e->aux]);
        }
        else if (e->spr)
            SPR_setVisibility(e->spr, HIDDEN);
    }
    e->aux++;
    if (e->aux >= nframes)
        e->aux = 0;
}

/* Remap living slot -> type 0x23. score_t is +0x18 for 4a6a (0 = scatter). */
static void become_expl(Slot *e, u8 score_t)
{
    u8 sat_space = (u8)(e->kind == KIND_GROUND || e->kind == KIND_GUN);
    u8 nt_locked = (u8)(e->kind == KIND_WIDE || e->kind == KIND_FIREBOX
                        || e->kind == KIND_BASE);

    marker_kill(e);
    e->kind = KIND_EXPL;
    e->variant = score_t;
    e->hp = 0;
    e->timer = 0;
    e->script = 0;          /* first frame: ALC + SFX + score + 84d1 arm */
    /* 84d1 keeps live SAT Y via sprite_sat_write. Forcing ground=1 on
     * 4898 type44/guns added VSCROLL frac and printed the disc BELOW
     * the sprite. 8f25 WIDE/FIREBOX/BASE already have ground=1. */
    if (sat_space)
        e->ground = 0;
    e->aux = 0;
    e->clock = 0;
    e->vx = 0;
    e->vy = 0;
    /* Flyers keep leftover SAT until 8446+84c9 4912 writes 84d1[1]
     * (item 1 type-35 velocity / SAT). SAT-space leftovers (type 44 /
     * guns) also keep leftover SAT — Japan 48B8 writes the live SAT Y.
     * Hide only NT-locked leftovers (8f25 wide/base/firebox). */
}

/* handler_type60 0x869E: fire_reset + SRL E132/E12E + ev16 + arm 86F3.
 * Runs in an enemy slot (MD ship is separate); clear sets E102 bit0. */
void entity_spawn_pdeath(s16 x, s16 y)
{
    Slot *e = free_enemy();

    /* 86b7/86bc: SRL E132, SRL E12E (ease ALC on death). */
    s_e132 = (u8)(s_e132 >> 1);
    s_spawn_pos_hi = (u8)(s_spawn_pos_hi >> 1);

    if (!e)
    {
        /* No slot: still signal death->continue so lives/respawn proceed. */
        sound_play_event(SND_EV_DEATH);
        player_e102_set(0x01);
        return;
    }
    e->alive = 1;
    e->kind = KIND_PDEAD;
    e->variant = 60;
    e->hp = 0;
    e->timer = 0;
    e->script = 0;          /* first frame: SFX + 86F3 arm */
    e->ground = 0;
    e->aux = 0;
    e->clock = 0;
    e->dest = 0;
    e->bind = 0;
    e->x = x;
    e->y = y;
    e->vx = 0;
    e->vy = 0;
    spr_detach(e);
    e->sat = 0;
    e->sat_col = 0;
    e->frame = 0;
}

static int aabb(s16 x1, s16 y1, s16 w1, s16 h1,
                s16 x2, s16 y2, s16 w2, s16 h2)
{
    return (x1 < (s16)(x2 + w2)) && ((s16)(x1 + w1) > x2)
        && (y1 < (s16)(y2 + h2)) && ((s16)(y1 + h1) > y2);
}


/* collision_size_table 0x45C9: Y/X half-sizes interleaved, indexed by
 * sat_name>>1. Hitbox = [pos+half, pos+16-half] => origin pos+half,
 * size 16-2*half (hitbox_setup_ix 0x45A0). Bytes through 0x4648 cover
 * sat_name 0x00..0xFE (high patterns read past the 32-byte KB'd core). */
static const u8 k_col_size[128] = {
    0x00, 0x00, 0x03, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x03, 0x05, 0x00, 0x06, 0x06,
    0x01, 0x01, 0x00, 0x00, 0x00, 0x06, 0x00, 0x03, 0x00, 0x00, 0x02, 0x02, 0x04, 0x04, 0x04, 0x04,
    0x02, 0x01, 0x02, 0x01, 0x00, 0x03, 0x00, 0x03, 0x00, 0x02, 0x00, 0x02, 0x00, 0x03, 0x00, 0x00,
    0x02, 0x02, 0x00, 0x00, 0x00, 0x01, 0x02, 0x01, 0x02, 0x06, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
    0x00, 0x00, 0x02, 0x00, 0x04, 0x00, 0x06, 0x00, 0x04, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x01, 0x02, 0x03, 0x02, 0x07, 0x02, 0x03, 0x02, 0x01,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02,
    0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x00, 0x03, 0x00, 0x02, 0x00, 0x02, 0x00, 0x02
};

#define SAT_PLAYER  0x38  /* pat14 ship; half 4,4 => 8x8 */

static void hitbox_of(u8 sat, s16 x, s16 y, s16 *ox, s16 *oy, s16 *ow, s16 *oh)
{
    u8 idx = (u8)(sat >> 1);
    u8 hy = k_col_size[idx];
    u8 hx = k_col_size[(u8)(idx + 1)];
    if (hx > 7) hx = 7;
    if (hy > 7) hy = 7;
    *ox = (s16)(x + (s16)hx);
    *oy = (s16)(y + (s16)hy);
    *ow = (s16)(16 - (s16)(hx << 1));
    *oh = (s16)(16 - (s16)(hy << 1));
}

static int hit_overlap(s16 x1, s16 y1, u8 sat1, s16 x2, s16 y2, u8 sat2)
{
    s16 ax, ay, aw, ah, bx, by, bw, bh;
    hitbox_of(sat1, x1, y1, &ax, &ay, &aw, &ah);
    hitbox_of(sat2, x2, y2, &bx, &by, &bw, &bh);
    return aabb(ax, ay, aw, ah, bx, by, bw, bh);
}

/* collision_routine 0x4560: both boxes are SAT X/Y and sat_name>>1 into
 * 0x45C9. Do not convert to visual X -- ship/shots/EC enemies all store
 * SAT X and draw with TMS EC, so SAT overlap is graphic overlap.
 * Do not add map_script_scroll_frac() here. Nametable-only bases/idols
 * have no sprite; tiles ride MD VSCROLL while SAT stays on the 8px grid
 * (8f25/8a5a). That 0-7px vs art is MD VDP != TMS, not a missing store.
 * Wreck stamps bind with scroll_px&~7 and then ride the same VSCROLL as
 * the live tiles, so the punch is not crooked vs the nametable. */
static int hit_overlap_slot(s16 x1, s16 y1, u8 sat1, const Slot *e)
{
    u8 esat = e->sat ? e->sat : (u8)0x40;

    return hit_overlap(x1, y1, sat1, e->x, e->y, esat);
}

/* death_transition_table 0x716B (collision_response 0x453E): type&0x7F ->
 * post-collision class/type written back to both parties. "Classes": */
#define CLS_NONE   0x00  /* inactive */
#define CLS_FIRE19 0x13  /* fire weapon -> type 19 converter */
#define CLS_EXPL   0x23  /* standard enemy explosion (type 35) */
#define CLS_MARK   0x27  /* col-marker stays type 39 */
#define CLS_CLEAR  0x28  /* instant despawn (type 40) */
#define CLS_PDEAD  0x3C  /* player death explosion (type 60) */
#define CLS_BASE   0x50  /* base/structure damage (type 80 husk) */

static const u8 k_death_trans[90] = {
    0x00, 0x3C, 0x28, 0x13, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23,
    0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23,
    0x23, 0x23, 0x23, 0x23, 0x23, 0x28, 0x28, 0x27, 0x28, 0x28, 0x28, 0x28, 0x23, 0x23, 0x23, 0x23,
    0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x23, 0x3C, 0x23, 0x28, 0x28,
    0x28, 0x23, 0x23, 0x23, 0x28, 0x28, 0x50, 0x50, 0x28, 0x50, 0x50, 0x50, 0x50, 0x50, 0x50, 0x50,
    0x28, 0x50, 0x28, 0x28, 0x50, 0x50, 0x50, 0x50, 0x50, 0x50
};

/* Which entity_post leg runs on MSX (gates which AABB overlaps count). */
#define POST_SHOT  0x01  /* check_hit_shots 44F9 / shots-only 44CA / full 44BA */
#define POST_SHIP  0x02  /* check_hit_player 44D4 / ship-only 44B0/44A6 / full */
#define POST_PICK  0x04  /* ship touch = pickup; handler restores player after 453E */
/* E14E: 44D4 AND 0x01 (fire vs 44BA/44A6); 44F9 BIT 1 (fire vs 44F9/44CA). */

static u8 slot_msx_type(const Slot *e)
{
    u8 k = e->kind;
    u8 v = e->variant;

    if (k == KIND_EBULLET || k == KIND_BOX || k == KIND_LUSTER || k == KIND_SIG
        || k == KIND_GROUND || k == KIND_WIDE || k == KIND_FIREBOX
        || k == KIND_STEALTH || k == KIND_GUN || k == KIND_UMBER
        || k == KIND_VEYBAR || k == KIND_SWOOP || k == KIND_GSWOOP
        || k == KIND_TRACKER || k == KIND_PAIRDESC || k == KIND_BASE
        || k == KIND_DESCEND || k == KIND_TERUZO)
    {
        if (v)
            return v;
    }
    if (k == KIND_FIREUP) return 83;
    if (k == KIND_HUSK) return 80;
    if (k == KIND_ORB) return 72;
    if (k == KIND_CHIP) return 63;
    if (k == KIND_RISER) return 62;
    if (k == KIND_SPAWNER) return (v ? v : 69);
    return k;
}

static u8 death_class(u8 t)
{
    t &= 0x7F;
    if (t >= 90)
        return CLS_EXPL;
    return k_death_trans[t];
}

/* MSX post-path by type (confirmed handlers). Default = full 44BA. */
static u8 post_flags(u8 t)
{
    t &= 0x7F;
    /* 44B0 ship-only pickups: remap then restore player */
    if (t == 62 || t == 63 || t == 72 || t == 83)
        return (u8)(POST_SHIP | POST_PICK);
    /* 44A6 ship-only hostiles - player shots pass through.
     * Scoped to KIND_EBULLET in enemy_takes_shots (not bare type id). */
    if (t == 20 || t == 37 || t == 38 || t == 41 || t == 42 || t == 43)
        return POST_SHIP;
    /* no entity_post: spawners, explosion, husk, marker, clear */
    if (t == 11 || t == 69 || t == 35 || t == 60 || t == 80 || t == 39 || t == 40 || t == 0)
        return 0;
    /* 44CA shots-only ground structures / bases / firebox / wide.
     * Type 44 is 44BA on MSX; Original mode still ignores ship AABB (44CA)
     * so the plane/husk never kills the player. */
    if (t == 44 || t == 69 || t == 70 || t == 71 || t == 81 || t == 82
        || (t >= 73 && t <= 79) || (t >= 84 && t <= 89))
        return POST_SHOT;
    /* full entity_post 44BA (airborne, type21/36/44/45, guns, ...) */
    return (u8)(POST_SHOT | POST_SHIP);
}

/* Shot AABB gate. 44A6 leads/fragments are unshootable only as KIND_EBULLET.
 * Type 21/45 light bars are also KIND_EBULLET but use 44BA (shootable).
 * Non-bullet kinds still take shots if type-id glitched into ship-only. */
static int enemy_takes_shots(const Slot *e)
{
    u8 et = slot_msx_type(e);
    u8 pf = post_flags(et);

    if (e->kind == KIND_BOX && !e->clock)
        return 0;              /* 782c: no entity_post until SET 7 */
    if ((e->kind == KIND_WIDE || e->kind == KIND_FIREBOX) && !e->armed)
        return 0;              /* 8f25: CF / uninit, skip 44CA */
    if (e->kind == KIND_BASE && !e->armed)
        return 0;              /* 8a5a: RET Z until E150.1 SET 7 */
    if (e->kind == KIND_BASE && e->variant == 79 && (e->aux & 0x02))
        return 0;              /* 8bb6 dying: no 44CA */
    if (e->kind == KIND_CIRCLE && !(e->aux & 0x40))
        return 0;              /* 83ee: idle XOR only, no 44BA */
    /* Ground / base structures are always shootable (MSX 44CA leg). */
    if (e->kind == KIND_GROUND || e->kind == KIND_GUN
        || e->kind == KIND_WIDE || e->kind == KIND_FIREBOX
        || e->kind == KIND_BASE)
        return 1;
    if (pf & POST_PICK)
        return 0;
    if (!pf)
        return 0;
    if (e->kind == KIND_EBULLET
        && (et == 20 || et == 37 || et == 38 || et == 41 || et == 42 || et == 43))
        return 0;
    if (pf & POST_SHOT)
        return 1;
    if (e->kind != KIND_EBULLET && e->kind != KIND_CHIP && e->kind != KIND_ORB
        && e->kind != KIND_FIREUP && e->kind != KIND_RISER
        && e->kind != KIND_EXPL && e->kind != KIND_HUSK
        && e->kind != KIND_SPAWNER)
        return 1;
    return 0;
}

/* Fire vs enemy. 44F9 BIT 1,E14E after the three shot slots; 44D4 AND 1
 * before the ship check. 44CA is 44F9 only; 44A6 is 44D4 only; 44BA is both.
 * Type 44 is 44BA on MSX — ship AABB skip (KIND_GROUND) is the leave-alone. */
static int enemy_takes_fire(const Slot *e)
{
    u8 et = slot_msx_type(e);
    u8 pf = post_flags(et);
    u8 mode = player_fire_mode();

    if (e->kind == KIND_BOX && !e->clock)
        return 0;
    if ((e->kind == KIND_WIDE || e->kind == KIND_FIREBOX) && !e->armed)
        return 0;
    if (e->kind == KIND_BASE && !e->armed)
        return 0;
    if (e->kind == KIND_BASE && e->variant == 79 && (e->aux & 0x02))
        return 0;
    if (e->kind == KIND_CIRCLE && !(e->aux & 0x40))
        return 0;
    if (pf & POST_PICK)
        return 0;
    if (!pf)
        return 0;
    /* 44A6: type 20/37/38/41 + 42/43 after they become 0xA5/0xA6. */
    if (e->kind == KIND_EBULLET
        && (et == 20 || et == 37 || et == 38 || et == 41 || et == 42 || et == 43))
        return (mode & 0x01) != 0;
    /* 44CA: 8806 wide/idol/firebox, 8b7a base. Type 44 is 44BA (not here). */
    if (et == 70 || et == 71 || et == 81 || et == 82
        || (et >= 73 && et <= 79) || (et >= 84 && et <= 89))
        return (mode & 0x02) != 0;
    /* 44BA (airborne, type 44, guns, 21/45): bit0 via 44D4 or bit1 via 44F9.
     * fire_init_table E14E is 0x01/0x02/0x03, so every fire_num hits. */
    return 1;
}

static void apply_dir(Slot *e, u8 dir)
{
    e->vx = k_dir_vx[dir & 15];
    e->vy = k_dir_vy[dir & 15];
}

static s16 clamp16(s16 v, s16 lo, s16 hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static void alc_recompute(void)
{
    u16 pos;
    u8 half;
    u8 de;
    u8 off;
    u8 count;
    u8 idx;
    u8 r;

    /* update_spawn_table_ptr 0xBE27:
     * A = E12E + E132, sat 0xFF, clamp 0xA0 -> 0x9F.
     * DE = (A>>1) & 0x7E -> BE7C pair {offset, count};
     * E135 clamp if >= count; E136 = count;
     * timer from BE76[A>>5]; E133 = BECC + offset. */
    pos = (u16)s_spawn_pos_hi + (u16)s_e132;
    if (pos > 0xFF)
        pos = 0xFF;
    if (pos >= 0xA0)
        pos = 0x9F;
    half = (u8)(pos >> 1);
    de = (u8)(half & 0x7E);
    if (de + 1u >= SPAWN_PAIR_LEN)
        de = (u8)(SPAWN_PAIR_LEN - 2);
    off = spawn_pair_table[de];
    count = spawn_pair_table[de + 1];
    if (s_e135 >= count)
        s_e135 = 0;
    s_e136 = count;
    s_spawn_base = off;
    idx = (u8)(half >> 4);          /* pos >> 5 */
    if (idx >= SPAWN_TIMER_LEN)
        idx = SPAWN_TIMER_LEN - 1;
    r = spawn_timer_ramp[idx];
    /* BE27 writes both E137 (live) and E138 (reload). reload 0 would
     * DEC-wrap to 255 on MSX; keep a 255-frame stall. */
    s_spawn_reload = r ? r : 255;
    s_spawn_timer = s_spawn_reload;
}

static void spawn_pos_add(u8 n)
{
    /* BF7A lo half: E12F += n; on carry INC E12E sat 0xFF (silent, no
     * sticky bit0). Caller does BF8C INC E142. Slice chase is sticky
     * bit0-only via BE27 from dec/inc_encounter_a / cmd12 / shot carry. */
    u16 lo = (u16)s_spawn_pos_lo + n;
    s_spawn_pos_lo = (u8)lo;
    if (lo > 0xFF)
    {
        s_spawn_pos_hi++;
        if (!s_spawn_pos_hi)
            s_spawn_pos_hi--;
    }
}

static void apply_dir_88(Slot *e, u8 dir, u8 speed);

static void teruzo_step(Slot *e)
{
    /* 7b55-7b78: every 8f read dir from script; set_velocity_from_dir
     * speed +17=4. Preserve X/Y fracs (Original only writes vel words). */
    u8 si = e->variant & 3;
    u8 idx = e->aux;
    u8 d;
    u8 xf;
    u8 yf;

    if (idx >= tz_dir_n[si])
        idx = (u8)(tz_dir_n[si] - 1);
    d = tz_dirs[si][idx];
    xf = e->script;
    yf = e->timer;
    apply_dir_88(e, d, 4);
    e->script = xf;
    e->timer = yf;
    if (!(d & 0x80) && (u8)(idx + 1) < tz_dir_n[si])
        e->aux = (u8)(idx + 1);
}

static void spawn_duster(Slot *e)
{
    /* handler_type10_duster 0x7a2a.
     * 8.8 packing matches type20/26: dest=Xvel, bind=Yvel,
     * script=Xfrac, timer=Yfrac. aux=+0x14 X-home tgt.
     * +0c=0x13 Y|X motion|X_homing; Yvel 0x0300; +16=8, +17=1.
     * +03=0x58 +04=0x89 (EC). */
    u8 r1 = rnd();
    u8 r2 = rnd();
    u8 x;

    e->kind = KIND_DUSTER;
    e->variant = 0;
    e->hp = 1;
    e->ground = 0;
    /* random_x_pos 71c5: X=(H&0x7f)+(L&0x1f)+0x28, Y=0 */
    x = (u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28);
    e->x = (s16)x;
    e->y = 0;
    e->vx = 0;
    e->vy = 0;
    e->dest = 0;            /* Xvel 8.8 start 0 */
    e->bind = 0x0300;       /* Yvel 8.8: vy=3 vy_frac=0 */
    e->script = 0;          /* X frac */
    e->timer = 0;           /* Y frac */
    /* +0x14: X<0x88 -> 0xFF else 0x00 (drift toward opposite edge) */
    e->aux = (x < 0x88) ? 0xFF : 0x00;
    e->clock = 0;
    e->alive = 1;
    e->sat_col = 0x89;          /* 7a48 +04; TMS EC bit7, nibble 9 */
    spr_place(e, FRAME_DUSTER);
    marker_place(e, FRAME_DUSTER_C);  /* spawn_col_marker SAT 0x5C */
}

static void duster_step(Slot *e)
{
    /* entity_update 4898 +0c=0x13: X_homing then Y/X 8.8 motion.
     * X_homing_sub 496B: tgt=aux(+14), accel=+16=8, B=+17=1.
     * Motion+cull is step_88_4898 in update_enemies. */
    u16 xvel = e->dest;

    if ((u8)e->x != e->aux)
    {
        if ((u8)e->x < e->aux)
            xvel = (u16)(xvel + 0x0008);
        else
            xvel = (u16)(xvel - 0x0008);
    }
    e->dest = xvel;
}

static void spawn_luster(Slot *e, u8 type)
{
    /* handler_type16 0x7beb / type17 0x7c8a / type18 0x7cb3.
     * Shared 7c05: SAT 0x74 / marker 0x7C, Yvel 0x0200, Y=0.
     * 8.8 packing matches type10 duster: dest=Xvel, bind=Yvel,
     * script=Xfrac, timer=Yfrac. aux=+14 X-home tgt; clock=+1d.
     * 16/17->38 dir +1d; 18->37 aim. 8ddb copies parent XY. */
    u8 right = rnd() & 1;

    e->kind = KIND_LUSTER;
    e->variant = type;
    e->hp = 1;
    e->ground = 0;
    e->bind = 0x0200;       /* Yvel 8.8: +09=2 */
    e->script = 0;          /* X frac */
    e->timer = 0;           /* Y frac */
    e->y = 0;
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    if (type == 18)
    {
        /* +0c=0x13; +16=0x0e; +17=2; +1d=0x30; C=0x8B;
         * DE=60ff / HL=9000; 7c32: +14=E, Xvel 03/FD from RRC E. */
        e->x = right ? 0x90 : 0x60;
        e->dest = right ? 0x0300 : 0xFD00;
        e->aux = right ? 0x00 : 0xFF;   /* +14 X-home tgt */
        e->clock = 0x30;                /* +1d fire */
        e->sat_col = 0x8B;
    }
    else if (type == 17)
    {
        /* +0c=0x13; Xvel 0xFC00; +16=0x40; +17=4; +1e=0xE0;
         * DE=3001 / HL=B007; +1d=E; +14=D spawn X. C=0x8E. */
        e->x = right ? 0xB0 : 0x30;
        e->dest = 0xFC00;
        e->aux = (u8)e->x;              /* +14 = spawn X */
        e->clock = right ? 7 : 1;       /* +1d dir for type38 */
        e->sat_col = 0x8E;
    }
    else
    {
        /* type16: +0c=0x01 Y-only; +1e=0xC0; DE=4001 / HL=B007.
         * +1d=E dir. C=0x8E. */
        e->x = right ? 0xB0 : 0x40;
        e->dest = 0;
        e->aux = 0;
        e->clock = right ? 7 : 1;       /* +1d dir for type38 */
        e->sat_col = 0x8E;
    }
    /* 7c14: all three start SAT 0x74 / marker 0x7C. 16/17 sat_col
     * remaps A-frame baked 0xB -> 0xE. */
    spr_place(e, FRAME_LUSTER_A);
    marker_place(e, FRAME_LUSTER_A_C);
}

static void spawn_teruzo(Slot *e, u8 type)
{
    /* MSX: (type & ~1) + random bit picks one of the four corner scripts.
     * 7b37 +0c=3 X|Y; 7b49 +17=4; 7b41 +1f=1; 7b45 +18=0. */
    u8 pair = (u8)((type & 0xFE) == 14 ? 2 : 0);
    u8 si = (u8)(pair + (rnd() & 1));

    e->kind = KIND_TERUZO;
    e->variant = si;
    e->hp = 1;
    e->aux = 0;                 /* +0x18 script index */
    e->clock = 1;               /* +0x1F=1 first dir next frame */
    e->x = tz_yx[si][1];
    e->y = tz_yx[si][0];
    e->dest = 0;                /* Xvel 8.8 */
    e->bind = 0;                /* Yvel 8.8 */
    e->script = 0;              /* X frac */
    e->timer = 0;               /* Y frac */
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    e->sat_col = tz_col[si];
    spr_place(e, FRAME_TERUZO);
    marker_place(e, FRAME_TERUZO_C);  /* spawn_col_marker SAT 0x64 */
}

static void spawn_box(Slot *e, u8 type, s16 x, s16 y, u8 sat_cd)
{
    /* handler_type4_box 0x7826 (types 4/5/6 share): +03 is SAT countdown
     * until DEC hits 0, then spawn_col_marker, HP5, SAT 0xD4/0x8F,
     * Yvel 8.8 00C0 (7841 writes +08 only; +09 leftover 0), SET 7.
     * Hidden/unhitable until then (no entity_post).
     * Stream leftover SAT=0 wraps 255 on first DEC. */
    e->kind = KIND_BOX;
    e->variant = type;
    e->hp = 0;
    e->ground = 0;
    e->x = x;
    e->y = y;
    e->vx = 0;
    e->vy = 0;
    e->dest = 0;
    e->bind = 0;                /* Yvel armed at 782c reveal */
    e->script = 0;
    e->timer = 0;
    e->alive = 1;
    e->clock = 0;               /* 0 = countdown */
    e->sat = sat_cd;            /* +03 countdown, not hitbox yet */
    e->sat_col = 0;
    e->aux = 0;
    spr_detach(e);
}

/* 77e0: (bcd & 0x0F)*3 into proto_box type/SAT tables. */
static u8 proto_box_off(u8 bcd)
{
    u8 i = (u8)(bcd & 0x0F);
    u8 off = (u8)(i + (u8)(i << 1));
    if (off > 27)
        off = 27;
    return off;
}

static void spawn_chip_at(s16 x, s16 y)
{
    /* Free-spawn chip: Y-only 8.8 at 1.0 px/frame (prior integer vy=1).
     * Box-6 death converts in-place and keeps the box bind=0x00C0. */
    Slot *e = free_enemy();
    if (!e)
        return;
    e->kind = KIND_CHIP;
    e->variant = 0;
    e->hp = 1;
    e->ground = 0;
    e->x = x;
    e->y = y;
    e->vx = 0;
    e->vy = 0;
    e->dest = 0;
    e->bind = 0x0100;
    e->script = 0;
    e->timer = 0;
    e->alive = 1;
    spr_place(e, FRAME_CHIP);
    e->sat = 0x04;              /* pat 1; 7882 SAT name (hitbox 10x10) */
}

static void apply_dir_88(Slot *e, u8 dir, u8 speed);

/* handler_type56_sig_single @ 819d: 71c5 then E=4 join 81a8 (speed 5,
 * set_velocity_from_dir, +0c=3). Shares ROM 81a8 with type59. Dir 4 = down. */
static void spawn_sig(Slot *e)
{
    u8 r1 = rnd();
    u8 r2 = rnd();
    u8 x = (u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28);

    e->kind = KIND_SIG;
    e->variant = 56;
    e->hp = 1;
    e->ground = 0;
    e->x = (s16)x;
    e->y = 0;                   /* 71c5 Y=0; X column 0x28..0xC6 */
    apply_dir_88(e, 4, 5);      /* E=4; +0x17=5 -> set_velocity_from_dir */
    e->alive = 1;
    e->sat_col = 0x8F;           /* +04; XOR 0x09 each frame @ 81c3 */
    spr_place(e, FRAME_SIG);
}

static void spawn_ebullet_dir(s16 x, s16 y, u8 dir)
{
    Slot *e = free_enemy();
    if (!e)
        return;
    e->kind = KIND_EBULLET;
    e->variant = 37;  /* MSX type37 lead; dir is aim only (was mis-typed as type) */
    e->hp = 1;
    e->timer = 0;
    e->script = 0;
    e->x = x;
    e->y = y;
    apply_dir(e, dir);
    e->alive = 1;
    e->sat_col = 0x8F;          /* 84eb type37 +04; TMS EC bit7 */
    spr_place(e, FRAME_LEAD);
    /* 84fa RET: same first-visit skip as init_frag variant 37. */
    {
        u8 idx = (u8)(e - s_en);
        if (idx < ENEMY_SLOTS)
            s_ebullet_init_ret[idx] = 1;
    }
}

static void spawn_fireup(Slot *e)
{
    const ModeAssets *a = mode_assets();

    e->kind = KIND_FIREUP;
    e->variant = (u8)(s_fireup_seq & 7);  /* +0x1c weapon number 0-7 */
    s_fireup_seq++;
    e->hp = 1;
    e->timer = 0;
    e->script = 0;
    e->x = (s16)(24 + (rnd() % (a->playfield_w - 48)));
    e->y = (s16)(a->playfield_h - 24);
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    spr_place(e, FRAME_CIRCLE);
}

static u8 aim_4c91(s16 x, s16 y);

static void spawn_ground_fall(Slot *e, u8 type, s16 x, s16 y, u16 dest)
{
    /* handler_type44_ground_structure 0x82d0:
     * Stream: 71c5 X=(H&0x7f)+(L&0x1f)+0x28, Y=0 (aim origin / on-screen
     * time). Map-script entity_place_ground keeps its XY.
     * +0x17 = (R&3)+1; player_pos_snapshot 4c8b (= aim_4c91 +
     * set_velocity_from_dir 8.8); +0c=3 X|Y motion; +03=0x40 plane,
     * +04=0x83 cyan; spawn_col_marker SAT 0x44. Port: dest/bind/
     * script/timer 8.8 like type20/37; vx/vy 0 so shared pass inert. */
    u8 speed = (u8)((rnd() & 3) + 1);
    u8 sat = (u8)((dest & 0xFF) ? (dest & 0xFF) : 0x40);

    e->kind = KIND_GROUND;
    e->variant = type;
    e->hp = 3;
    e->ground = 0;              /* 82d0: entity_update 4898, not E700.1 Y+8 */
    e->dest = dest;
    e->x = x;
    e->y = y;
    e->alive = 1;
    apply_dir_88(e, aim_4c91(x, y), speed);
    e->sat_col = 0x83;               /* 82d0 +04 cyan; TMS EC bit7 */
    spr_place(e, FRAME_PLANE);       /* visual plane; hitbox from sat */
    e->sat = sat;
    marker_place(e, FRAME_PLANE_C);  /* spawn_col_marker SAT 0x44 */
}

/* Type 80: handler_type80 8e14. dest = +0x18 subtype for 849c (0 after 90dc). */
static void spawn_d1_child(Slot *e, s16 x, s16 y);

static void spawn_husk_at(Slot *e, s16 x, s16 y)
{
    e->kind = KIND_HUSK;
    e->variant = 80;
    e->hp = 0;
    e->timer = 0;
    e->script = 0;
    e->ground = 1;
    e->dest = 0;
    e->bind = 0;
    e->x = x;
    e->y = y;
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    spr_place(e, FRAME_BOX);
}

/* 8833: child 0xD1 = type 81 | bit7, HP 0, SAT name 0x24, parent XY.
 * No 88ed (8824/88c2 is type-81 death, not this spawn). 8f45 scroll-off.
 * 7904 BIT 7 skips the 880d dispatch; a 453e hit DECs 0->255 and restores. */
static void spawn_d1_child(Slot *e, s16 x, s16 y)
{
    e->kind = KIND_WIDE;
    e->variant = 81;
    e->hp = 0;
    e->timer = 0;
    e->script = 0;
    e->ground = 1;
    e->armed = 1;
    e->dest = 0;
    e->bind = 0;
    e->aux = 0;
    e->clock = 0;
    e->x = x;
    e->y = y;
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    e->sat = 0x24;
    e->sat_col = 0;
    spr_detach(e);
}

/* structure_award_index_table 0x4B29, types 0-89. 4a6a uses +0x18. */
static const u8 k_struct_award[90] = {
    0x00,0x00,0x00,0x00,0x07,0x07,0x07,0x06,0x06,0x07,0x04,0x04,0x06,0x06,0x06,0x06,
    0x07,0x07,0x08,0x00,0x02,0x01,0x07,0x07,0x07,0x07,0x08,0x08,0x08,0x08,0x06,0x06,
    0x08,0x08,0x08,0x00,0x09,0x02,0x02,0x02,0x00,0x03,0x03,0x03,0x02,0x03,0x06,0x06,
    0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x02,0x03,0x04,0x02,0x00,0x07,0x0F,0x0B,
    0x09,0x0A,0x0B,0x03,0x0B,0x0A,0x06,0x06,0x00,0x07,0x06,0x05,0x06,0x06,0x07,0x0A,
    0x00,0x13,0x06,0x00,0x08,0x09,0x09,0x07,0x07,0x08
};

/* 8eaf large_descender_color_table: type61 SAT (+04) + type83 +0x1d.
 * Type61: E149&7 index; if table==0x81 use 0x8F on SAT (8341). */
static const u8 k_fire83_color[8] = {
    0x81, 0x83, 0x84, 0x86, 0x87, 0x89, 0x8A, 0x8D
};

static void award_subtype(u8 t)
{
    u8 idx = 0;

    if (t < (u8)sizeof(k_struct_award))
        idx = k_struct_award[t];
    player_add_score(idx);
}

/* 880d leftover -> type 80. dest keeps +0x18 so 8e14 849c scores the source. */
static void become_husk(Slot *e, u8 orig)
{
    e->kind = KIND_HUSK;
    e->variant = 80;
    e->hp = 0;
    e->timer = 0;
    e->script = 0;
    e->ground = 1;
    e->dest = orig;
    e->vx = 0;
    e->vy = 0;
    /* 8e14 next tick: 849c arms 84d1. Do not invent FRAME_BOX.
     * Hide leftover body so the original sprite cannot ride VSCROLL. */
    if (e->spr)
        SPR_setVisibility(e->spr, HIDDEN);
}

/*
 * handler_type80 8e14:
 *   first frame (bit7 clear): bfb3, ev18, SET 7, +0x0c=0, JP 849c
 *     (score + 84bc E124/E125 + anim +0x0d/0e/0f/10 then entity_update)
 *   later: 8f45 scroll-off (Y>=0xD0 -> bfab + clear); +0x0f ? 4898 : 48d0
 *
 * 8e2a JP 849c is the same tail as type35 after 8498. There is no
 * skip of 84bc: a husk DECs E124 and may latch E125 for BFA0 type 44.
 */
static void entity_inc_encounter_a(void);
static int step_8f45(Slot *e);
static int step_8f25_unarmed(Slot *e);

/* 84bc: DEC E124; Z -> E124=0x10, E125=1 (BFA0 type 44 next spawn_tick).
 * Shared by type35 8446 and type80 8e2a JP 849c. */
static void tick_e124_84bc(void)
{
    if (s_e124)
        s_e124--;
    if (!s_e124)
    {
        s_e124 = 0x10;
        s_e125 = 1;
    }
}

static void husk_step(Slot *e)
{
    if (!e->script)
    {
        /* 8e14: bfb3, ev18, SET 7, +0c=0, JP 849c (score + 84bc + 84d1).
         * 8f45 starts next tick (BIT 7 already set). */
        entity_dec_encounter_a();
        sound_play_event(SND_EV_EXPLODE);
        award_subtype((u8)e->dest);
        tick_e124_84bc();
        e->script = 1;
        e->ground = 1;
        e->vx = 0;
        e->vy = 0;
        /* 849c: +0D=1, +0E=4, +0F=1, +10=6, table 84d1, then 84c9 4898. */
        e->clock = 1;
        e->aux = 1;
        anim_sub_4912(e, k_t35_sat, k_t35_col, 6, 4);
        return;
    }
    if (step_8f45(e))
        return;

    /* 8e30: +0x0f NZ -> 4898 anim_sub; else 48d0. Wrap +0f>=+10 -> 0. */
    if (!e->aux)
    {
        spr_kill(e);
        return;
    }
    anim_sub_4912(e, k_t35_sat, k_t35_col, 6, 4);
}

/* LAB_ram_8f45: E700.1 then unsigned Y+=8; CP 0xD0 NC -> bfab + 48d0.
 * SCF on entry is the 8f25 armed "busy" flag (87ae JR C skips init). */
static int step_8f45(Slot *e)
{
    u8 ny;
    u8 next;

    if (!map_script_row_carry())
        return 0;
    ny = (u8)e->y;
    next = (u8)(ny + 8);
    e->y = (s16)next;
    if (next < 0xD0)
        return 0;
    entity_inc_encounter_a();
    spr_kill(e);
    return 1;
}

/* 8f25 unarmed: E700.1, Y+=8, RET NC; wrap -> SET 7, Y+=0x10. Returns 1 if
 * still unarmed (caller skips the rest of the handler). */
static int step_8f25_unarmed(Slot *e)
{
    u8 ny;
    u8 next;

    if (!e->armed)
    {
        if (map_script_row_carry())
        {
            ny = (u8)e->y;
            next = (u8)(ny + 8);
            e->y = (s16)next;
            if (next < ny)
            {
                e->armed = 1;
                e->y = (s16)(u8)(next + 0x10);
                return 0;
            }
        }
        return 1;
    }
    return 0;
}

/* base_core_anim 0x8a16: (SAT name, color) x4 yellow, then 0x8a1e black.
 * Names 0x1C/0x20/0x24/0x20 = lead / med_circle / lg_circle / med_circle. */
/* 8a16 SAT names only (lead / med / lg / med). Do not walk into other
 * FRAME_* indices. FRAME_MED_CIRCLE is pat 8 baked TMS 15 (same as
 * lead/lg). 8a16 colors 8F/83/8A/8B stay in the table; mid 0x83 uploads
 * as k_orb_mid_pal (PAL2[7] cyan) so it does not hit dim PAL2[3]. */
static const u8 k_orb_sat[4] = { 0x1C, 0x20, 0x24, 0x20 };
static const u8 k_orb_frame[4] = {
    FRAME_LEAD, FRAME_MED_CIRCLE, FRAME_CIRCLE, FRAME_MED_CIRCLE
};
static const u8 k_orb_yel_col[4] = { 0x8F, 0x83, 0x8A, 0x8B };
static const u8 k_orb_blk_col[4] = { 0x81, 0x81, 0x81, 0x81 };

/*
 * handler_type72_base_core 0x8983:
 *   first: Yvel=0xFFF8, +0x0c=5, anim 8a16 (4 frames / reload 4),
 *          +0x1e=4, +0x1f=+0x18 (70/71)
 *   each: if +0x1e: DEC +0x1b; on 0, DEC +0x1e; on 0:
 *           +0x1f==0x46 (70) -> 48d0
 *           else anim 8a1e, Yvel lo=0xF0 (0xFFF0)
 *         4898, 44b0
 *   collect (bit7 cleared): player 0x81;
 *           +0x1e ? 8a26+ev19+48d0 : E722=+0x1c/1d, SET 5 E102, 48d0
 * Port: bind/timer = Yvel 8.8; clock=+0x1b; script=+0x1e; aux=anim tick
 *       (anim_sub +0E=4 via aux>>2). dest = warp ptr (+0x1c/1d).
 */
static void orb_step(Slot *e)
{
    u8 idx;

    /* 89bb: if +0x1e: DEC +0x1b; on 0 DEC +0x1e; on 0 branch. */
    if (e->script)
    {
        e->clock--;
        if (!e->clock)
        {
            e->script--;
            if (!e->script)
            {
                if (e->variant == 70)
                {
                    /* type 70 yellow expires; never turns black. */
                    spr_kill(e);
                    return;
                }
                /* 89d3: anim 8a1e, Yvel lo=0xF0 -> 0xFFF0. */
                e->bind = 0xFFF0;
            }
        }
    }

    /* 89df: 4898 Y_motion (+0c bit0). Unsigned wrap, CP 0xD0 clears. */
    if (step_88_y_4898(e))
        return;
    e->vx = 0;
    e->vy = 0;

    /* anim_sub 0x4912: +0E=4, table 8a16 then 8a1e. aux>>2 is that reload.
     * SAT names stay 8a16 (0x1C/0x20/0x24/0x20). k_orb_frame is the SAT
     * mapping (lead/med/lg/med). The hardware sprite is always the 16x16
     * FRAME_CIRCLE vehicle: SGDK BALANCED cuts FRAME_LEAD to an 8x8 that
     * shows only pat 7's UL tile (4 px shard). Pixels are k_japan_pat*. */
    idx = (u8)((e->aux >> 2) & 3);
    if (!e->spr || e->frame != FRAME_CIRCLE)
        spr_place(e, FRAME_CIRCLE);
    /* k_orb_frame is the SAT map (lead/med/lg/med == 1C/20/24/20). */
    e->sat = k_orb_sat[idx];
    if (k_frame_sat[k_orb_frame[idx]] != e->sat)
        e->sat = k_frame_sat[k_orb_frame[idx]];
    spr_set_sat_col(e, e->script ? k_orb_yel_col[idx] : k_orb_blk_col[idx]);
    e->aux++;
}

/*
 * handler_type83 8e3a black_shadow:
 *   first: +0x0c=1, Yvel=0xFFE0, type=0xD3, +0x1d=8eaf[+0x1c]
 *   each: +0x1b++, SAT 0x24/0x81 every 4th else 0x04/+0x1d, 4898, 44b0
 *   collect: player 0x81, +0x1b=0, E148-=5 sat 0, SET 7 player+5,
 *            48d0, bfc8, fire_select(+0x1c)
 * Port: bind/timer = Yvel 8.8 0xFFE0; clock=+0x1b; aux=+0x1d color;
 *       sat_col 0x81 blank (CIRCLE/0x24) vs weapon tint (CHIP/0x04).
 */
static void fireup_step(Slot *e)
{
    u8 flash;

    if (!e->script)
    {
        /* 8e40: +0c=1, Yvel=FFE0, type=D3, +1d=8eaf[+1c]. Falls into 8e5d. */
        e->script = 1;              /* init done (Xvel unused; dest=0) */
        e->ground = 0;
        e->vx = 0;
        e->vy = 0;
        e->dest = 0;                /* Xvel 8.8 */
        e->bind = 0xFFE0;           /* Yvel 8.8: -0.125 px/frame */
        e->timer = 0;               /* Y frac */
        e->clock = 0;               /* +0x1b flash phase */
        e->aux = k_fire83_color[e->variant & 7]; /* +0x1d weapon tint */
    }

    /* 8e5d: A=+0x1b; INC +0x1b; AND 3 -> 0: pat 0x24/col 0x81 else 0x04/+0x1d */
    flash = e->clock;
    e->clock = (u8)(flash + 1);
    if ((flash & 3) == 0)
    {
        spr_place(e, FRAME_CIRCLE); /* SAT 0x24 lg_circle */
        spr_set_sat_col(e, 0x81);   /* blank/black flash */
    }
    else
    {
        spr_place(e, FRAME_CHIP);   /* pat 1 SAT 0x04 */
        e->sat = 0x04;              /* 8e5d SAT name for hitbox */
        spr_set_sat_col(e, e->aux); /* weapon color from 8eaf */
    }

    /* 8e79: 4898 Y_motion (+0c=1). Unsigned wrap, CP 0xD0 clears. */
    if (step_88_y_4898(e))
        return;
    e->vx = 0;
    e->vy = 0;
}

static void spawn_wide_at(Slot *e, u8 type, s16 x, s16 y, u16 dest)
{
    u8 hp;

    /* 87c7: HP from type|0x80, not Y. <0xC8 -> 6 (70/71);
     * >=0xD7 -> 3 (87-89); else 4 (81/82/84-86). Type 82 stamps digit. */
    {
        u8 t80 = (u8)(type | 0x80);
        if (t80 < 0xC8)
            hp = 6;
        else if (t80 >= 0xD7)
            hp = 3;
        else
            hp = 4;
    }

    e->kind = (type == 82) ? KIND_FIREBOX : KIND_WIDE;
    e->variant = type;
    e->hp = hp;
    e->timer = 0;
    e->script = 0;
    e->ground = 1;
    e->armed = 0;               /* 8f25 BIT 7 clear until Y wrap */
    e->dest = dest;
    e->x = x;
    e->y = y;
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    /* 8EB7: +0x1c=3 / +0x1d=0x18 then JP 87c3. +0x1d is the 0x18 reload. */
    if (type >= 84 && type <= 86)
        e->timer = 3;
    /* Idol-class + type 82 firebox: stream stamps nametable art; MSX SAT name
     * 0x24 for hitbox size only, sat_color 0 (invisible). Type 82 also stamps
     * digit 0x30+(IX+0x1c) via 87e2/8948 (script=0 until stamped). Death:
     * 84-86 -> husk+88ab; 82/89 -> fire-up places spr like idol->orb. */
    e->sat = 0x24;  /* hitbox half 0,0 => 16x16 (k_col_size[0x12]) */
    if (type == 70 || type == 71 || type == 81 || type == 82
        || (type >= 84 && type <= 86)
        || type == 87 || type == 88 || type == 89)
    {
        /* Nametable-only. Release a reused SAT so a leftover flyer /
         * shot sprite cannot stay composited on the structure. */
        marker_kill(e);
        if (e->spr)
        {
            SPR_releaseSprite(e->spr);
            e->spr = NULL;
        }
        e->mspr = NULL;
        if (type == 82)
            e->script = 0;      /* 87e2 after 8f25 BIT 7 */
    }
    else
        spr_place(e, FRAME_CIRCLE);
}

static int spawn_proto_box(void)
{
    /* handler_type68 77a1: X=(H&0x3F)+0x38, +0x20 per child;
     * types from 77ea[(E104&0x0F)*3]; SAT countdown from 7808 after
     * nibble-swap(E105). Y left 0 (stream slot / 71c5 leftover). */
    u8 r = rnd();
    s16 x = (s16)((u8)((r & 0x3F) + 0x38));
    u8 type_off = proto_box_off(player_score_mid());
    u8 e105 = player_score_hi();
    u8 sat_off = proto_box_off((u8)((e105 << 4) | (e105 >> 4)));
    u8 i;

    for (i = 0; i < 3; i++)
    {
        Slot *e = free_enemy();
        if (!e)
            /* 77d9 CALL 4496 / 77dc RET C: children 2 and 3 are simply lost
             * when the table is full. Only the first slot decides the caller's
             * carry (BFA0 0x4496 / RET C), which is what keeps the E125 latch. */
            return i != 0;
        spawn_box(e, k_box_types[type_off + i], x, 0, k_box_sat[sat_off + i]);
        x = (s16)(x + 0x20);
    }
    return 1;
}


/* gun pair table 0x8189: flags, color, period, child type */
static const u8 k_gun[5][4] = {
    { 0x00, 0x8F, 32, 38 },
    { 0x40, 0x8D,  0, 21 },
    { 0x20, 0x8A, 80, 38 },
    { 0x00, 0x89, 32, 21 },
    { 0x20, 0x87, 46, 21 }
};

/* base_segment_table 0x8df1: sat_name, HP, y_off, x_off, motion.
 * MSX writes sat_name to +0x03 for hitbox size but never sets +0x04;
 * sat_color stays 0 (invisible). Visual is nametable tiles only.
 * 8ac7 xo/yo adjust SAT after 8948; 8c15 eyes stay on the bind cell. */
static const u8 k_base[7][5] = {
    { 0x20, 0x28, 0x00, 0x00, 0x7F },
    { 0x20, 0x14, 0x00, 0x00, 0x08 },
    { 0x1C, 0x0A, 0xFC, 0xFC, 0x06 },
    { 0x20, 0x14, 0xFC, 0x00, 0x0A },
    { 0x1C, 0x14, 0x00, 0xFC, 0x0A },
    { 0x20, 0x28, 0x00, 0x00, 0x0A },
    { 0x24, 0x63, 0x04, 0x04, 0x10 }
};

static const u8 k_stealth_x[4] = { 32, 208, 80, 160 };
/* 0x807C (X,dir) pairs: 20 02 / D0 06 / 50 04 / A0 04. 4cf7 dir 2 =
 * down-right (word0 Y=90, word1 X=90). Dir 0 is right, not down. */
static const u8 k_stealth_dir[4] = { 2, 6, 4, 4 };
/* 0x8084: player Y < entity Y. 0x8087: player Y >= entity Y. 16-dir volley. */
static const u8 k_volley_hi[3] = { 0x0C, 0x0A, 0x0E };
static const u8 k_volley_lo[3] = { 0x04, 0x02, 0x06 };
/* 0x808A type 66 bit0: five (Y,X) offsets, last pair is the 00 00 tail. */
static const s8 k_volley_66[5][2] = {
    {  24,   0 },
    {   0, -24 },
    {   0,  24 },
    { -24,   0 },
    {   0,   0 }
};

static u8 s_base_left;
static u8 s_e150;           /* base_encounter_flags */
static u8 s_desc_cycle;
static u8 s_pat_rr;         /* E717 base_attack_cursor, 0-7 */

static void spawn_frag(s16 x, s16 y, u8 dir, u8 variant);

static void spawn_child_dir(s16 x, s16 y, u8 stype, u8 dir)
{
    if (stype == 21)
    {
        /* type 21 light_bar: shared spawn_frag (speed 4 + ev0x16). */
        spawn_frag(x, y, dir, 21);
        return;
    }
    if (stype == 38)
    {
        /* type 38 burst_fragment: 8507 +0x17=3, real variant (not dir). */
        spawn_frag(x, y, dir, 38);
        return;
    }
    spawn_ebullet_dir(x, y, dir);
}

static void box_step(Slot *e)
{
    /* entity_update 4898 Y_motion (+0c=1): 8.8 via bind/timer;
     * shared pass inert. Types 4/5/6 share handler_type4_box.
     * First-frame 782c: DEC +03, RET NZ (no move / no SAT / no hit). */
    if (e->kind == KIND_BOX && !e->clock)
    {
        e->sat--;
        if (e->sat)
            return;
        e->hp = 5;                  /* +0x19 = 5 */
        e->bind = 0x00C0;           /* 7841 +08=0xC0; +09 leftover 0 */
        e->clock = 1;
        e->sat_col = 0x8F;          /* +04 */
        spr_place(e, FRAME_BOX);    /* +03=0xD4 */
        marker_place(e, FRAME_BOX_C);
        /* 784d entity_update same frame after SET 7 */
    }
    /* Reveal writes SAT once. If addSprite failed (VRAM/slot leak),
     * retry -- Japan 71da/784d still occupy the type-4/5/6 slot. */
    if (e->clock)
    {
        if (!e->spr)
            spr_place(e, FRAME_BOX);
        if (e->spr && !e->mspr)
            marker_place(e, FRAME_BOX_C);
    }

    /* 784d CALL 4898 +0c=1: unsigned 8.8 + Y>=0xD0.
     * Signed s32 + playfield max_y=200 killed Y=201..207. */
    if (step_88_y_4898(e))
        return;
    e->vx = 0;
    e->vy = 0;
}

/* 0x78af handler_type63_power_chip: Y 8.8 only. No box frame, no SAT blink. */
static void chip_step(Slot *e)
{
    /* 78af CALL 4898 +0c=1: unsigned 8.8 + Y>=0xD0.
     * Box-6 convert keeps bind=0x00C0; signed s32 + max_y=200
     * killed Y=201..207. */
    if (step_88_y_4898(e))
        return;
    e->vx = 0;
    e->vy = 0;
}

/* 0x7882: in-place type 63; SAT 0x04 / color 0x8F / pattern chip. */
static void become_chip(Slot *e)
{
    marker_kill(e);
    e->kind = KIND_CHIP;
    e->variant = 0;
    e->hp = 1;
    e->ground = 0;
    e->vx = 0;
    e->vy = 0;
    e->clock = 1;
    e->sat_col = 0x8F;
    spr_place(e, FRAME_CHIP);
    e->sat = 0x04;              /* 7882 SAT 0x04 after name write */
}

static void spawn_gun(Slot *e, u8 type)
{
    /* handler_type46_ground_projectiles 0x8094.
     * 8.8 packing matches type20/26-29/30: dest=Xvel, bind=Yvel,
     * script=Xfrac, timer=Yfrac. aux=ang|side(0x10)|latch(0x40);
     * clock=+0x18 fire countdown. Period/stype/flags from k_gun via
     * variant. 8094 writes X=0x30/0xC0, never +01: stream leftover Y=0.
     * Do not touch type41/45 aux/clock beyond this kind. */
    u8 pair = (u8)(((type - 46) & 0xFE) >> 1);
    u8 flags;
    u8 period;
    u8 right = rnd() & 1;

    if (pair > 4)
        pair = 4;
    flags = k_gun[pair][0];
    period = k_gun[pair][2];

    e->kind = KIND_GUN;
    e->variant = type;
    e->hp = 1;
    e->ground = 0;              /* 8094 +0c=1: 4898 Y 8.8, not 8f25 */
    e->x = right ? 0xC0 : 0x30;
    e->y = 0;               /* 8094 leaves +01; stream Y=0 */
    e->vx = 0;
    e->vy = 0;
    e->dest = 0;            /* Xvel 8.8 (Y-only) */
    e->bind = 0x0150;       /* Yvel 8.8: vy=1 vy_frac=0x50 */
    e->script = 0;          /* X frac */
    e->timer = 0;           /* Y frac */
    e->alive = 1;
    e->clock = period ? period : 1;
    if (flags & 0x20)
        e->aux = (u8)(12 | (right ? 0x10 : 0));
    else
        e->aux = right ? 8 : 0;
    e->sat_col = k_gun[pair][1];    /* +04 from gun pair table */
    spr_place(e, FRAME_LOGA);       /* +03=0x48 pat 18 */
    marker_place(e, FRAME_LOGA_B);  /* spawn_col_marker SAT 0x50 pat 20 */
}

static void gun_fire(Slot *e)
{
    u8 pair = (u8)(((e->variant - 46) & 0xFE) >> 1);
    u8 stype;
    u8 dir = e->aux & 15;

    if (pair > 4)
        pair = 4;
    stype = k_gun[pair][3];
    /* 816d: +03=0x4C pat 19 on the PRIMARY (keeps +04 colour), marker
     * +03=0x54 pat 21 colour 0x81. Not a black-on-black flash -- Japan
     * shows the fire pose as coloured pat 19 over black pat 21. */
    spr_place(e, FRAME_LOGA_C);
    marker_place(e, FRAME_LOGA_D);
    /* 816d -> 8ddb: copy parent Y/X. Japan v1 loga A|B peak is SAT
     * (X+8,Y) — first set row of pat 18|20 is y=0 xs mid 8. SAT origin
     * is the top-left vertex; spawn from the peak so shots leave the
     * diamond tip, not a corner. */
    spawn_child_dir((s16)(e->x + 8), e->y, stype, dir);
}

static void gun_step(Slot *e)
{
    u8 pair = (u8)(((e->variant - 46) & 0xFE) >> 1);
    u8 flags;
    s32 ypos;

    if (pair > 4)
        pair = 4;
    flags = k_gun[pair][0];

    if (flags & 0x40)
    {
        /* Y-track: fire once when player crosses above, clear latch below. */
        u8 above = (u8)(player_y() < e->y);

        if (e->aux & 0x40)
        {
            if (!above)
                e->aux = (u8)(e->aux & 0xBF);
        }
        else if (above)
        {
            gun_fire(e);
            e->aux = (u8)(e->aux | 0x40);
        }
    }
    else
    {
        if (e->clock)
            e->clock--;
        if (!e->clock)
        {
            u8 period = k_gun[pair][2];
            u8 ang = e->aux & 15;

            if (flags & 0x20)
            {
                s8 step = (e->aux & 0x10) ? -1 : 1;
                ang = (u8)((ang + step) & 15);
                e->aux = (u8)((e->aux & 0x70) | ang);
            }
            e->clock = period ? period : 32;
            gun_fire(e);
            if (flags & 0x20)
            {
                if (ang == 4)
                {
                    /* Sweep done: reset ang=12, resume Y motion.
                     * 8155: restore +03=0x48 loga_A. */
                    e->aux = (u8)((e->aux & 0x70) | 12);
                    e->bind = 0x0150;
                    e->clock = period ? period : 32;
                    spr_place(e, FRAME_LOGA);  /* restore +03=0x48 */
                    marker_place(e, FRAME_LOGA_B); /* 8162 marker 0x50 */
                }
                else
                {
                    /* Mid-sweep: rapid fire, pause fall (+0c=0). */
                    e->clock = 1;
                    e->bind = 0;
                }
            }
        }
    }

    /* entity_update 4898 Y_motion: 8.8 via bind/timer; shared pass inert. */
    ypos = ((s32)e->y << 8) | (u8)e->timer;
    ypos += (s16)e->bind;
    e->timer = (u8)ypos;
    e->y = (s16)(ypos >> 8);
    e->vx = 0;
    e->vy = 0;
    /* 4898 Y_motion_sub CP 0xD0 (unsigned). */
    if ((u8)e->y >= 0xD0)
        spr_kill(e);
}

/* LAB_ram_4c91 / dir_remap_table 0x4D45. 16-dir aim; E returned as dir. */
static u8 aim_4c91(s16 x, s16 y)
{
    static const u8 k_thr[3] = { 0x32, 0x6A, 0xAB };
    static const u8 k_remap[32] = {
        0x02, 0x03, 0x03, 0x04, 0x0E, 0x0D, 0x0D, 0x0C,
        0x06, 0x05, 0x05, 0x04, 0x0A, 0x0B, 0x0B, 0x0C,
        0x02, 0x01, 0x01, 0x00, 0x0E, 0x0F, 0x0F, 0x00,
        0x06, 0x07, 0x07, 0x08, 0x0A, 0x09, 0x09, 0x08
    };
    s16 dy = (s16)(player_y() - y);
    s16 dx = (s16)(player_x() - x);
    u16 ady;
    u16 adx;
    u16 lo;
    u16 hi;
    u8 flags = 0;
    u8 b;
    u8 i;
    u8 ratio;

    if (dy < 0)
    {
        dy = (s16)-dy;
        flags |= 0x04;
    }
    if (dy == 0)
        dy = 1;
    ady = (u16)dy;
    if (dx < 0)
    {
        dx = (s16)-dx;
        flags |= 0x08;
    }
    if (dx == 0)
        dx = 1;
    adx = (u16)dx;
    if (adx >= ady)
    {
        flags |= 0x10;
        lo = ady;
        hi = adx;
    }
    else
    {
        lo = adx;
        hi = ady;
    }
    /* Z80 div_hl_e of (lo<<8)/hi; L is the low byte (256 -> 0 at 45 deg). */
    ratio = (u8)(((u16)lo << 8) / hi);
    b = 3;
    for (i = 0; i < 3; i++)
    {
        if (ratio < k_thr[i])
            break;
        b--;
    }
    return k_remap[(b | flags) & 31];
}


/* handler_type20 0x8668 Xvel: one prng_next -> H/L; dest=Xvel 8.8, script=Xfrac.
 * Packs like apply_dir_88 (dest/bind/script/timer); +0c flags are step-side only.
 * Does not touch aux/clock (type41/45) or parent type65/umber fields. */
static void type20_init_vel(Slot *e)
{
    u16 r;
    s8 xhi;

    s_rng = (u16)(s_rng * 2053 + 13849);
    r = s_rng;
    xhi = (s8)(((r >> 8) & 3) - 2);
    e->dest = (u16)(((u16)(u8)xhi << 8) | (u8)r);
    e->script = 0;          /* X position frac (IX+07) */
    e->bind = 0;            /* Yvel 8.8 (IX+08/09), start 0 */
    e->timer = 0;           /* Y position frac (IX+06) */
    e->vx = 0;
    e->vy = 0;
}

/* handler_type20_lead_homing 0x8668 first frame:
 *   +0c=0x0B (Y_motion|X_motion|Y_homing), +13=0xFF tgt, +15=0x0C accel, +17=1,
 *   Xvel.hi=(R&3)-2, Xvel.lo=L (full 8.8). Ongoing: entity_update then 44a6. */
static void spawn_lead20(s16 x, s16 y)
{
    Slot *c = free_enemy();

    if (!c)
        return;
    c->kind = KIND_EBULLET;
    c->variant = 20;
    c->hp = 1;
    c->ground = 0;
    c->x = x;
    c->y = y;
    /* 8668: +03=0x1C +04=0x8F, +0c=0x0B, +13=0xFF, +15=0x0C, +17=1;
     * Xvel 8.8 from one R. */
    type20_init_vel(c);
    c->alive = 1;
    c->sat_col = 0x8F;          /* 8672 +04; TMS EC bit7 */
    spr_place(c, FRAME_LEAD);
}

/* handler_type59 @ 0x8269: dir=+0x1a&0x0F; JP 81a8 (speed 5,
 * set_velocity_from_dir, +0c=3 X|Y). Shared SAT 0x70 with type56. */
static void init_type59(Slot *c, s16 x, s16 y, u8 dir)
{
    c->kind = KIND_SIG;
    c->variant = 59;
    c->hp = 1;
    c->ground = 0;
    c->x = x;
    c->y = y;
    apply_dir_88(c, (u8)(dir & 15), 5);
    c->alive = 1;
    c->sat_col = 0x8F;              /* shared 81c3 XOR 0x09 with type56 */
    spr_place(c, FRAME_SIG);
}

static void spawn_sideways59(s16 x, s16 y, u8 dir)
{
    Slot *c = free_enemy();

    if (!c)
        return;
    init_type59(c, x, y, dir);
}

static void spawn_stealth(Slot *e, u8 type)
{
    u8 si = (u8)((rnd() & 6) >> 1);

    e->kind = KIND_STEALTH;
    e->variant = type;
    /* +0x19 = 7; type 65 (0xC1) overrides to 4. Type 34 keeps 7. */
    e->hp = (type == 65) ? 4 : 7;
    e->ground = 0;
    e->x = k_stealth_x[si];
    e->y = 0;               /* 7f99 leaves +01; stream leftover Y=0 (top) */
    /* 7f99: +17=1 set_velocity_from_dir, +0c=3 X|Y 8.8.
     * script/timer = X/Y fracs; variant==66 stands in for +05 bit0. */
    apply_dir_88(e, k_stealth_dir[si], 1);
    e->alive = 1;
    /* 7fc9/7fcd: +0D/+1D = 0x30. Type 65 7ff0 writes +0D=0x20 only;
     * +1D stays 0x30. Port clock=+1d first countdown. Reload in stealth_step. */
    e->clock = 48;
    /* 7fc5 +04=0x88; 7fec type65 0x85; 8002 type66 0x8b. Solid SAT. */
    if (type == 65)
        e->sat_col = 0x85;
    else if (type == 66)
        e->sat_col = 0x8B;
    else
        e->sat_col = 0x88;          /* type 34 (0xA2) keeps 0x88 */
    spr_place(e, FRAME_STEALTH);      /* sat 0xCC pat 51 */
    marker_place(e, FRAME_STEALTH_C); /* spawn_col_marker SAT 0xD0 */
}

static void stealth_step(Slot *e)
{
    /* Volley on +1d (clock); cruise 8.8 applied in entity_update.
     * 8017: reload +1d from +0d. Type 65 +0d=0x20; 34/66 stay 0x30. */
    if (e->clock)
        e->clock--;
    else
    {
        u8 period = (e->variant == 65) ? 32 : 48;
        u8 i;

        e->clock = period;
        if (e->variant == 66)
        {
            /* 0x8023: ev21, 4c91 aim, table 808a (Y,X) + type 59. */
            u8 dir = aim_4c91(e->x, e->y);

            sound_play_event(SND_EV_EHIT2);
            for (i = 0; i < 5; i++)
                spawn_sideways59((s16)(e->x + k_volley_66[i][1]),
                                 (s16)(e->y + k_volley_66[i][0]),
                                 dir);
        }
        else
        {
            /* 0x8031: 8087 if playerY >= entityY else 8084. */
            const u8 *tab = (player_y() >= e->y) ? k_volley_lo : k_volley_hi;
            u8 n = (e->variant == 65) ? 1 : 3;

            for (i = 0; i < n; i++)
            {
                if (e->variant == 65)
                    spawn_lead20(e->x, e->y);
                else
                    spawn_frag(e->x, e->y, tab[i], 38);
            }
        }
    }
    /* 8012: DEC +1d, volley, 4898, 71f6, JP 82a7 (44BA+7904). No vis, no XOR. */
}

static void spawn_descender(Slot *e)
{
    /* handler_type61_large_descender 0x8302: +09=02, +0c=1 Y-only 8.8.
     * Pat 62 sart + compl 63 (SAT F8/FC). clock=+1e halt.
     * +04 from 8eaf[E149&7] via sat_col (0x81->0x8F).
     * 8302 writes X=0x40/0xB0, never +01: leftover Y=0. */
    e->kind = KIND_DESCEND;
    e->variant = 61;
    e->hp = 1;
    e->clock = 32;              /* +0x1e halt frames at Y=0x60 */
    e->ground = 0;
    e->dest = 0;                /* Xvel 8.8 (Y-only) */
    e->bind = 0x0200;           /* Yvel 8.8: +09=0x02 */
    e->script = 0;              /* X frac */
    e->timer = 0;               /* Y frac */
    e->x = (player_x() >= 0x78) ? 64 : 176;
    e->y = 0;               /* 8302 leaves +01; stream Y=0 */
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    /* 8327: A=(E149); INC E149; +1d=A&7; +04=8eaf[+1d], 0x81->0x8F. */
    {
        u8 idx = (u8)(s_desc_cycle & 7);
        u8 col;

        s_desc_cycle = (u8)((s_desc_cycle + 1) & 7);
        e->aux = idx;               /* +0x1d idx -> fire# on 8394 */
        col = k_fire83_color[idx];
        if (col == 0x81)
            col = 0x8F;
        e->sat_col = col;
    }
    spr_place(e, FRAME_SART);       /* +03=0xf8 pat 62 */
    marker_place(e, FRAME_SART_C);  /* spawn_col_marker SAT 0xFC */
}

static void descender_step(Slot *e)
{
    /* 834a: at Y==0x60 clear +0c, DEC +1e; expire -> +0c=1 +09=FC.
     * Then entity_update Y-only 8.8 (bind/timer). Rise same frame. */
    if (e->y == 0x60)
    {
        /* Original: +0c=0; DEC +1e; on Z set +0c=1 +09=FC (same frame). */
        e->bind = 0;
        e->y = 0x60;
        if (e->clock)
            e->clock--;
        if (!e->clock)
            e->bind = 0xFC00;   /* Yvel 8.8: +09=0xFC */
    }
    if (e->bind)
    {
        /* 8362: 4898. Halt keeps +0c=0 (bind=0, no Y_motion). Rise
         * +0c=1 Yvel FC00; unsigned wrap CP 0xD0 clears. */
        if (step_88_y_4898(e))
            return;
    }
    e->vx = 0;
    e->vy = 0;
}

/* handler_type62_invisible_riser 0x8709:
 * Yvel 8.8 FF80, pat 0, +0c=1; every-16f VRAM poke; ship-touch ->
 * INC E10A + ev8 + status. Spawned from type61 death when
 * (E140&0x3F)==(E103&0x3F). 8709 BIT 7 clear: init SET 7 / 8727 RET
 * (no 8728, no 4898). 8385 is the type write; this is the next visit. */
static void become_riser(Slot *e)
{
    marker_kill(e);
    if (e->spr)
    {
        SPR_releaseSprite(e->spr);
        e->spr = NULL;
    }
    e->kind = KIND_RISER;
    e->variant = 62;
    e->hp = 1;
    e->ground = 0;
    e->dest = 0;                /* Xvel 8.8 */
    e->bind = 0xFF80;           /* Yvel 8.8: -0.5 px/frame */
    e->script = 0;              /* X frac */
    e->timer = 0;               /* Y frac */
    e->clock = 0;               /* +0x0d frame counter */
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    /* 8385 writes 0x3E (bit7 clear) and RETs. Next dispatch is 8709
     * init SET 7 / 8727 RET. Arm skip so the first KIND_RISER visit
     * is that RET, not 8728+4898. */
    {
        u8 idx = (u8)(e - s_en);
        if (idx < ENEMY_SLOTS)
            s_riser_init_ret[idx] = 1;
    }
}

static void spawn_riser(Slot *e)
{
    const ModeAssets *a = mode_assets();

    e->x = (s16)(16 + (rnd() % (a->playfield_w - 32)));
    e->y = (s16)(a->playfield_h - 32);
    become_riser(e);
}

static void riser_step(Slot *e)
{
    u8 old = e->clock;

    /* 8728: every 16f (old&0x0f)==0 -> LDIRVM row from 876b+(old&0x10?0x20:0). */
    e->clock = (u8)(old + 1);
    if ((old & 0x0F) == 0)
        map_script_type62_poke((u8)((old & 0x10) ? 1 : 0));

    /* 874a: 4898 Y_motion (+0c=1). Unsigned wrap, CP 0xD0 clears. */
    if (step_88_y_4898(e))
        return;
    e->vx = 0;
    e->vy = 0;
}

/* type61 post-death 836b: if type==0x23, dec_encounter_a; gate to 62 or 83. */
static int descender_on_death(Slot *e)
{
    entity_dec_encounter_a();
    if ((s_alc_shots & 0x3F) == (player_score_lo() & 0x3F))
    {
        award_subtype(61);
        become_riser(e);  /* become_riser marker_kill */
        return 1;
    }
    if (player_e148() >= 5)
    {
        award_subtype(61);
        marker_kill(e);
        /* 8394: type 0x53; +0x1c := +0x1d (color cycle / fire#). */
        e->kind = KIND_FIREUP;
        e->variant = (u8)(e->aux & 7);
        e->hp = 1;
        e->timer = 0;
        e->script = 0;
        e->ground = 0;
        e->dest = 0;
        e->bind = 0;
        e->vx = 0;
        e->vy = 0;
        spr_place(e, FRAME_CIRCLE);
        return 1;
    }
    return 0;
}

static void spawn_med_circle(Slot *e)
{
    /* 0x839f: Y=0x10+(L&0x7f) X=0x40+(H&0x7f); +04=0x86 SAT 0x20;
     * +0c=3 +17=3 HP5; +1b=0x78 +1c=0x1e. +05.0 still clear. */
    e->kind = KIND_CIRCLE;
    e->variant = 67;
    e->hp = 5;
    e->timer = 0;
    e->script = 0;
    e->ground = 0;
    e->dest = 0;
    e->bind = 0;
    e->clock = 0x78;
    e->aux = 0x1E;
    e->x = (s16)(64 + (rnd() & 0x7F));
    e->y = (s16)(16 + (rnd() & 0x7F));
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    e->sat_col = 0x86;          /* +04; XOR 0x0c @ 83e0 */
    spr_place(e, FRAME_MED_CIRCLE); /* +03=0x20 pat 8 */
}

static void circle_step(Slot *e)
{
    /* 0x83d8: SAT name ^=0x34 (0x20 <-> 0x14), color ^=0x0c.
     * SAT 0x14 is gfx pat 5 (small star), extracted into
     * FRAME_SMALL_STAR. DEC +1b; NZ + bit0 clear -> 48b8 only.
     * Z: SET +05.0, DEC +1c, +1c==0 SET +05.1; else +04=0x8d,
     * +1b=0x32+(R&0x1e), aim_4c91 + set_velocity_from_dir speed 3.
     * Bit0 gates 8424 JP 4898 (+0c=3). */
    u16 fr;

    e->sat ^= 0x34;
    fr = frame_from_sat(e->sat);
    if (fr < FRAME_N)
        spr_place(e, fr);
    spr_set_sat_col(e, (u8)(e->sat_col ^ 0x0c));

    e->clock--;
    if (!e->clock)
    {
        u8 a = (u8)(e->aux | 0x40);
        u8 phase = (u8)(a & 0x1F);

        if (phase)
            phase--;
        a = (u8)((a & 0xE0) | phase);
        if (!phase)
            a |= 0x80;

        if (!(a & 0x80))
        {
            u8 r = rnd();
            e->clock = (u8)(0x32 + (r & 0x1E));
            spr_set_sat_col(e, 0x8d);   /* 840a overwrites XOR that frame */
            apply_dir_88(e, aim_4c91(e->x, e->y), 3);
        }
        e->aux = a;
    }

    /* 83ee: BIT 0 of +05 (aux 0x40) else 48b8 -- no 4898 while idle.
     * Armed 8424 JP NZ 4898 +0c=3: u8 8.8 wrap-cull Y>=0xD0 / X>=0xD1.
     * Signed s32 + shared Y>200 killed Y=201..207 and let
     * X=0xD1..0xFF live; rise-wrap Y went negative instead of 0xFF. */
    if (e->aux & 0x40)
    {
        if (step_88_4898(e))
            return;
    }
}

/* umber_burst_param_table 0x79b7 */
static const u8 k_umber_burst[7] = { 0x04, 0x05, 0x02, 0x07, 0x03, 0x06, 0x01 };

/* base_spawner_spawn_table 0x7af7: (type, count) x8 */
static const u8 k_spawner[8][2] = {
    { 10, 30 }, { 16, 8 }, { 22, 10 }, { 23, 8 },
    { 48, 6 }, { 8, 8 }, { 65, 6 }, { 36, 30 }
};

/*
 * base_attack_patterns 0x93AB: 8 descriptors of 3-byte (r0,rM,r3) records,
 * 0x00-terminated. Offsets into k_pat_blob.
 */
static const u8 k_pat_blob[] = {
    0x04,0x30,0x02,0x00,
    0x04,0x20,0x03,0x02,0x20,0x02,0x00,
    0x04,0x1C,0x02,0x04,0x30,0x04,0x00,
    0x04,0x28,0x05,0x00,
    0x05,0x40,0x0E,0x00,
    0x04,0x10,0x0A,0x03,0x20,0x05,0x00,
    0x02,0x20,0x08,0x00,
    0x03,0x20,0x08,0x00
};
static const u8 k_pat_off[8] = { 0, 4, 11, 18, 22, 26, 33, 37 };

static int spawn_from_type(u8 t);
static void spawn_frag(s16 x, s16 y, u8 dir, u8 variant);
static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant);
static void entity_inc_encounter_a(void);

/* set_velocity_from_dir 4cf7 (+0x17 = speed) into screen-space 8.8.
 * dest=Xvel (word1), bind=Yvel (word0), script=Xfrac, timer=Yfrac; vx/vy
 * cleared so the shared integer pass does not double-apply.
 * k_unit_x = ROM word0 (Y), k_unit_y = ROM word1 (X). */
static void apply_dir_88(Slot *e, u8 dir, u8 speed)
{
    s16 xvel = (s16)(k_unit_y[dir & 15] * (s16)speed);
    s16 yvel = (s16)(k_unit_x[dir & 15] * (s16)speed);

    e->dest = (u16)xvel;
    e->bind = (u16)yvel;
    e->script = 0;
    e->timer = 0;
    e->vx = 0;
    e->vy = 0;
}

/* 4cf7 speed byte: BIT 6 => *3, BIT 7 => *4, then DJNZ *(A&0x3F).
 * 0xC2 = *24 (12 px/frame cardinal). 0xC3 = *36 (18 px). Do not
 * drop bit6 (0xC2 would be 4 px, 0xC3 would be 6 px). */
static void apply_dir_4cf7(Slot *e, u8 dir, u8 speed)
{
    u8 mul = 1;

    if (speed & 0x40)
        mul = (u8)(mul * 3);
    if (speed & 0x80)
        mul = (u8)(mul * 4);
    mul = (u8)(mul * (u8)(speed & 0x3F));
    apply_dir_88(e, dir, mul);
}

/* type 42/43: speed 3 then 85dd XOR R into X/Y vel low bytes. */
static void apply_dir_88_xor(Slot *e, u8 dir)
{
    u8 rx;
    u8 ry;

    apply_dir_88(e, dir, 3);
    rx = rnd();
    ry = rnd();
    e->dest = (u16)((e->dest & 0xFF00) | ((u8)e->dest ^ rx));
    e->bind = (u16)((e->bind & 0xFF00) | ((u8)e->bind ^ ry));
}

static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)
{
    e->kind = KIND_EBULLET;
    e->variant = variant;
    e->hp = 1;
    e->timer = 0;
    e->script = 0;
    e->ground = 0;
    e->dest = 0;
    e->x = x;
    e->y = y;
    apply_dir(e, dir);
    if (variant == 20)
    {
        /* Same first-frame fields as spawn_lead20 / 0x8668 (full X 8.8). */
        type20_init_vel(e);
    }
    else if (variant == 37)
    {
        /* handler_type37 84e3: +0x17=3; player_pos_snapshot 4c8b
         * (= aim_4c91 then set_velocity_from_dir). Clean speed-3 8.8; no XOR.
         * Type 42 CALL 84e3 then XOR - keep apply_dir_88_xor below. */
        apply_dir_88(e, aim_4c91(x, y), 3);
    }
    else if (variant == 42)
    {
        /* handler_type42_proto_bullet 0x85cc:
         * CALL 84e3 (type37 init body), LD (IX+0)=0xA5, XOR R into
         * IX+0x0a / IX+0x08 (X/Y vel low bytes), RET 85ed. No 4898.
         * Next visit is type 0xA5 (37 armed). Port keeps variant 42. */
        apply_dir_88_xor(e, aim_4c91(x, y));
    }
    else if (variant == 43)
    {
        /* handler_type43_proto_fragment 0x85d6 (falls into 0x85dd XOR):
         * CALL 8507 (type38 init), LD (IX+0)=0xA6, XOR R vel lows, RET 85ed.
         * Next visit is type 0xA6 (38 armed). Dir from +0x1a. Port keeps 43. */
        apply_dir_88_xor(e, dir);
    }
    else if (variant == 41)
    {
        /* handler_type41_pair_fragment 0x852f:
         * +0x1a param (low4 base, bit4 curve sense); +0x1b heading = base +/-4;
         * 4cf7 speed 2, LDIR vel -> +1c/+1e, then +17=4 (no 4898 this frame).
         * Port: clock=+0x1a (bias dir); aux packs count/sense/heading;
         * dest/bind = the speed-2 seed (LDIR source). */
        u8 base = (u8)(dir & 15);
        u8 heading = (u8)((dir & 0x10)
            ? ((base + 0xFC) & 15)
            : ((base + 4) & 15));
        e->clock = dir;
        e->aux = (u8)((2 << 5) | (dir & 0x10) | heading);
        apply_dir_88(e, heading, 2);
    }
    else if (variant == 38)
    {
        /* handler_type38_burst_fragment 0x8507:
         * +0x17=3; dir=+0x1a&0x0F; set_velocity_from_dir (8.8). */
        apply_dir_88(e, dir, 3);
    }
    else if (variant == 21)
    {
        /* handler_type21_light_bar 0x8635/0x863b:
         * +0x17=4; dir=+0x1a&0x0F; set_velocity_from_dir (8.8); SFX #0x16. */
        apply_dir_88(e, dir, 4);
        sound_play_event(SND_EV_LIGHTBAR);
    }
    else if (variant == 45)
    {
        /* handler_type45_light_bar_var 0x85ee:
         * +0x17 = (R&1)+2 speed; CALL 850b (SAT 0x1C/col 0x8F/dir); +0x19=3 HP;
         * +0x1c=0x28. Same apply_dir_88 8.8 path as 21/37/38/41/42/43.
         * Meta off fracs: aux=(speed<<4)|(dir&15), clock=+0x1c re-aim.
         * Active 8625 overwrites SAT 0x18/0x20; spawn LIGHT_BAR until first step. */
        u8 speed = (u8)(2 + (rnd() & 1));
        e->hp = 3;
        e->aux = (u8)((speed << 4) | (dir & 15));
        e->clock = 0x28;
        e->sat_col = 0x8F;          /* 850b +04; pulse is size not color */
        apply_dir_88(e, (u8)(dir & 15), speed);
    }
    e->alive = 1;
    /* 20/37/38/41/42/43: +04=0x8F (8672/84eb/8513/8539). Type 21 init
     * 863b does not write +04 (active 8659 is R-nibble|0x80). */
    if (variant != 21)
        e->sat_col = 0x8F;
    /* 21: SAT 0x18 pat 6. 45: 850b writes 0x1C then 8625 pulses 0x18/0x20. */
    spr_place(e, (variant == 21 || variant == 45) ? FRAME_LIGHT_BAR : FRAME_LEAD);
    /* 37 84fa / 38 8524 / 41 857e / 21 8656: SET 7 RET.
     * 42/43: CALL 84e3/8507 (those RETs return into XOR) then 85ed RET.
     * Type 20 init falls into 4898; type 45 CALL 850b then 8608/82a4. */
    if (variant == 21 || variant == 37 || variant == 38 || variant == 41
        || variant == 42 || variant == 43)
    {
        u8 idx = (u8)(e - s_en);
        if (idx < ENEMY_SLOTS)
            s_ebullet_init_ret[idx] = 1;
    }
}

static void spawn_frag(s16 x, s16 y, u8 dir, u8 variant)
{
    Slot *e = free_enemy();
    if (!e)
        return;
    init_frag(e, x, y, dir, variant);
}

static void spawn_umber(Slot *e, u8 type)
{
    /* handler_type7_umber 0x791d (shared 7/8/9 via 0x7923).
     * 8.8 packing matches type20/duster: dest=Xvel, bind=Yvel,
     * script=Xfrac, timer=Yfrac. vx/vy 0 so shared pass inert.
     * +0c=0x09 Y|Y_homing; Yvel 0x0300; +15=0x10; +17=1; +13 tgt 0.
     * 791d writes X=0x78, never +01: stream leftover Y=0 (top).
     * Type9: clock=+0x1d spawn timer 8. */
    e->kind = KIND_UMBER;
    e->variant = type;
    e->hp = 1;
    e->ground = 0;
    e->dest = 0;            /* Xvel 8.8 (Y-only) */
    e->bind = 0x0300;       /* Yvel 8.8: vy=3 vy_frac=0 */
    e->script = 0;          /* X frac */
    e->timer = 0;           /* Y frac */
    e->clock = (type == 9) ? 8 : 0;  /* +0x1d type9 only */
    e->aux = 0;
    e->x = 120;             /* +0x02 = 0x78 */
    e->y = 0;               /* 791d leaves +01; stream Y=0 */
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    if (type == 9)
    {
        e->sat_col = 0x83;                /* cyan */
        spr_place(e, FRAME_UMBER_B);      /* pat 56 SAT 0xE0 */
        marker_place(e, FRAME_UMBER_B_C); /* pat 58 SAT 0xE8 */
    }
    else
    {
        /* type7 white 0x8F; type8 patched 0x8B @ 79c7 */
        e->sat_col = (type == 8) ? 0x8B : 0x8F;
        spr_place(e, FRAME_UMBER);        /* pat 55 SAT 0xDC */
        marker_place(e, FRAME_UMBER_C);   /* pat 57 SAT 0xE4 */
    }
}

static void umber_burst(Slot *e)
{
    u8 i;
    if (e->variant == 7)
    {
        /* 0x7986: D/E = parent Y/X; 7x type38 write (HL)=26, +01=D, +02=E.
         * Same 8ddb class as luster/veybar/swoop: parent XY, no SAT-center. */
        for (i = 0; i < 7; i++)
            spawn_frag(e->x, e->y, k_umber_burst[i], 38);
    }
    else if (e->variant == 8)
    {
        /* 0x79cc: two type41; copy IX+01/+02 into both; +0x1a = 0x05 / 0x13. */
        spawn_frag(e->x, e->y, 5, 41);
        spawn_frag(e->x, e->y, 0x13, 41);
    }
}

static void umber_step(Slot *e)
{
    /* Active 0x7954: 795d SAT morph on Yvel.hi, then burst when the
     * Yvel word == 0 (before entity_update). Type9 0x7a12: DEC +0x1d,
     * reload 8, 8ddb type20 at parent XY (no 795d morph).
     * 79ae CALL 4898 +0c=0x09: Y_homing_sub then Y_motion_sub. */
    u16 yvel;

    if (e->variant == 7 || e->variant == 8)
    {
        u8 yh = (u8)(e->bind >> 8);

        /* 0x795D: OR A / JR Z -> 0xE0/0xE8; CP 0xFF / JR NZ skip;
         * else 0xDC/0xE4. Type 9 stays on 7a12 (spawn E0/E8 only). */
        if (yh == 0)
        {
            spr_place(e, FRAME_UMBER_B);      /* +03 = 0xE0 */
            marker_place(e, FRAME_UMBER_B_C); /* IY+03 = 0xE8 */
        }
        else if (yh == 0xFF)
        {
            spr_place(e, FRAME_UMBER);        /* +03 = 0xDC */
            marker_place(e, FRAME_UMBER_C);   /* IY+03 = 0xE4 */
        }
        if (e->bind == 0)
            umber_burst(e);
    }

    if (e->variant == 9)
    {
        if (e->clock)
            e->clock--;
        else
        {
            e->clock = 8;
            /* 0x7a22: A=0x14 type20, 8ddb copies IX+01/+02. */
            spawn_frag(e->x, e->y, 0, 20);
        }
    }

    yvel = e->bind;
    if ((u8)e->y != 0)
        yvel = (u16)(yvel - 0x0010);
    e->bind = yvel;

    /* 79ae CALL 4898 +0c=0x09: Y_homing then Y_motion_sub.
     * Unsigned 8.8 + Y>=0xD0. Signed s32 + 192+8 cull killed
     * Y=201..207 and let rise-wrap Y=0+0xFD00 sit at -3. */
    if (step_88_y_4898(e))
        return;
    e->vx = 0;
    e->vy = 0;
}

static void spawn_veybar(Slot *e, u8 type)
{
    /* handler_type22_veybar 0x7d0f / type24_fast 0x7db4 -> shared 0x7d2d.
     * 8.8 packing matches type20/duster: dest=Xvel, bind=Yvel,
     * script=Xfrac, timer=Yfrac. Yvel 0x0400; +15=0x14; +17=1; +13 tgt 0.
     * 22/23: +0c=0x09 (Xvel armed, X-motion off until morph fire @0x20).
     * 24/25: +0c=0x1b + X-home (+14 tgt, +16=0x10). clock=+0x1d. */
    u8 fast = (u8)(type >= 24);
    u8 right = rnd() & 1;

    e->kind = KIND_VEYBAR;
    e->variant = type;
    e->hp = 1;
    e->ground = 0;
    e->script = 0;          /* X frac */
    e->timer = 0;           /* Y frac */
    e->bind = 0x0400;       /* Yvel 8.8: vy=4 */
    e->y = 0;
    e->vx = 0;
    e->vy = 0;
    e->alive = 1;
    if (fast)
    {
        e->x = right ? 184 : 56;
        e->dest = right ? 0xFD00 : 0x0300;  /* Xvel -3 / +3 */
        e->aux = right ? 0xFF : 0x00;       /* +0x14 X-home tgt */
        e->clock = 0x58;                    /* +0x1d = 88 */
    }
    else
    {
        e->x = right ? 200 : 40;
        e->dest = right ? 0xFF00 : 0x0100;  /* Xvel -1 / +1 (motion off) */
        e->aux = 0;                         /* bit0 phase, bit1 x_on */
        e->clock = 0x50;                    /* +0x1d = 80 */
    }
    e->sat_col = fast ? 0x89 : 0x83;        /* 24/25 light-red; 22/23 cyan */
    spr_place(e, FRAME_VEYBAR_0);
    marker_place(e, FRAME_VEYBAR_C0);  /* spawn_col_marker SAT 0x98 */
}

static void veybar_step(Slot *e)
{
    /* Active 0x7d4c (shared 22-25): countdown +0x1d / phase +0x05.0;
     * Y_homing then Y/X 8.8. Morph 0x7d64: clock<0x40 and (RRCA x2) only
     * bits 2-3 set; 7d73 SAT (IX+03)=0x94-E, marker (IY+03)=SAT+0x14
     * then 71f6 dual-SAT sibling. Fire 0x7d8c when marker==0xa0
     * (E==0x08 => clock==0x20): 8ddb type37 at parent XY. 22/23 (type>>1==0x4b):
     * 7d95 +17=4 aim+set_vel, +17=1 +15=0x0c SET +0c.1; 24/25 skip
     * re-aim/arm (already +0c=0x1b). Telegraph clocks: 0x30/0x20/0x10/0x00
     * -> SAT 0x88/0x8c/0x90/0x94 (pats 34-37). */
    u16 yvel = e->bind;
    u16 xvel = e->dest;
    u8 fast = (u8)(e->variant >= 24);
    u8 y_accel = 0x14;
    u8 x_on = fast ? 1 : (u8)(e->aux & 2);

    if (fast)
    {
        /* Same DEC/morph window as 22/23; aux is X-home tgt so no phase bit.
         * clock hits each value once (stops at 0) so type37 fires once @0x20. */
        if (e->clock)
            e->clock--;
        if (e->clock < 0x40)
        {
            u8 rot = (u8)((e->clock >> 2) | (e->clock << 6)); /* RRCA RRCA */
            if ((u8)(rot & 0x0c) == rot)
            {
                u8 sat = (u8)(0x94 - rot);
                u16 fi = (u16)((sat - 0x84) >> 2);
                /* 7d73 parent + marker; 71f6 emits marker SAT sibling. */
                spr_place(e, (u16)(FRAME_VEYBAR_0 + fi));
                marker_place(e, (u16)(FRAME_VEYBAR_C0 + fi));
                if ((u8)(sat + 0x14) == 0xa0)
                {
                    /* 7dab: alloc + 8ddb A=0x25 type37, IY Y/X = parent.
                     * 24/25 skip 7d95 (type>>1 != 0x4b). Child 84e3 aims. */
                    spawn_frag(e->x, e->y, 0, 37);
                }
            }
        }
    }
    else if (!(e->aux & 1))
    {
        if (e->clock)
            e->clock--;
        if (!e->clock)
            e->aux = (u8)(e->aux | 1);
        /* Morph window runs even on the frame clock hits 0 (MSX fall-through). */
        if (e->clock < 0x40)
        {
            u8 rot = (u8)((e->clock >> 2) | (e->clock << 6)); /* RRCA RRCA */
            if ((u8)(rot & 0x0c) == rot)
            {
                u8 sat = (u8)(0x94 - rot);
                u16 fi = (u16)((sat - 0x84) >> 2);
                spr_place(e, (u16)(FRAME_VEYBAR_0 + fi));
                marker_place(e, (u16)(FRAME_VEYBAR_C0 + fi));
                if ((u8)(sat + 0x14) == 0xa0)
                {
                    /* 7d95: +17=4; 4c91; set_velocity_from_dir; then +17=1 /
                     * +15=0x0c; SET +0c.1. Preserve X/Y fracs (vel words only).
                     * Same-frame motion uses the re-aimed 8.8 (not spawn +/-1). */
                    u8 xf = e->script;
                    u8 yf = e->timer;
                    apply_dir_88(e, aim_4c91(e->x, e->y), 4);
                    e->script = xf;
                    e->timer = yf;
                    xvel = e->dest;
                    yvel = e->bind;
                    e->aux = (u8)(e->aux | 2);
                    x_on = 1;
                    /* 7dab: alloc + 8ddb A=0x25 type37 at parent XY. */
                    spawn_frag(e->x, e->y, 0, 37);
                }
            }
        }
    }
    if (x_on && !fast)
        y_accel = 0x0c;

    /* Y_homing_sub: tgt +13=0, accel=+15, B=+17=1. */
    if ((u8)e->y != 0)
        yvel = (u16)(yvel - (u16)y_accel);
    e->bind = yvel;

    /* X_homing_sub (fast only): tgt=aux(+14), accel=+16=0x10, B=1. */
    if (fast && (u8)e->x != e->aux)
    {
        if ((u8)e->x < e->aux)
            xvel = (u16)(xvel + 0x0010);
        else
            xvel = (u16)(xvel - 0x0010);
    }
    e->dest = xvel;

    /* 7d83 CALL 4898: +0c=0x09 Y-only until morph SET +0c.1;
     * 24/25 +0c=0x1b already X|Y. Unsigned 8.8 + Y>=0xD0 / X>=0xD1.
     * Signed s32 + 192+8 cull killed Y=201..207 and let rise-wrap
     * Y=0+0xFD00 sit at -3; X>=0xD1 stayed live past 0xD1. */
    if (x_on)
    {
        if (step_88_4898(e))
            return;
    }
    else if (step_88_y_4898(e))
        return;
    e->vx = 0;
    e->vy = 0;
}

/* anim_sub +0d timer / +0f frame for KIND_SWOOP (period +0e=4, count +10=4). */
static u8 s_swoop_atim[ENEMY_SLOTS];
static u8 s_swoop_afi[ENEMY_SLOTS];

static void spawn_swoop(Slot *e, u8 type)
{
    /* handler_type26/27 @ 7de2 / type28/29 @ 7e78.
     * 8.8 packing matches type20/apply_dir_88: dest=Xvel, bind=Yvel,
     * script=Xfrac, timer=Yfrac. aux=+0x1d child type; clock=+0x1e fire.
     * +0x13 Y-home tgt left 0 (entity_clear); do not touch type41/45 aux/clock
     * ownership beyond this kind. */
    e->kind = KIND_SWOOP;
    e->variant = type;
    e->hp = 1;
    e->ground = 0;
    e->y = 0;               /* spawn writes type only; Y starts cleared */
    e->vx = 0;
    e->vy = 0;
    e->script = 0;          /* X frac */
    e->timer = 0;           /* Y frac */
    e->bind = 0x0280;       /* Yvel 8.8 */
    e->alive = 1;
    if (type == 26)
    {
        e->x = 0xC8;            /* H from HL=0xC825 */
        e->dest = 0xFF40;       /* Xvel 8.8 */
        e->aux = 37;            /* L = child type */
        e->clock = 0x18;        /* +0x1e */
    }
    else if (type == 27)
    {
        e->x = 0x28;            /* HL=0x2814 */
        e->dest = 0x00C0;
        e->aux = 20;
        e->clock = 0x18;
    }
    else if (type == 28)
    {
        e->x = 0xC0;            /* HL=0xC03B */
        e->dest = 0xFE00;
        e->aux = 59;
        e->clock = 0x04;        /* type28/29 set +1e=4 before join */
    }
    else
    {
        e->x = 0x30;            /* HL=0x3029 */
        e->dest = 0x0200;
        e->aux = 41;
        e->clock = 0x04;
    }
    /* anim_sub: +0d/+0e=4, +0f=0, +10=4; table pats 43-46.
     * +04 from edge_swooper_a/b_anim: 26/27=0x8E, 28/29=0x87. */
    {
        u8 si = (u8)(e - s_en);
        s_swoop_atim[si] = 4;
        s_swoop_afi[si] = 0;
    }
    e->sat_col = (type <= 27) ? 0x8E : 0x87;
    spr_place(e, FRAME_SPINNER_0);
    marker_place(e, FRAME_SPINNER_C0);  /* 71da + 7e5f: SAT+0x10 */
}

static void swoop_step(Slot *e)
{
    /* entity_update 4898 with +0c=0x0F: Y_homing (bit3) then Y/X motion + anim.
     * Y_homing_sub: B=+17=1, accel=+15=0x07, tgt=+13=0.
     * anim_sub 4912: every 4f cycle pats 43-46; 71f6 marker = sat+0x10. */
    u16 yvel = e->bind;
    u8 si = (u8)(e - s_en);

    if ((u8)e->y != 0)
    {
        /* tgt 0 < Y -> SBC accel (never ADD with tgt 0). */
        yvel = (u16)(yvel - 0x0007);
    }
    e->bind = yvel;

    /* 7e55 CALL 4898: +0c=0x0F Y|X 8.8. Unsigned Y>=0xD0 / X>=0xD1.
     * Signed s32 + 192+8 cull killed Y=201..207 and let rise-wrap
     * Y=0+0xFD00 sit at -3; X>=0xD1 stayed live past 0xD1. */
    if (step_88_4898(e))
        return;

    /* anim_sub 4912 (+0c bit2): DEC +0d; reload +0e=4; apply table[afi]
     * then INC (wrap +10=4). Port keeps afi = displayed frame; advance first
     * then place so marker (sat+0x10) always matches primary. spr_sync later. */
    if (s_swoop_atim[si])
        s_swoop_atim[si]--;
    if (!s_swoop_atim[si])
    {
        u8 fi = s_swoop_afi[si];
        s_swoop_atim[si] = 4;
        /* Original: write table[afi] then INC. Re-apply current then advance. */
        spr_place(e, (u16)(FRAME_SPINNER_0 + fi));
        marker_place(e, (u16)(FRAME_SPINNER_C0 + fi));
        fi++;
        if (fi >= 4)
            fi = 0;
        s_swoop_afi[si] = fi;
    }

    /* 7e3f: DEC +0x1e; on 0 reload 0x20 and 8ddb(child, C=0x04).
     * 8ddb: IY+01/+02 = parent IX+01/+02 (Y/X). No SAT-center +4/+8.
     * 26->37 84e3 aims from that XY; 27->20 8668 ignores C; 28->59
     * already parent XY; 29->41 C=0x04 (heading base+4, may still read
     * offset). Spinner pats 43-46 unchanged. */
    if (e->clock)
        e->clock--;
    else
    {
        u8 ct = e->aux;
        e->clock = 0x20;
        if (ct == 37)
            /* 26: 8ddb A=0x25 type37 at parent XY (84e3 re-aims). */
            spawn_frag(e->x, e->y, 0, 37);
        else if (ct == 20)
            /* 27: 8ddb A=0x14 type20 at parent XY. */
            spawn_frag(e->x, e->y, 0, 20);
        else if (ct == 59)
        {
            Slot *c = free_enemy();
            if (c)
                /* 8ddb C=0x04 -> +0x1a; type59 8269 -> apply_dir_88 speed 5. */
                init_type59(c, e->x, e->y, 4);
        }
        else
            /* type 29: 8ddb A=0x29 type41 C=0x04 at parent XY. */
            spawn_frag(e->x, e->y, 0x04, 41);
    }
}

static void spawn_tracker(Slot *e, u8 type)
{
    /* handler_type31_stealth_tracker @ 7f84 (run) / shared init body 7fa0.
     * Stream spawn: 807c X+dir, speed 1, sat 0xCC pat51, color 0x88,
     * +0c=1 Y-then-X (not shooter +0c=3). vy=+2 (sprint 0026); Xvel from dir
     * for flank phase. No volley. Absent-as-child path uses spawn_gswoop. */
    u8 si = (u8)((rnd() & 6) >> 1);

    e->kind = KIND_TRACKER;
    e->variant = type;
    e->hp = 7;
    e->ground = 0;
    e->x = k_stealth_x[si];
    e->y = 0;               /* 7f84/807c never +01; stream leftover Y=0 */
    e->vx = 0;
    e->vy = 0;
    apply_dir_88(e, k_stealth_dir[si], 1);
    /* Y-track uses fixed +2; keep dest (Xvel) from 807c dir for flank. */
    e->bind = 0x0200;
    e->timer = 0;
    e->clock = 0x01;            /* +0c = Y_motion */
    e->aux = 0xFF;              /* no gswoop parent */
    e->alive = 1;
    e->sat_col = 0x88;            /* +04; ^=0x06 @ 7f73 */
    spr_place(e, FRAME_STEALTH);      /* sat 0xCC pat 51 */
    marker_place(e, FRAME_STEALTH_C); /* spawn_col_marker SAT 0xD0 */
}

static void tracker_step(Slot *e)
{
    /* 7f84: playerY CP entityY; BIT6 +05 -> CCF; NC keep Y, CY -> +0c=2.
     * 7f73: +04 ^= 0x06; 7f7b CALL 4898. No merge (parent 7f20 only).
     * +0c=1 Y_motion_sub unsigned Y>=0xD0; +0c=2 X_motion_sub
     * unsigned X>=0xD1. Signed s32 + playfield max_y=200 killed
     * type32 child first rise (Y=0xD0+0xFF00 -> 0xCF) and left-wrap
     * X=0+FE80 -> 0xFE. */
    s16 py = player_y();
    u8 mode = (u8)(e->clock & 3);
    u8 past;

    if (!(e->clock & 0x80))
    {
        if (e->clock & 0x40)
            past = ((u8)e->y <= (u8)py);
        else
            past = ((u8)e->y > (u8)py);
        if (past)
        {
            mode = 2;
            e->clock = (u8)((e->clock & (u8)~3) | 2);
        }
    }
    else
        mode = (u8)(e->clock & 3);

    if (mode & 1)
    {
        if (step_88_y_4898(e))
            return;
    }
    if (mode & 2)
    {
        u16 xpos = (u16)(((u16)((u8)e->x) << 8) | (u8)e->script);

        xpos = (u16)(xpos + e->dest);
        e->script = (u8)xpos;
        e->x = (s16)(u8)(xpos >> 8);
        e->vx = 0;
        if ((u8)e->x >= 0xD1)
        {
            spr_kill(e);
            return;
        }
    }
    e->vx = 0;
    e->vy = 0;

    /* 7f73: +04 ^= 0x06 then 4898 (0x88<->0x8E real tint). */
    spr_set_sat_col(e, (u8)(e->sat_col ^ 0x06));
    e->clock = (u8)((e->clock & (u8)~0x04) | ((e->sat_col & 0x06) ? 0x04 : 0));
}

static void spawn_gswoop(Slot *e, u8 type)
{
    /* handler_type30_ground_swooper @ 7e9c.
     * 8.8 packing matches type20/26-29: dest=Xvel, bind=Yvel,
     * script=Xfrac, timer=Yfrac. clock low=+0c (1=Y,2=X); bit2=xor
     * phase; bit6=type32 sense; bit7=lock. aux=paired sibling (0xFF).
     * +03 SAT name 0xec (child 0xf0); +04=0x8f. */
    Slot *c;
    u8 ei;

    e->kind = KIND_GSWOOP;
    e->variant = type;
    e->hp = 1;
    e->ground = 0;
    e->script = 0;          /* X frac */
    e->timer = 0;           /* Y frac */
    e->vx = 0;
    e->vy = 0;
    e->x = 0x30;
    e->aux = 0xFF;
    e->clock = 0x01;        /* +0c = Y_motion */
    e->alive = 1;
    ei = (u8)(e - s_en);
    e->sat_col = 0x8F;      /* +04; ^=0x06 @ 7f73 */
    if (type == 30)
    {
        e->y = 0;
        e->bind = 0x0180;   /* Yvel 8.8 */
        e->dest = 0x0180;   /* Xvel 8.8 */
    }
    else
    {
        /* type32: rise from Y=0xD0, sense bit6, Xvel flip at 7f11. */
        e->y = 0xD0;
        e->bind = 0xFF00;
        e->dest = 0x0100;
        e->clock = (u8)(e->clock | 0x40);
    }

    /* spawn_col_marker + LDIR pair: child type own+1 at X=0xC0.
     * Child is KIND_TRACKER (7f84), sat 0xf0 degid_right -- not stream pat51. */
    c = free_enemy();
    if (c)
    {
        u8 ci = (u8)(c - s_en);

        c->kind = KIND_TRACKER;
        c->variant = (u8)(type + 1);
        c->hp = 1;
        c->ground = 0;
        c->script = 0;
        c->timer = 0;
        c->vx = 0;
        c->vy = 0;
        c->x = 0xC0;
        c->y = e->y;
        c->bind = e->bind;
        c->clock = e->clock;
        c->dest = (type == 30) ? 0xFE80 : 0xFF00;
        c->aux = ei;
        c->alive = 1;
        c->sat_col = 0x8F;      /* +04; +03=0xf0 on MSX */
        e->aux = ci;
        spr_place(c, FRAME_DEGID_R); /* +03=0xf0 degid_right */
    }
    spr_place(e, FRAME_DEGID_L); /* +03=0xec degid_left */
}

static void gswoop_step(Slot *e)
{
    /* Active 7f20 / child 7f84 / epilogue 7f73-7f78 + entity_update 4898.
     * 7f73: +04 ^= 0x06 every frame (sat_col 0x8F<->0x89).
     * Merge 7f5b: +03=0xf4, sib type:=0x28 (type40 clear), X+5, +0c=1. */
    s16 py = player_y();
    u8 mode = (u8)(e->clock & 3);
    u8 past;
    Slot *sib = NULL;

    if (e->aux < ENEMY_SLOTS)
    {
        sib = &s_en[e->aux];
        if (!sib->alive || (sib->kind != KIND_GSWOOP && sib->kind != KIND_TRACKER))
            sib = NULL;
    }

    if (!(e->clock & 0x80))
    {
        /* CP playerY,ownY; type32 BIT6 -> CCF; CY => +0c=2. */
        if (e->clock & 0x40)
            past = ((u8)e->y <= (u8)py);
        else
            past = ((u8)e->y > (u8)py);
        if (past)
        {
            mode = 2;
            e->clock = (u8)((e->clock & (u8)~3) | 2);
            if (sib && (e->variant == 30 || e->variant == 32))
                sib->clock = (u8)((sib->clock & (u8)~3) | 2);
        }

        /* Parent: unsigned (pair.X - own.X) < 0x0B -> 7f5b.
         * 7f54 SUB (IX+02); CP 0x0B; JR NC 7f73. After the pair
         * crosses left, A wraps (>=0x0B) and merge is refused. */
        if (sib && (e->variant == 30 || e->variant == 32))
        {
            if ((u8)((u8)sib->x - (u8)e->x) < 0x0B)
            {
                /* SET lock; +03=0xf4; sib->type40; X+5; +0c=1. */
                e->clock = (u8)((e->clock & (u8)~3) | 0x81);
                /* +03=0xf4 degid_complete */
                spr_place(e, FRAME_DEGID);
                sib->variant = 40; /* type 0x28; handler = entity_clear */
                spr_kill(sib);
                e->aux = 0xFF;
                e->x = (s16)(e->x + 5);
                mode = 1;
            }
        }
    }
    else
        mode = (u8)(e->clock & 3);

    if (mode & 1)
    {
        /* 7f7b CALL 4898 +0c=1: Y_motion_sub unsigned Y>=0xD0. */
        if (step_88_y_4898(e))
            return;
    }
    if (mode & 2)
    {
        /* 7f7b CALL 4898 +0c=2: X_motion_sub unsigned X>=0xD1. */
        u16 xpos = (u16)(((u16)((u8)e->x) << 8) | (u8)e->script);

        xpos = (u16)(xpos + e->dest);
        e->script = (u8)xpos;
        e->x = (s16)(u8)(xpos >> 8);
        e->vx = 0;
        if ((u8)e->x >= 0xD1)
        {
            spr_kill(e);
            return;
        }
    }
    e->vx = 0;
    e->vy = 0;

    /* 7f73: LD A,(IX+0x04); XOR 0x06; LD (IX+0x04),A -- then 4898. */
    spr_set_sat_col(e, (u8)(e->sat_col ^ 0x06));
    e->clock = (u8)((e->clock & (u8)~0x04) | ((e->sat_col & 0x06) ? 0x04 : 0));
}
static void spawn_flash(Slot *e)
{
    /* handler_type36_flashing 0x8296/0x82b3:
     * 71c5 random_x; +0c=1 Y-only; +08=0x80 Yvel.lo (+09=0) =>
     * Yvel 8.8 0x0080; +03=0x34 +04=0x8f; +19=0x10 HP.
     * Port: dest/bind/script/timer 8.8 (like type4/61). */
    u8 r1 = rnd();
    u8 r2 = rnd();

    e->kind = KIND_FLASH;
    e->variant = 36;
    e->hp = 16;                 /* +0x19 = 0x10 */
    e->ground = 0;
    /* random_x_pos 71c5: X=(H&0x7f)+(L&0x1f)+0x28, Y=0 */
    e->x = (s16)((u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28));
    e->y = 0;
    e->vx = 0;
    e->vy = 0;
    e->dest = 0;                /* Xvel 8.8 (Y-only) */
    e->bind = 0x0080;           /* Yvel 8.8: 0.5 px/frame */
    e->script = 0;              /* X frac */
    e->timer = 0;               /* Y frac */
    e->sat_col = 0x8F;          /* +04; XOR 0x0e each frame */
    e->aux = 0;
    e->clock = 0;
    e->alive = 1;
    spr_place(e, FRAME_BOLT);   /* +03=0x34 pat 13 super_hard_bolt */
}

static void flash_step(Slot *e)
{
    /* 0x829c: attr XOR 0x0e; entity_update Y_motion (+0c=1);
     * Y_motion_sub unsigned CP 0xD0; entity_post + 7904. */
    spr_set_sat_col(e, (u8)(e->sat_col ^ 0x0e)); /* 0x8F<->0x81 */
    if (step_88_y_4898(e))
        return;
    e->vx = 0;
    e->vy = 0;
}

static void spawn_pairdesc(Slot *e, u8 type)
{
    /* 81d1/8247: 71c5, SAT 0x6C/0x68, E=4, JP 81ac (speed 5 dir 4,
     * +0c=3, +1f=0x20). Convert to type59 after countdown. Keep sig art. */
    u8 r1 = rnd();
    u8 r2 = rnd();
    u8 x = (u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28);

    e->kind = KIND_PAIRDESC;
    e->variant = type;
    e->hp = 1;
    e->clock = 32;              /* +0x1f descend frames */
    e->ground = 0;
    e->x = (s16)x;
    e->y = 0;                   /* 71c5 Y=0; X column 0x28..0xC6 */
    apply_dir_88(e, 4, 5);      /* E=4; 81ac speed 5; +0c=3 X|Y */
    e->alive = 1;
    e->sat_col = 0x8F;              /* 81c3 XOR shared with 56/59 */
    /* 81d7 71da, no LD (HL). 8247 two 71da (sibling + unnamed). Occupancy. */
    e->marker = (type == 58) ? 2 : 1;
    /* MSX: type57 SAT 0x6C pat27 sig_double; type58 SAT 0x68 pat26 sig_triple */
    spr_place(e, (type == 58) ? FRAME_SIG_TRIPLE : FRAME_SIG_DOUBLE);
}

static void pairdesc_step(Slot *e)
{
    /* +0c=3 X|Y 8.8 (dir 4 speed 5 from 81ac); on +1f expire -> type59 @ 8269. */
    if (e->clock)
    {
        s32 xpos = ((s32)e->x << 8) | (u8)e->script;
        s32 ypos = ((s32)e->y << 8) | (u8)e->timer;

        e->clock--;
        xpos += (s16)e->dest;
        ypos += (s16)e->bind;
        e->script = (u8)xpos;
        e->timer = (u8)ypos;
        e->x = (s16)(xpos >> 8);
        e->y = (s16)(ypos >> 8);
        e->vx = 0;
        e->vy = 0;
        spr_set_sat_col(e, (u8)(e->sat_col ^ 0x09));
        return;
    }
    {
        /* 0x8207: ev21 then 4c91. Shared 81e6 path for type 57 and 58. */
        u8 dir;
        u8 n = (e->variant == 58) ? 2 : 1;
        u8 k;

        sound_play_event(SND_EV_EHIT2);
        /* 0x820c 4c91 → E=aim (16-dir). Convert writes +0x1A then RET;
         * 8269 next frame: AND 0x0F, JP 81a8 speed 5. Port applies now.
         * 8214 DEC E → self aim-1; 822E INC A → child1 aim+1;
         * type 58 8236 LD A,(HL) / 8244 DEC A → child2 aim. */
        dir = aim_4c91(e->x, e->y);
        init_type59(e, e->x, e->y, (u8)(dir - 1));
        for (k = 0; k < n; k++)
        {
            Slot *c = free_enemy();
            if (!c)
                break;
            init_type59(c, e->x, e->y, (u8)(k ? dir : (dir + 1)));
        }
    }
}

/* 8ddb from base_spawner_active 7ab0/7ab6: A=type, C=+0x1a (3 or 5). Parent
 * Y/X would be copied; table-wave first-frames re-roll X via 71c5 and ignore
 * +0x1a. Caller passes spawner aux (C) for side fidelity. */
static int spawn_8ddb_spawner(Slot *parent, u8 type, u8 c)
{
    (void)parent;
    (void)c;
    return spawn_from_type(type);
}
static void spawn_spawner(Slot *e)
{
    /* handler_type11 7ad4 -> base_spawner_active 7a67 first frame.
     * Table index: (E130>>3)&0x0E as byte offset -> pair (E130>>4)&7.
     * +0x03/+0x1b/+0x1c = 0x28; random_x 71c5; left X<0x78 -> drift+2 C=3
     * else drift-2 C=5. */
    u8 pair = (u8)((s_e130 >> 4) & 7);
    u8 et = k_spawner[pair][0];
    u8 cnt = k_spawner[pair][1];
    u8 r1 = rnd();
    u8 r2 = rnd();
    u8 x = (u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28);

    e->kind = KIND_SPAWNER;
    e->variant = 69;
    e->hp = 3;
    e->ground = 0;
    e->script = et;             /* +0x18 emit type */
    e->dest = cnt;              /* +0x19 remaining count */
    e->timer = 0x28;            /* +0x1b fire countdown */
    e->clock = 0x28;            /* +0x1c reload */
    e->x = (s16)x;
    e->y = 0;                   /* 71c5 Y=0 */
    e->vy = 0;
    if (x < 0x78)
    {
        e->vx = 2;              /* +0x0a drift; NOT applied every frame */
        e->aux = 3;             /* +0x1a 8ddb C */
    }
    else
    {
        e->vx = (s8)0xFE;       /* -2 */
        e->aux = 5;
    }
    e->alive = 1;
    /* 7af0 SAT 0x28 is also the 0x28 interval. 7a67 / 71c5 never
     * write +04; TMS color 0 is transparent. Do not spr_place
     * FRAME_FIRE -- that baked white target at Y=0. */
    e->sat = 0x28;
    e->sat_col = 0;
    spr_detach(e);
}

/* cmd 1 97CA: type 69 + (+01 emit, +02 count, +03 interval). 7a67 copies
 * those to +18/+19/+1b/+1c then 71c5 (Y=0, random X). Not a nametable stamp. */
static void spawn_spawner_cmd1(Slot *e, u8 emit, u8 count, u8 interval)
{
    u8 r1 = rnd();
    u8 r2 = rnd();
    u8 x = (u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28);

    e->kind = KIND_SPAWNER;
    e->variant = 69;
    e->hp = 3;
    e->ground = 0;
    e->script = emit;
    e->dest = count ? count : 1;
    e->timer = interval ? interval : 0x28;
    e->clock = e->timer;
    e->x = (s16)x;
    e->y = 0;
    e->vy = 0;
    if (x < 0x78)
    {
        e->vx = 2;
        e->aux = 3;
    }
    else
    {
        e->vx = (s8)0xFE;
        e->aux = 5;
    }
    e->alive = 1;
    /* 97ca LDIR leaves +03 = interval; 7a67 copies it to +1b/+1c.
     * SAT name stays the interval; +04 leftover 0 (invisible). */
    e->sat = interval;
    e->sat_col = 0;
    spr_detach(e);
}

static void spawner_step(Slot *e)
{
    /* base_spawner_active 7a9c: E12D.bit3 gate; interval; 8ddb; walk on fire;
     * bounce when u8 X >= 0xC0 (unsigned wrap supplies left edge). */
    u8 x;

    if (s_spawn_ctrl & 0x08)
        return;
    if (e->timer)
    {
        e->timer--;
        return;
    }
    e->timer = e->clock ? e->clock : 0x28;
    if (!spawn_8ddb_spawner(e, (u8)e->script, e->aux))
        return;                 /* pool full: keep count, no walk */
    if (e->dest)
        e->dest--;
    if (!e->dest)
    {
        spr_kill(e);
        return;
    }
    x = (u8)((u8)e->x + (s8)e->vx);
    e->x = (s16)x;
    if (x >= 0xC0)
        e->vx = (s8)(-(s8)e->vx);
}

static void base_fire(Slot *e)
{
    /* 0x8d14: A=type-0xC9 -> dispatch_inline_table. ROM words:
     * 73->8d2a, 74->8d51, 75->8d6c, 76->8d73, 77->8d93, 78->8d98, 79->8db8.
     * Aim (4c91) only for 8d98 (type 78). 73/74/76/77/79 share +0x13 cursor (vx). */
    /* 8d98 (type 78) is the only 8d14 path that aims; 42 re-aims in 84e3. */
    u8 dir = aim_4c91(e->x, e->y);
    /* 8ddb: IY+01/+02 = parent IX+01/+02. No +4/+8. */
    s16 x = e->x;
    s16 y = e->y;

    if (e->variant == 73)
    {
        /* 8d2a: ADD +0x13,3; store; AND 0x0F; CP 0x0F / 0x0E / 0x09.
         * 9..13: JR 8d2d adds 3 to the already-masked A (not the stored word).
         * a<9 -> type 21 dir=a; a==14 -> type 42 C stale (port dir 0);
         * a==15 -> type 42 C=4. Cursor in unused base vx. */
        u8 cur = (u8)e->vx;
        u8 a;
        for (;;)
        {
            cur = (u8)(cur + 3);
            e->vx = (s8)cur;
            a = (u8)(cur & 0x0F);
            if (a >= 15)
            {
                spawn_frag(x, y, 4, 42);
                return;
            }
            if (a >= 14)
            {
                spawn_frag(x, y, 0, 42);
                return;
            }
            if (a < 9)
            {
                spawn_frag(x, y, a, 21);
                return;
            }
            cur = a;            /* 8d2d: next ADD uses masked A */
        }
        return;
    }
    if (e->variant == 74 || e->variant == 77)
    {
        /* 8d51 (74 B=4) / 8d93 (77 B=2): type 43 via 8dd9.
         * C from +0x13 (vx); if >=9 then C=0; INC C -> +0x13 each shot. */
        u8 n = (u8)((e->variant == 74) ? 4 : 2);
        u8 k;
        u8 c = (u8)e->vx;
        for (k = 0; k < n; k++)
        {
            if (c >= 9)
                c = 0;
            spawn_frag(x, y, c, 43);
            c = (u8)(c + 1);
            e->vx = (s8)c;
        }
        return;
    }
    if (e->variant == 75)
    {
        /* 8d6c: single type 42 (8dd5). */
        spawn_frag(x, y, 0, 42);
        return;
    }
    if (e->variant == 76)
    {
        /* 8d73: DEC +0x13; C=(+0x13)&7; type43 @C;
         * if C!=4 also type43 @(8-C). Cursor stays post-DEC (not &7). */
        u8 c;
        e->vx = (s8)((u8)e->vx - 1);
        c = (u8)((u8)e->vx & 7);
        spawn_frag(x, y, c, 43);
        if (c != 4)
            spawn_frag(x, y, (u8)(8 - c), 43);
        return;
    }
    if (e->variant == 78)
    {
        /* 8d98: CALL 4c91; 5-spread table 0, -1, +1, -2, +2 via type 43. */
        static const s8 sprd[5] = { 0, -1, 1, -2, 2 };
        u8 k;
        for (k = 0; k < 5; k++)
            spawn_frag(x, y, (u8)((dir + sprd[k]) & 15), 43);
        return;
    }
    if (e->variant == 79)
    {
        /* 8db8: INC +0x13; (&3)==0 -> type 42 (8d6c); else type 45 dir=R&0x0C.
         * Cursor in unused base vx (shared with 73/74/76/77). */
        u8 cur = (u8)((u8)e->vx + 1);
        e->vx = (s8)cur;
        if ((cur & 3) == 0)
            spawn_frag(x, y, 0, 42);
        else
            spawn_frag(x, y, (u8)(rnd() & 0x0C), 45);
        return;
    }
    spawn_frag(x, y, dir, 38);
}

static void base_finish_death(Slot *e)
{
    s16 sx = e->x;
    s16 sy = e->y;
    u8 drop = e->variant;
    u8 n;
    u8 k;

    /* 8baa: 8ca2 punch at live SAT XY, type 50, DEC E152.
     * Port: award + ev17 + scatter then punch (73-78 same path, 79 delayed). */
    award_subtype(drop);
    sound_play_event(SND_EV_EHIT);
    spr_kill(e);
    scatter_expl(sx, sy);
    if (s_base_left)
        s_base_left--;
    map_script_base_seg_down(sx, sy, drop);
    n = 0;
    for (k = 0; k < ENEMY_SLOTS; k++)
        if (s_en[k].alive && s_en[k].kind == KIND_BASE)
            n++;
    if (!n)
        map_script_base_no_segments();
}

/* 8c15 / 8c39: VRAM from 8948 bind stored at arm (NT col/row), not live SAT. */
static void base_8c15(const Slot *e)
{
    if (!(e->bind & 0x8000))
        return;
    map_script_base_8c15_at((u8)((e->bind >> 8) & 31), (u8)(e->bind & 31),
                            e->variant, (u8)(e->script & 3));
}

static void base_step(Slot *e)
{
    u8 idx = (u8)(e->variant - 73);
    u8 p5;
    u8 pat;
    u8 rec;
    u8 phase;
    u8 rate;
    u8 fire_acc;
    const u8 *p;
    u16 sum;

    /* 8a5a: until BIT 7, E700.1 -> Y+=8, then E150.1 else RET.
     * Hold: SET 7, Y+=0x10, table xo/yo, 8948 bind, fall into 8ae8. */
    if (!e->armed)
    {
        if (map_script_row_carry())
            e->y = (s16)(u8)((u8)e->y + 8);
        if (!(entity_base_flags() & 2))
            return;
        e->armed = 1;
        {
            u8 ypre = (u8)e->y;
            u8 col;
            u8 row;

            /* 8a7d L=Y then Y+=0x10; 8948 uses L (pre-+0x10), H=X-0x20
             * before table xo/yo at 8ac7. Store the NT cell like +06/+07
             * so later 8c15 paints the same tiles as the body (no live
             * VSCROLL re-bind → 16px south / 4th eye C>=0x18 skip). */
            e->y = (s16)(u8)(ypre + 0x10);
            if (idx > 6)
                idx = 0;
            if (map_script_8948_cell(e->x, (s16)ypre, &col, &row))
                e->bind = (u16)(0x8000 | ((u16)col << 8) | row);
            else
                e->bind = 0;
            e->y = (s16)(u8)((u8)e->y + k_base[idx][2]);
            e->x = (s16)(u8)((u8)e->x + k_base[idx][3]);
        }
        e->script = (u8)(e->script | 0x80);
        /* MSX first 8c15 is the first phase step. Paint phase 0 on arm
         * so all four eyes exist (closed) before the first carry; the
         * 4th eye was never opened if its later C>=0x18 skip fired. */
        base_8c15(e);
    }

    /* 8ae8 BIT 1 +05: type 79 last-hit 8ba1 SET +05.1 keep 0xCF, then 8bb6.
     * +19 is 0 after 7904 kill; DEC wraps 255 frames, scatter every 4 (AND 3),
     * then 8baa -> 8ca2 -> 8c80 (HP==0 -> 8d07). No 44ca/7904 while dying. */
    if (e->variant == 79 && (e->aux & 0x02))
    {
        e->hp--;
        if (!e->hp)
        {
            base_finish_death(e);
            return;
        }
        if ((e->hp & 3) == 0)
            scatter_expl(e->x, e->y);
        return;
    }

    /* 8afa BIT 2,E150: timeout -> 8f45 (Y+=8 per E700.1, Y>=0xD0 clear). */
    if (entity_base_flags() & 4)
    {
        if (step_8f45(e))
            return;
    }

    if (idx > 6)
        idx = 0;
    p5 = k_base[idx][4];
    if (s_e150 & 8)
        p5 <<= 1;           /* E150 bit3: SLA IX+15 (once in ROM via +05.0) */
    pat = (u8)(e->dest & 7);
    rec = (u8)((e->dest >> 3) & 0x1F);
    phase = e->script & 3;
    /* 8aef type79 -> 8b6c (skip anim). 8b18: rage and phase==3 skip anim
     * so the fire window stays open at double p5. */
    if (e->variant != 79 && !((s_e150 & 8) && phase == 3))
    {
        p = k_pat_blob + k_pat_off[pat] + rec;
        if (p[0] == 0)
        {
            rec = 0;
            p = k_pat_blob + k_pat_off[pat];
            e->dest = (u16)((e->dest & (u16)~0x00F8) | ((u16)rec << 3));
        }
        if (phase == 0)
            rate = p[0];
        else if (phase == 3)
            rate = p[2];
        else
            rate = p[1];

        sum = (u16)e->timer + rate;
        if (sum > 255)
        {
            s8 step = (e->script & 0x10) ? -1 : 1;
            s8 np = (s8)(phase + step);
            e->timer = 0;
            if (np <= 0)
            {
                rec = (u8)(rec + 3);
                e->dest = (u16)((e->dest & (u16)~0x00F8) | ((u16)(rec & 0x1F) << 3));
                e->script = (u8)((e->script & 0xF0) | 0);
                e->script = (u8)(e->script & (u8)~0x10);
            }
            else if (np >= 3)
            {
                e->script = (u8)((e->script & 0xF0) | 3 | 0x10);
            }
            else
                e->script = (u8)((e->script & 0xF0) | (u8)np | (e->script & 0x10));
            /* 8b60 CALL 8c15 after a phase step. */
            base_8c15(e);
        }
        else
            e->timer = (u8)sum;
    }

    phase = e->script & 3;
    /* 8b6c fire acc: no on-screen Y gate (Y_motion 0xD0 is airborne only). */
    if (phase == 3 || e->variant == 79)
    {
        fire_acc = (u8)(e->dest >> 8);
        sum = (u16)fire_acc + p5;
        if (sum > 255)
        {
            e->dest = (u16)(e->dest & 0x00FF);
            base_fire(e);
        }
        else
            e->dest = (u16)((e->dest & 0x00FF) | (sum << 8));
    }
}

static void spawn_base_seg(Slot *e, u8 type, s16 x, s16 y)
{
    u8 idx = (u8)(type - 73);

    if (idx > 6)
        idx = 0;
    /* 8a5a: BIT 7 clear until E150.1. Table xo/yo applied at SET 7 (8ac7),
     * not at place. SAT name is hitbox size; sat_col=0 (no SAT). */

    e->kind = KIND_BASE;
    e->variant = type;
    e->hp = k_base[idx][1];
    e->sat = k_base[idx][0];
    e->timer = 0;
    e->script = 0;
    e->ground = 1;
    e->armed = 0;
    e->aux = 0;
    e->clock = 0;
    e->dest = s_pat_rr;     /* pattern index 0-7; record=0; fire_acc=0 */
    s_pat_rr++;
    if (s_pat_rr >= 8)
        s_pat_rr = 0;
    e->x = x;
    e->y = y;
    e->vx = 0;
    e->vy = 0;
    e->bind = 0;
    e->alive = 1;
    spr_detach(e);
}

static int is_port_type(u8 t)
{
    if (t >= 4 && t <= 18) return 1;
    if (t == 20) return 1;          /* lead_homing 0x14 */
    if (t == 21) return 1;          /* light_bar 0x15; child + stream leftover */
    if (t >= 22 && t <= 30) return 1;
    if (t == 31 || t == 32 || t == 33 || t == 34 || t == 36) return 1;
    if (t == 41) return 1;          /* pair_fragment 0x29; child + stream leftover */
    if (t == 44) return 1;
    if (t == 45) return 1;          /* light_bar_var 0x2D; child + stream leftover */
    if (t >= 46 && t <= 55) return 1;
    if (t >= 56 && t <= 59) return 1;
    if (t == 61 || t == 62) return 1;
    if (t == 63 || t == 64) return 1;
    if (t >= 65 && t <= 69) return 1;
    if (t == 70 || t == 71) return 1;
    if (t >= 73 && t <= 79) return 1;
    if (t == 82) return 1;
    if (t == 83) return 1;
    /* zanac.asm entity_jump_table 0x70B7: labeled handler_type* for
     * 1-3 (player/shot/fire), 4-25, 35-89 are all wired in this file
     * or player.c. Types 26-34 share the 7de2/7e78/7e9c/7f84/7f99
     * bodies already ported. Child-only 35/37-40/42/43/60/72/80/81/84-89
     * stay spawn_from_type==0 (is_port_type / stream leftover). */
    return 0;
}

static int spawn_from_type(u8 t)
{
    Slot *e;

    if (t == 68)
        return spawn_proto_box();
    if (t == 63)
    {
        /* Stream type63: same leftover as MSX (Y=0) + 71c5 X. */
        u8 r1 = rnd();
        u8 r2 = rnd();
        spawn_chip_at((s16)((u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28)), 0);
        return 1;
    }
    if (t == 64)
    {
        /* 8279: index spawn_type_list by E130/2 + R&3, clamp 0x5F,
         * write the byte into +00, RET. 0xBECC has 0x40 at 0/23/51, so a
         * 64 result leaves the slot as type 64 and the same handler runs
         * next frame. Force-44 invented a plane whenever the lookup was
         * 64 — wrong at idx 23 (18/24/16) and 51 (58/28/23). Re-roll
         * until the byte is not 64 (eventual MSX type; E130 stable). */
        u8 nt = 64;
        int guard = 0;

        while (nt == 64 && guard < 8)
        {
            u8 idx = (u8)((s_e130 >> 1) + (rnd() & 3));
            if (idx > 0x5F)
                idx = 0x5F;
            nt = spawn_type_list[idx];
            guard++;
        }
        if (nt == 64 || !is_port_type(nt))
            nt = 44;
        return spawn_from_type(nt);
    }

    e = free_enemy();
    if (!e)
        return 0;
    if (t >= 4 && t <= 6)
    {
        /* Stream 4/5/6: 71c5 X, Y=0, SAT leftover 0 -> 256f countdown. */
        u8 r1 = rnd();
        u8 r2 = rnd();
        spawn_box(e, t, (s16)((u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28)), 0, 0);
    }
    else if (t == 10)
        spawn_duster(e);
    else if (t >= 12 && t <= 15)
        spawn_teruzo(e, t);
    else if (t >= 16 && t <= 18)
        spawn_luster(e, t);
    else if (t == 20)
    {
        /* handler_type20 8668 stream: random_x_pos 71c5, Y=0; first-frame
         * Xvel 8.8 via type20_init_vel. Y-home then 4898 u8 wrap-cull. */
        u8 r1 = rnd();
        u8 r2 = rnd();
        u8 x = (u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28);

        e->kind = KIND_EBULLET;
        e->variant = 20;
        e->hp = 1;
        e->ground = 0;
        e->x = (s16)x;
        e->y = 0;
        type20_init_vel(e);
        e->alive = 1;
        e->sat_col = 0x8F;      /* 8672 +04; TMS EC bit7 */
        spr_place(e, FRAME_LEAD);
    }
    else if (t == 56)
        spawn_sig(e);
    else if (t == 83)
        spawn_fireup(e);
    else if (t == 44)
    {
        /* 82d0 CALL 71c5: X=(H&0x7f)+(L&0x1f)+0x28, Y=0.
         * Aim origin + on-screen time. Map-script keeps place_ground XY. */
        u8 r1 = rnd();
        u8 r2 = rnd();
        spawn_ground_fall(e, t,
            (s16)((u8)((r1 & 0x7f) + (r2 & 0x1f) + 0x28)), 0, 0);
    }
    else if (t == 70 || t == 71)
        spawn_wide_at(e, t, (s16)(16 + (rnd() % 180)), -16, 0);
    else if (t == 82)
        spawn_wide_at(e, t, (s16)(16 + (rnd() % 180)), -16, 0);
    else if (t >= 46 && t <= 55)
        spawn_gun(e, t);
    else if (t == 61)
        spawn_descender(e);
    else if (t == 62)
        spawn_riser(e);
    else if (t == 34 || t == 65 || t == 66)
        spawn_stealth(e, t);
    else if (t == 67)
        spawn_med_circle(e);
    else if (t >= 73 && t <= 79)
        spawn_base_seg(e, t, (s16)(16 + (rnd() % 180)), -16);
    else if (t >= 7 && t <= 9)
        spawn_umber(e, t);
    else if (t == 11 || t == 69)
        spawn_spawner(e);
    else if (t >= 22 && t <= 25)
        spawn_veybar(e, t);
    else if (t >= 26 && t <= 29)
        spawn_swoop(e, t);
    else if (t == 30 || t == 32)
        spawn_gswoop(e, t);
    else if (t == 31 || t == 33)
        spawn_tracker(e, t);
    else if (t == 36)
        spawn_flash(e);
    else if (t == 57 || t == 58)
        spawn_pairdesc(e, t);
    else if (t == 59)
    {
        /* Bare table spawn: +0x1a unset -> dir 4 like type56 E=4 sibling. */
        const ModeAssets *a = mode_assets();
        init_type59(e, 8, (s16)(16 + (rnd() % (a->playfield_h / 2))), 4);
    }
    else if (t == 21 || t == 41 || t == 45)
    {
        /* Stream first frame: alloc writes type only (BF79). Handlers 8635 /
         * 852f / 85ee do not CALL 71c5; leftover XY is slot RAM. Port slots
         * are zeroed, so match type20's stream convention: 71c5 Y=0 then
         * the type init with leftover +0x1a = 0. */
        init_frag(e, (s16)random_x_71c5(), 0, 0, t);
    }
    else
        return 0;
    return 1;
}

static void spawn_tick(void)
{
    u8 slot;
    u8 ctr;
    u8 t;
    u16 idx;

    /* ground_struct_spawn_ctrl 0xBF2C.
     * Bit1 = stream active (E12D). Round 1 never sends cmd 0, so we
     * start with bit1 set at init - matching MSX gameplay start.
     * Bit0 = sticky update_spawn_table_ptr request (BE27 RES0).
     * E125 bit0 = BFA0 immediate type 44 (checked before bit3 block).
     * Bit3 = stream-block (SET at 8fd4, RES at 90c5 / 906f / 9325). */
    if (s_spawn_ctrl & 0x01)
    {
        s_spawn_ctrl = (u8)(s_spawn_ctrl & (u8)~0x01);
        alc_recompute();
    }
    if (s_e125 & 0x01)
    {
        /* BFA0: CALL 4496 / RET C / then RES 0,(E125) / LD (HL),0x44.
         * A full table must keep the husk latch (84c6) for the next tick.
         * 0x44 there is the entity TYPE BYTE and entity_dispatch indexes
         * entity_jump_table by type*2, so 0x44 = 68 = handler_type68_proto_box
         * (0x77A1), the three-box cluster. It is not decimal 44, which is
         * 0x2C = handler_type44_ground_structure (0x82D0). */
        if (spawn_from_type(68))
            s_e125 = (u8)(s_e125 & (u8)~0x01);
        return;
    }
    if (s_spawn_ctrl & 0x08)
        return;
    if (!(s_spawn_ctrl & 0x02))
        return;
    if (s_spawn_timer)
    {
        s_spawn_timer--;
        return;
    }
    s_spawn_timer = s_spawn_reload ? s_spawn_reload : 255;

    /* BF55: every-16th stream slot -> type 0x3D (61) descender.
     * Does not advance E135 / spawn_pos (BF94). */
    slot = s_stream_slot;
    s_stream_slot++;
    if ((slot & 0x0F) == 0)
    {
        spawn_from_type(61);
        return;
    }

    /* BF60-BF70: index E133 slice by E135, wrap on count (E136). */
    if (!s_e136)
        return;
    ctr = s_e135;
    s_e135++;
    if ((u8)(s_e136 - 1) == ctr)
        s_e135 = 0;
    idx = (u16)s_spawn_base + (u16)ctr;
    if (idx >= SPAWN_TYPE_LEN)
        return;
    t = spawn_type_list[idx];
    if (!t)
        return;
    if (!is_port_type(t))
        return;
    /* BF79 write type + BF7A E12F+=8 + BF8C INC E142 sat - only if slot ok. */
    if (!spawn_from_type(t))
        return;
    spawn_pos_add(8);
    s_e142++;
    if (!s_e142)
        s_e142--;
}

static void update_shots(void)
{
    u8 i;
    for (i = 0; i < SHOT_SLOTS; i++)
    {
        Slot *s = &s_shot[i];
        if (!s->alive)
            continue;
        /* 7221 BIT 7 clear: init SET 7 RET. 7225 JP 4898 is the
         * already-armed path only. Spawn wrote type 2 at ship XY;
         * 44F9 CP 0x82 then hits that SAT, not one vel-step up. */
        if (s_shot_init_ret[i])
        {
            s_shot_init_ret[i] = 0;
            if (s->spr)
                spr_sync(s);
            continue;
        }
        /* 7225 -> 4898: +0c=1 Y-only, unsigned Y>=0xD0. */
        if (step_88_y_4898(s))
            continue;
        if (s->spr)
            spr_sync(s);
    }
}

static void fire_offscreen_reset(u8 fn)
{
    /* 0x749c: off-screen + E14D==0 -> fire_reset 7544. Fire 1/4/5/6. */
    if ((fn == 1 || fn == 4 || fn == 5 || fn == 6) && player_fire_ammo() == 0)
        player_fire_reset();
}

static void update_fire(void)
{
    const ModeAssets *a = mode_assets();
    Slot *f = &s_fire;
    u8 fn;
    u8 cycle;

    if (!f->alive)
    {
        /* Failed spr_place after 728F must not leak the skip into later 7306. */
        s_fire7_life_ticked = 0;
        fire7_cram_restore();
        return;
    }

    fn = player_fire_num();
    if (fn == 2)
    {
        /* Field Shutter 0x72F5: Y=player_Y-8, X=player_X every frame. */
        f->x = player_x();
        f->y = (s16)(player_y() - 8);
    }
    else if (fn == 3)
    {
        /* Circular 0x735D: dir++ each frame, 4cf7 +17=0xC3 (*36),
         * offset += vel (IX+08 Y / IX+0a X). Share apply_dir_4cf7. */
        s16 cy;
        s16 cx;
        s16 max_x;

        s_fdir = (u8)((s_fdir + 1) & 0x0F);
        apply_dir_4cf7(f, s_fdir, 0xC3);
        s_fyoff = (s16)(s_fyoff + (s16)f->bind);
        s_fxoff = (s16)(s_fxoff + (s16)f->dest);
        cy = clamp16(player_y(), 0x38, 0xA7);
        max_x = (s16)(a->playfield_w - (256 - 0xA7));
        if (max_x < 0xA7)
            max_x = 0xA7;
        cx = clamp16(player_x(), 0x48, max_x);
        /* 7396/73be: ADD A,H is 8-bit. 733d/7349 seed 0xC000/0xF600.
         * Signed (cy + off>>8) puts 0x38+0xC0 at -8; MSX SAT Y is 0xF8. */
        f->y = (s16)(u8)((u8)cy + (u8)((u16)s_fyoff >> 8));
        f->x = (s16)(u8)((u8)cx + (u8)((u16)s_fxoff >> 8));
        /* 73c2: CALL 730B after orbit; underflow JP 7544 skips 48b8. */
        if (player_fire_life_tick())
            return;
    }
    else if (fn == 4)
    {
        /* Vibrator 0x7439: vx += accel; if X>=anchor reverse; Y until +0x1C=0. */
        s_fvx = (s16)(s_fvx + s_faccel);
        if (f->x >= s_fanchor)
            s_fvx = (s16)(s_fvx - (s16)(s_faccel * 2));
        f->x = (s16)(f->x + (s_fvx >> 8));
        if (f->timer)
        {
            f->timer--;
            f->y = (s16)(f->y + f->vy);
        }
        /* 74e2 DEC +1b is type19 expire (per hit), not 7439. */
    }
    else if (fn == 5)
    {
        /* Rewinder 0x7464: clamp Y>=16, X=player_X, vy += 4 (8.8), die behind ship. */
        if (f->y < 0x10)
            f->y = 0x10;
        f->x = player_x();
        if ((s16)(player_y() + 0x10) < f->y)
        {
            spr_kill(f);
            fire_offscreen_reset(5);
            return;
        }
        /* 7484: Yvel += 4 (8.8), then 4898 Y_motion only (+0c=1).
         * Do not drop IX+06 leftover (y += s_fvy>>8 was integer-only). */
        s_fvy = (s16)(s_fvy + 4);
        f->bind = (u16)s_fvy;
        if (step_88_y_4898(f))
        {
            fire_offscreen_reset(5);
            return;
        }
    }
    else if (fn == 1 || fn == 6)
    {
        /* Fire 1 72ea -> 72de + 4898. Fire 6 7494 -> 4898 only.
         * Both +0c=1 Yvel 0xFE00. 72de color INC is fire 1 (cycle). */
        if (step_88_y_4898(f))
        {
            fire_offscreen_reset(fn);
            return;
        }
    }
    else if (fn == 0 || fn == 7)
    {
        /* 72de -> 4898: +0c=3 X|Y 8.8, unsigned Y>=0xD0 / X>=0xD1.
         * Fire 0 speed 0xC2; fire 7 speed 0xC3.
         * 7306: CALL 730B then JR 72de. Underflow skips motion.
         * 7253 BIT 7 mutex: spawn 728F already ticked 730B this frame. */
        if (fn == 7)
        {
            u8 skip = s_fire7_life_ticked;

            s_fire7_life_ticked = 0;
            if (!skip && player_fire_life_tick())
                return;
        }
        if (step_88_4898(f))
        {
            fire_offscreen_reset(fn);
            return;
        }
    }
    else
    {
        f->x += f->vx;
        f->y += f->vy;
    }

    /* Fire 0/7 script is 4898 X frac; fire 1/6 timer is Y frac. Do not
     * use those as a blink tick. 72de is color INC only; SAT write
     * every frame. */
    if (fn != 0 && fn != 1 && fn != 6 && fn != 7)
        f->script++;
    /* fire 0/1/2/7 run: INC sat_color, keep TMS EC bit7 so SAT overlap
     * stays graphic overlap. 3/4/5 stay 0x8F. Fire 7 is Japan 72de
     * INC+AND 0x8F on a dedicated CRAM index (tiles stay nibble 13). */
    cycle = (u8)(fn == 0 || fn == 1 || fn == 2 || fn == 7);
    if (cycle)
    {
        /* Japan 72de is one SAT-colour INC. Fire 7 already cycles CRAM
         * on PAL2[13]; 0/1/2 are the same INC and only one fire is live,
         * so they share that index. Per-frame tile remap of 0/1/2 was
         * the remaining colour-cycle hitch. */
        fire7_cycle_cram(f);
    }
    if (f->spr)
    {
        s16 fdx = mode_draw_x(f->x, f->sat_col);

        spr_sync(f);
        /* spr_sync hid HUD overlap. Do not SPR_setVisibility(VISIBLE)
         * over the bar (that flicker). Blink/expire only on-playfield. */
        if (mode_hud_overlap(fdx, MODE_SPR_W))
            SPR_setVisibility(f->spr, HIDDEN);
        else if (cycle)
            spr_vis_playfield(f->spr, fdx, mode_draw_y(f->y),
                              (fn == 0 || fn == 1 || fn == 7) ? 1 : (f->script & 1));
        else
            spr_vis_playfield(f->spr, fdx, mode_draw_y(f->y), 1);
    }

    if (fn != 0 && fn != 1 && fn != 2 && fn != 3 && fn != 6 && fn != 7)
    {
        if (f->x < -16 || f->x > (s16)(a->playfield_w + 8)
            || f->y < -24 || f->y > (s16)(a->playfield_h + 8))
        {
            spr_kill(f);
            fire_offscreen_reset(fn);
        }
    }
}

/* 4898 Y_motion_sub / X_motion_sub: u8 8.8 ADD HL,DE then unsigned
 * Y>=0xD0 / X>=0xD1 -> entity_clear. Sim stays MSX; letterbox is
 * slot_draw_y at spr_sync only (do not cull in screen Y). */
static int step_88_4898(Slot *e)
{
    u16 xpos = (u16)(((u16)((u8)e->x) << 8) | (u8)e->script);
    u16 ypos = (u16)(((u16)((u8)e->y) << 8) | (u8)e->timer);

    xpos = (u16)(xpos + e->dest);
    ypos = (u16)(ypos + e->bind);
    e->script = (u8)xpos;
    e->timer = (u8)ypos;
    e->x = (s16)(u8)(xpos >> 8);
    e->y = (s16)(u8)(ypos >> 8);
    e->vx = 0;
    e->vy = 0;
    if ((u8)e->y >= 0xD0 || (u8)e->x >= 0xD1)
    {
        spr_kill(e);
        return 1;
    }
    return 0;
}

/* 4898 Y_motion_sub only. Fire 5 +0c=1 (X is overwritten from the ship). */
static int step_88_y_4898(Slot *e)
{
    u16 ypos = (u16)(((u16)((u8)e->y) << 8) | (u8)e->timer);

    ypos = (u16)(ypos + e->bind);
    e->timer = (u8)ypos;
    e->y = (s16)(u8)(ypos >> 8);
    e->vy = 0;
    if ((u8)e->y >= 0xD0)
    {
        spr_kill(e);
        return 1;
    }
    return 0;
}

static void luster_step(Slot *e)
{
    /* Active 7c43 (16/17) / 7cd8 (18) then entity_update via 79ae.
     * 16: +0c=1 Y 8.8 only. 17/18: +0c=0x13 X_homing then Y|X 8.8.
     * X_homing_sub: tgt=aux(+14), accel=+16, B=+17 (4 / 2).
     * 8ddb children at parent XY. 4898 u8 8.8 + Y>=0xD0 / X>=0xD1. */
    u16 xvel = e->dest;
    u16 yvel = e->bind;
    u16 xpos;
    u16 ypos;
    u8 y = (u8)e->y;

    if (e->variant == 18)
    {
        /* 7ce1: DEC +0x1d; on 0 reload 0x30, SAT 0x74/0x7C, 8ddb type37. */
        e->clock--;
        if (!e->clock)
        {
            e->clock = 0x30;
            spr_place(e, FRAME_LUSTER_A);
            marker_place(e, FRAME_LUSTER_A_C);
            spawn_frag(e->x, e->y, 0, 37);
        }
        /* 7cfc: +1d==8 -> SAT 0x78/0x80 (open telegraph). */
        if (e->clock == 8)
        {
            spr_place(e, FRAME_LUSTER);
            marker_place(e, FRAME_LUSTER_C);
        }
    }
    else
    {
        /* 7c43: 0x18-band SAT 0x74/0x7C; 0x10-band SAT 0x78/0x80 + type38. */
        u8 mask = (e->variant == 16) ? 0xC0 : 0xE0;

        if ((u8)(((u8)(y + 0x18) & mask) - 0x18) == y)
        {
            spr_place(e, FRAME_LUSTER_A);
            marker_place(e, FRAME_LUSTER_A_C);
        }
        else if ((u8)(((u8)(y + 0x10) & mask) - 0x10) == y)
        {
            spr_place(e, FRAME_LUSTER);
            marker_place(e, FRAME_LUSTER_C);
            spawn_frag(e->x, e->y, e->clock, 38);
        }
    }

    if (e->variant == 17 || e->variant == 18)
    {
        u8 accel = (e->variant == 17) ? 0x40 : 0x0e;
        u8 iters = (e->variant == 17) ? 4 : 2;
        u8 i;
        u8 x = (u8)e->x;

        for (i = 0; i < iters; i++)
        {
            if (x != e->aux)
            {
                if (x < e->aux)
                    xvel = (u16)(xvel + accel);
                else
                    xvel = (u16)(xvel - accel);
            }
        }
        e->dest = xvel;
    }

    ypos = (u16)(((u16)((u8)e->y) << 8) | (u8)e->timer);
    ypos = (u16)(ypos + yvel);
    e->timer = (u8)ypos;
    e->y = (s16)(u8)(ypos >> 8);

    if (e->variant == 17 || e->variant == 18)
    {
        xpos = (u16)(((u16)((u8)e->x) << 8) | (u8)e->script);
        xpos = (u16)(xpos + xvel);
        e->script = (u8)xpos;
        e->x = (s16)(u8)(xpos >> 8);
    }

    e->vx = 0;
    e->vy = 0;

    /* Y_motion_sub CP 0xD0; X_motion_sub CP 0xD1 (17/18 bit1 only). */
    if ((u8)e->y >= 0xD0
        || ((e->variant == 17 || e->variant == 18) && (u8)e->x >= 0xD1))
        spr_kill(e);
}

/* handler_type84_wide_variant 0x8EC7: DEC +0x1c; on 0 reload +0x1d=0x18,
 * alloc, then type 84/85/86 emit type 38 / aimed type 21 / rotating type 21. */
static void wide_variant_step(Slot *e)
{
    u8 t = e->variant;
    u8 dir;
    u8 stype;

    if (t < 84 || t > 86)
        return;
    if (!e->armed)
        return;                 /* 8f25 uninit: handler rest skipped */
    if (e->timer)
        e->timer--;
    if (e->timer)
        return;

    /* reload +0x1c from +0x1d. Type overwrite only if a child slot exists. */
    e->timer = 0x18;
    if (!free_enemy())
        return;

    if (t == 84)
    {
        /* 8f13: +0x1c=0x0A; INC +0x1e; C=(+0x1e*2)&0x0F; A=0x26 type 38. */
        e->timer = 0x0A;
        e->script++;
        dir = (u8)((e->script << 1) & 0x0F);
        stype = 38;
    }
    else if (t == 85)
    {
        /* 8efc: player X (E302) vs own X. E710 NZ -> C, Z -> B. */
        if ((u8)player_x() >= (u8)e->x)
            dir = map_script_scroll_speed() ? 1 : 0;
        else
            dir = map_script_scroll_speed() ? 7 : 8;
        stype = 21;
    }
    else
    {
        /* 8ee3: +0x1c=8; INC +0x1e; C=((+0x1e)&3)*4+2; A=0x15 type 21. */
        e->timer = 8;
        e->script++;
        dir = (u8)(((e->script & 3) << 2) + 2);
        stype = 21;
    }
    spawn_child_dir(e->x, e->y, stype, dir);
}

static void update_enemies(void)
{
    const ModeAssets *a = mode_assets();
    u8 i;
    s16 max_x = (s16)(a->playfield_w - 16);
    s16 max_y = (s16)(a->playfield_h + 8);

    for (i = 0; i < ENEMY_SLOTS; i++)
    {
        Slot *e = &s_en[i];
        if (!e->alive)
            continue;

        if (e->kind == KIND_PDEAD)
        {
            /* handler_type60 0x869E / anim 0x86F3 tick=4, 11 frames.
             * +0F starts at 1 (empty frame 0 skipped); wrap +0F=0 -> E102.0. */
            if (!e->script)
            {
                sound_play_event(SND_EV_DEATH);
                /* 86c3-86dc: +0F=1,+10=0x0B,+0D=4,+0E=4,+0C=4.
                 * +0D=4: first three 4898 ticks write nothing. */
                e->clock = 4;
                e->aux = 1;
                e->script = 1;
            }
            if (!e->aux)
            {
                /* 86eb: SET 0,(E102); clear slot. */
                player_e102_set(0x01);
                spr_kill(e);
                continue;
            }
            anim_sub_4912(e, k_t60_sat, k_t60_col, 11, 4);
            if (e->spr)
                spr_sync(e);
            continue;               /* bit2-only; no shared motion/cull */
        }
        else if (e->kind == KIND_EXPL)
        {
            /* handler_type35 0x8446: bit7 clear = first frame ALC dump +
             * ev17 + 4a6a score + 84d1 arm (+0E=4,+0F=1,+10=6). */
            if (!e->script)
            {
                u16 lo = (u16)s_spawn_pos_lo + 0x10;
                u8 a;
                u16 w;

                s_spawn_pos_lo = (u8)lo;
                if (lo > 0xFF)
                    entity_inc_encounter_a();

                /* 8457: E142 < 0x11 -> shot_rate_table[E142+1] into E131. */
                if (s_e142 < 0x11)
                {
                    a = k_shot_rate[s_e142 + 1];
                    w = (u16)s_e131 + a;
                    s_e131 = (u8)w;
                    if (w > 255)
                        entity_inc_encounter_b();
                }
                /* 8473: E141 < 8 -> 0x24-(E141*4); else 1. Into E131. */
                if (s_e141 < 8)
                    a = (u8)(0x24 - (s_e141 << 2));
                else
                    a = 1;
                w = (u16)s_e131 + a;
                s_e131 = (u8)w;
                if (w > 255)
                    entity_inc_encounter_b();
                s_e142 = 0;
                s_e141 = 0;

                /* 8495 ev17 + 849c add_score_for_subtype(+0x18) + 84bc. */
                sound_play_event(SND_EV_EHIT);
                award_subtype(e->variant);
                tick_e124_84bc();
                /* 84a3-84b9: +0D=1,+0E=4,+0F=1,+10=6, table 84d1.
                 * 84c9 JP 4898 same frame: 4912 writes table[1]. */
                e->clock = 1;
                e->aux = 1;
                e->script = 1;
            }
            /* 84c9: +0F==0 -> clear; else entity_update bit2 anim. */
            if (!e->aux)
            {
                spr_kill(e);
                continue;
            }
            anim_sub_4912(e, k_t35_sat, k_t35_col, 6, 4);
            if (e->spr)
                spr_sync(e);
            continue;               /* 84c9: +0c bit2 anim only, no Y cull */
        }
        else if (e->kind == KIND_DUSTER)
        {
            duster_step(e);
            if (step_88_4898(e))
                continue;
        }
        else if (e->kind == KIND_TERUZO)
        {
            /* 7b07: +0c=3 X|Y 8.8; dir reload every 8f via set_vel speed 4. */
            if (e->clock)
                e->clock--;
            if (!e->clock)
            {
                e->clock = 8;
                teruzo_step(e);
            }
            if (step_88_4898(e))
                continue;
        }
        else if (e->kind == KIND_LUSTER)
        {
            luster_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_SIG)
        {
            /* type56 @ 819d and type59 @ 8269 both join 81a8: +0c=3
             * X|Y 8.8 via dest/bind + script/timer (set_velocity_from_dir speed 5).
             * 4898 u8 wrap-cull Y>=0xD0 / X>=0xD1. */
            if (step_88_4898(e))
                continue;
            /* 81c3: +04 ^= 0x09 (0x8F<->0x86) */
            spr_set_sat_col(e, (u8)(e->sat_col ^ 0x09));
        }
        else if (e->kind == KIND_BOX)
        {
            box_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_CHIP)
        {
            chip_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_GROUND)
        {
            /* type44 82f9 CALL 4898 +0c=3: u8 8.8 wrap-cull
             * Y>=0xD0 / X>=0xD1. Signed s32 + playfield max_y=200 /
             * X>256 killed Y=201..207 and X=0xD1..0xFF. */
            if (step_88_4898(e))
                continue;
        }
        else if (e->kind == KIND_FIREUP)
        {
            fireup_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_HUSK)
        {
            husk_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_ORB)
        {
            orb_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_GUN)
        {
            gun_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_STEALTH)
        {
            /* 7f99/8012: volley then entity_update 4898 +0c=3 X|Y 8.8
             * (set_velocity_from_dir speed 1 at spawn). u8 wrap-cull
             * Y>=0xD0 / X>=0xD1 (s32 X lived past 0xD1; wrap re-entered). */
            stealth_step(e);
            if (step_88_4898(e))
                continue;
        }
        else if (e->kind == KIND_DESCEND)
        {
            descender_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_RISER)
        {
            /* 8709 BIT 7 clear: 870f-8723 init then 8727 RET.
             * 8385 already wrote type 0x3E; this visit is the init RET.
             * 8728 poke + 874a 4898 start next frame. */
            if (s_riser_init_ret[i])
            {
                s_riser_init_ret[i] = 0;
                continue;
            }
            riser_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_CIRCLE)
        {
            /* 83ee idle: JP 48b8 (XOR only). Armed 8424 JP 4898
             * +0c=3: u8 wrap-cull Y>=0xD0 / X>=0xD1. */
            circle_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_UMBER)
        {
            umber_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_VEYBAR)
        {
            veybar_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_SWOOP)
        {
            swoop_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_TRACKER)
        {
            tracker_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_GSWOOP)
        {
            gswoop_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_FLASH)
        {
            flash_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_PAIRDESC)
            pairdesc_step(e);
        else if (e->kind == KIND_SPAWNER)
        {
            spawner_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_BASE)
        {
            base_step(e);
            if (!e->alive)
                continue;
        }
        else if (e->kind == KIND_WIDE)
        {
            /* 8eb7 CALL 8f25 before the variant fire body. Arming frame
             * JP (HL) into the body; 8f45 is the next-tick BIT 7 path. */
            if (!e->armed)
            {
                (void)step_8f25_unarmed(e);
                /* Arming JP (HL): CF clear, 8ebc init (already at spawn).
                 * 8f45 / DEC +0x1c start next tick. */
            }
            else if (step_8f45(e))
                continue;
            else
                wide_variant_step(e);
        }
        else if (e->kind == KIND_FIREBOX)
        {
            /* 87ab CALL 8f25; 87e2 digit after BIT 7 / arming JP (HL). */
            if (!e->armed)
            {
                (void)step_8f25_unarmed(e);
                if (e->armed && !e->script)
                {
                    map_script_stamp_82_digit(e->x, e->y, (u8)e->dest);
                    e->script = 1;
                }
            }
            else if (step_8f45(e))
                continue;
            else if (!e->script)
            {
                map_script_stamp_82_digit(e->x, e->y, (u8)e->dest);
                e->script = 1;
            }
        }
        else if (e->kind == KIND_EBULLET
            && (e->variant == 21 || e->variant == 37 || e->variant == 38
                || e->variant == 41 || e->variant == 42 || e->variant == 43)
            && s_ebullet_init_ret[i])
        {
            /* 84fa / 8524 / 857e / 8656: SET 7 RET.
             * 42/43 85ed: XOR then RET (type already 0xA5/0xA6). No 4898,
             * no 8659, no 857f DEC +15. SAT stays at spawn XY this visit. */
            s_ebullet_init_ret[i] = 0;
            if (e->spr || e->mspr)
                spr_sync(e);
            continue;
        }
        else if (e->kind == KIND_EBULLET && e->variant == 20)
        {
            /* +0c=0x0B: Y_homing + Y_motion + X_motion (no X_homing bit4).
             * Y_homing_sub 0x4942: tgt +13=0xFF, accel +15=0x0C, B=+17=1.
             * Then 4898 u8 8.8 wrap-cull Y>=0xD0 / X>=0xD1 (type45 extra-threat
             * hole: s32 X lived past 0xD1; Y wrap re-entered). */
            if ((u8)e->y != 0xFF)
                e->bind = (u16)(e->bind + 0x000C);
            if (step_88_4898(e))
                continue;
        }
        else if (e->kind == KIND_EBULLET
            && (e->variant == 21 || e->variant == 37 || e->variant == 38
                || e->variant == 42 || e->variant == 43 || e->variant == 45))
        {
            /* 8.8 vels (37/38/21/45 clean; 42/43 XOR'd at spawn): dest=Xvel,
             * bind=Yvel, script/timer fracs. Keep apply_dir_88.
             * u8 wrap + 4898 Y>=0xD0 / X>=0xD1 (same as luster 17/18).
             * Type 21 active 8659: LD A,R / AND 0x0F / OR 0x80 / +04 then
             * 4898 / 44ba. Init 863b still writes no +04. spr_kill zeros
             * sat_col; without 8659 EC never arms and the bar draws 32px
             * right of SAT X.
             * Type 45 (0x8608): DEC clock/+0x1c before 4898; on 0: R bit0 ?
             * dir += (R&8)-4 + apply_dir_88(speed) : reload 0x28 then DEC (0x27).
             * 8625: SAT +03 = 0x18 + ((clock&1)<<3) every active frame. */
            if (e->variant == 21)
                spr_set_sat_col(e, (u8)(0x80 | (rnd() & 0x0F)));
            if (e->variant == 45)
            {
                if (e->clock)
                    e->clock--;
                if (!e->clock)
                {
                    u8 r = rnd();
                    if (r & 1)
                    {
                        u8 speed = (u8)(e->aux >> 4);
                        u8 d = (u8)((e->aux & 15) + (r & 8) - 4);
                        e->aux = (u8)((speed << 4) | (d & 15));
                        apply_dir_88(e, (u8)(d & 15), speed);
                    }
                    /* 8604 LD 0x28 then 8608 DEC => SAT sees 0x27 (odd/med). */
                    e->clock = 0x27;
                }
                /* clock LSB 0: FRAME_LIGHT_BAR SAT 0x18; 1: FRAME_MED_CIRCLE 0x20 */
                spr_place(e, (e->clock & 1) ? FRAME_MED_CIRCLE : FRAME_LIGHT_BAR);
            }
            if (step_88_4898(e))
                continue;
        }
        else if (e->kind == KIND_EBULLET && e->variant == 41)
        {
            /* 0x857f: DEC +0x15; Z -> reload 2 and INC/DEC +0x1b by +0x1a bit4.
             * 4cf7(+0x1b) speed 4, then ADD HL,(+1c/+1e) speed-2 seed, 4898.
             * apply_dir_88 would zero script/timer (frac) every frame. */
            u8 meta = e->aux;
            u8 heading = (u8)(meta & 15);
            u8 count = (u8)(meta >> 5);
            u8 seed = e->clock;
            u8 ih;
            u8 hd;

            if (count)
                count--;
            if (!count)
            {
                count = 2;
                if (meta & 0x10)
                    heading = (u8)((heading - 1) & 15);
                else
                    heading = (u8)((heading + 1) & 15);
            }
            e->aux = (u8)((count << 5) | (meta & 0x10) | heading);
            hd = (u8)(heading & 15);
            ih = (u8)((seed & 0x10)
                ? ((seed + 0xFC) & 15)
                : ((seed + 4) & 15));
            e->dest = (u16)((s16)(k_unit_y[hd] * 4) + (s16)(k_unit_y[ih] * 2));
            e->bind = (u16)((s16)(k_unit_x[hd] * 4) + (s16)(k_unit_x[ih] * 2));
            e->vx = 0;
            e->vy = 0;
            if (step_88_4898(e))
                continue;
        }
        /* Type 69: X drifts only on successful fire (spawner_step); vx holds
         * drift delta and must not feed the shared integer pass.
         * WIDE/FIREBOX Y is 8f25/8f45 in the handler (CALL before body). */
        if (e->kind != KIND_SPAWNER
            && e->kind != KIND_HUSK
            && e->kind != KIND_BASE
            && e->kind != KIND_WIDE
            && e->kind != KIND_FIREBOX
            && e->kind != KIND_GUN)
        {
            e->x += e->vx;
            e->y += e->vy;
        }
        /* Type 69 retires on count==0 only (7abc entity_clear); u8 X wrap
         * at bounce must not trip playfield cull. Luster 16-18, duster/teruzo/sig,
         * stealth 34/65/66, type44 ground, type67 med_circle, 8.8 leads/bars
         * 20/21/37/38/41/42/43/45, umber 7-9, veybar 22-25, swoop 26-29,
         * tracker 31/33, gswoop 30/32, box 4/5/6 / chip 63, and 4898 Y-only 36/61/62/72/83 use
         * unsigned Y>=0xD0 (letterbox is draw-only). Exclude them so
         * Y=201..207 is not culled 7px early. */
        if (e->kind != KIND_SPAWNER
            && e->kind != KIND_HUSK
            && e->kind != KIND_WIDE
            && e->kind != KIND_FIREBOX
            && e->kind != KIND_BASE
            && e->kind != KIND_GUN
            && e->kind != KIND_LUSTER
            && e->kind != KIND_DUSTER
            && e->kind != KIND_TERUZO
            && e->kind != KIND_SIG
            && e->kind != KIND_STEALTH
            && e->kind != KIND_ORB
            && e->kind != KIND_RISER
            && e->kind != KIND_DESCEND
            && e->kind != KIND_FIREUP
            && e->kind != KIND_FLASH
            && e->kind != KIND_BOX
            && e->kind != KIND_CHIP
            && e->kind != KIND_GROUND
            && e->kind != KIND_CIRCLE
            && e->kind != KIND_GSWOOP
            && e->kind != KIND_TRACKER
            && e->kind != KIND_SWOOP
            && e->kind != KIND_VEYBAR
            && e->kind != KIND_UMBER
            && !(e->kind == KIND_EBULLET
                && (e->variant == 20 || e->variant == 21 || e->variant == 37
                    || e->variant == 38 || e->variant == 41 || e->variant == 42
                    || e->variant == 43 || e->variant == 45))
            && (e->x < -16 || e->x > max_x + 16
                || (e->kind != KIND_GSWOOP && e->y > max_y)
                || e->y < -24))
        {
            spr_kill(e);
            continue;
        }
        if (e->spr || e->mspr)
            spr_sync(e);
    }
}

static void box_death_drop(s16 sx, s16 sy);
static void box_kill_7878(Slot *e);

static void box_death_drop(s16 sx, s16 sy)
{
    /* 788f: in-place type 38 + two 8ddb. Port: three type-38 frags. */
    spawn_frag(sx, sy, 3, 38);
    spawn_frag(sx, sy, 5, 38);
    spawn_frag(sx, sy, 4, 38);
}

/* 7878 after 7904 Z (shot or 44BA ship). +18 from 453E is the box type.
 * CP 5 RET Z (stay type 35; 849c next tick). CP 4 -> 788f. Else 7882.
 * No play_sound_event; ev17 is type35 first frame only. */
static void box_kill_7878(Slot *e)
{
    u8 drop = e->variant;
    s16 sx = e->x;
    s16 sy = e->y;

    if (drop == 5)
    {
        become_expl(e, drop);
        return;
    }
    if (drop == 4)
    {
        spr_kill(e);
        box_death_drop(sx, sy);
        return;
    }
    become_chip(e);
}

/* 74e2: type19 expire for fire 4. 74a4 remaps 3->19 on 453E, then
 * 74e2 DEC +1b (one hit), SAT 0x20 at 0x1E, color 0x81 at 0x0F,
 * Z -> 7507 (ammo 0 fire_reset else 48d0). ev24 (A=0x18) every 74e2
 * is AY leave-alone; play once when +1b is still the 7435 seed. */
static void fire4_expire_hit(Slot *f)
{
    if (!f->alive)
        return;
    if (s_fexpire == 0x3C)
        sound_play_event(SND_EV_FIRE_EXPIRE);
    if (s_fexpire)
        s_fexpire--;
    if (s_fexpire == 0x1E)
        spr_place(f, FRAME_MED_CIRCLE);
    if (s_fexpire == 0x0F)
        spr_set_sat_col(f, 0x81);
    if (!s_fexpire)
    {
        spr_kill(f);
        fire_offscreen_reset(4);
    }
}

static void collide_bolt_enemies(Slot *bolt, u8 persist)
{
    u8 j;
    u8 bolt_sat = bolt->sat ? bolt->sat : (u8)0x28;

    for (j = 0; j < ENEMY_SLOTS; j++)
    {
        Slot *e = &s_en[j];
        s16 sx, sy;
        u8 drop;
        u8 kind;
        if (!e->alive)
            continue;
        /* Shots: 44F9 (44BA/44CA). Fire: E14E 44D4 bit0 / 44F9 bit1. */
        if (bolt == &s_fire)
        {
            if (!enemy_takes_fire(e))
                continue;
        }
        else if (!enemy_takes_shots(e))
            continue;
        if (!hit_overlap_slot(bolt->x, bolt->y, bolt_sat, e))
            continue;

        if (!persist)
            spr_kill(bolt);
        else if (persist == 2)
        {
            /* 74e2 type19 expire: DEC +1b once per hit, then 7439. */
            fire4_expire_hit(bolt);
        }
        else if (persist == 4)
        {
            /* type19 7511: explode_enemies + ev19 + 48d0 + 749c.
             * 8a3e skips type>=0x46, so 44CA structures still 7904. */
            entity_explode_airborne();
            sound_play_event(SND_EV_PLASMA);
            spr_kill(bolt);
            fire_offscreen_reset(6);
            if (e->kind == KIND_EXPL)
                return;
        }
        else if (persist == 1)
        {
            /* fire 2 expire 0x74C1: ev24, DEC E14D, FF -> fire_reset.
             * ammo == 0x14 -> SAT name 0x20 (pat 8). */
            player_fire_dec_ammo();
            if (player_fire_ammo() == 0xFF)
            {
                spr_kill(bolt);
                player_fire_reset();
            }
            else
            {
                sound_play_event(SND_EV_FIRE_EXPIRE);
                if (player_fire_ammo() == 0x14)
                    spr_place(bolt, FRAME_MED_CIRCLE);
            }
        }
        /* persist 3: type19 expire is the live update (1/3/5/7 piercing). */
        /* 8833 child 0xD1: 7904 BIT 7 skips 880d. 453e still remaps the
         * bolt (shot consumed) then DEC 0->255 and restores type 0xD1.
         * Do not fall into 8824/88c2; that punch is type-81 death. */
        if (e->kind == KIND_WIDE && e->variant == 81 && e->hp == 0
            && !e->spr)
        {
            sound_play_event(SND_EV_BASEHIT);
            return;
        }
        if (e->hp)
            e->hp--;
        if (e->hp)
        {
            /* 7904: hit that does not kill plays ev20 (A=0x14).
             * 8b82 CP 0xCF: only type 79 then ev17 + 8bc1 scatter.
             * 8b8d: HP 0x32 / 0x14 -> 8c15/8c80 stage stamp. */
            sound_play_event(SND_EV_BASEHIT);
            if (e->kind == KIND_BOX && e->hp == 1)
            {
                /* 7860: last-HP SAT color. type4 0x89, type5 0x8A, else 0x87. */
                u8 col = 0x87;

                if (e->variant == 4)
                    col = 0x89;
                else if (e->variant == 5)
                    col = 0x8A;
                spr_set_sat_col(e, col);
            }
            if (e->kind == KIND_BASE && e->variant == 79)
            {
                sound_play_event(SND_EV_EHIT);
                scatter_expl(e->x, e->y);
                /* 8b97 JP 8c15; type79 dispatch idx6 is 8c80 (not live 8c15). */
                if (e->hp == 0x32 || e->hp == 0x14)
                    map_script_punch_79_hp(e->x, e->y, e->hp);
            }
            return;
        }
        sx = e->x;
        sy = e->y;
        drop = e->variant;
        kind = e->kind;
        {
            u16 dest = e->dest;
            if (kind == KIND_WIDE || kind == KIND_FIREBOX)
            {
                /* 880d: A=+0x18 type. Default (IX+0)=0x48, then dispatch.
                 * 81/84-88 become type 80; 8e14 does bfb3+ev18+849c next tick.
                 * 82/89 8874: 4a6a +0x18 + ev18, become type 83 (8e3a). */
                if (drop == 82)
                {
                    /* 8874: 4a6a +0x18, ev18, 88d8, type 83 in-place. */
                    award_subtype(drop);
                    sound_play_explode();
                    map_script_punch_88d8(sx, sy);
                    e->kind = KIND_FIREUP;
                    e->variant = (u8)(dest & 7);
                    e->hp = 1;
                    e->timer = 0;
                    e->script = 0;
                    e->ground = 0;
                    e->dest = 0;
                    e->vx = 0;
                    e->vy = 0;
                    /* Firebox was nametable-only; fire-up needs visible pat 9. */
                    spr_place(e, FRAME_CIRCLE);
                    return;
                }
                if (drop >= 87)
                {
                    /* 8892: husk; 87->88b1, 88->88cb, else R&7 then 8874. */
                    if (drop == 87)
                    {
                        become_husk(e, drop);
                        map_script_punch_88b1(sx, sy);
                        return;
                    }
                    if (drop == 88)
                    {
                        become_husk(e, drop);
                        map_script_punch_88cb(sx, sy);
                        return;
                    }
                    /* 88a9 -> 8874: 4a6a still reads +0x18 (type 89=8). */
                    award_subtype(drop);
                    sound_play_explode();
                    map_script_punch_88d8(sx, sy);
                    e->kind = KIND_FIREUP;
                    e->variant = (u8)(rnd() & 7);
                    e->hp = 1;
                    e->timer = 0;
                    e->script = 0;
                    e->ground = 0;
                    e->dest = 0;
                    e->vx = 0;
                    e->vy = 0;
                    /* Was nametable-only; fire-up needs visible pat 9. */
                    spr_place(e, FRAME_CIRCLE);
                    return;
                }
                if (drop >= 84 && drop <= 86)
                {
                    /* 8854: type 80 husk + 88ab tiles. */
                    become_husk(e, drop);
                    map_script_punch_88ab(sx, sy, drop);
                    return;
                }
                if (drop == 81)
                {
                    /* 8824: type 80 husk + 88c2, X-0x24 Y-0x10. */
                    become_husk(e, drop);
                    map_script_punch_88c2(sx, sy);
                    return;
                }
                /* 8833: 70/71. 8810 this slot := type 72; bfc8; 4a6a;
                 * child 0xD1 HP 0 SAT 0x24. Bytes do not JP 88ed --
                 * punching 3x2 to 0x28 painted blue/white on the yellow
                 * totem. Japan leaves the stream face; only the orb drops. */
                entity_inc_encounter_b();
                award_subtype(drop);
                e->kind = KIND_ORB;
                e->variant = drop;  /* +0x1f = +0x18 (70/71) */
                e->hp = 1;
                e->timer = 0;       /* Y frac (8.8) */
                e->clock = 0;       /* +0x1b phase byte */
                e->script = 4;      /* +0x1e yellow life */
                e->aux = 0;         /* anim tick */
                e->bind = 0xFFF8;   /* Yvel 8.8; 71 later -> 0xFFF0 */
                e->ground = 0;
                e->vx = 0;
                e->vy = 0;
                /* dest kept: +0x1c/1d warp ptr from idol table.
                 * Idol had no SAT; first 8a16 pair is SAT 0x1C / 0x8F.
                 * 16x16 vehicle; pixels are Japan pat 7, not FRAME_LEAD. */
                marker_kill(e);
                e->vram_fr = 0xFF;
                spr_place(e, FRAME_CIRCLE);
                e->sat = k_orb_sat[0];
                spr_set_sat_col(e, k_orb_yel_col[0]);
                {
                    Slot *c = free_enemy();
                    if (c)
                        spawn_d1_child(c, sx, sy);
                }
                return;
            }
            if (kind == KIND_BOX)
            {
                /* 7878: no 4a6a / no ev18. Type 5 scores via 849c. */
                box_kill_7878(e);
                return;
            }
            if (kind == KIND_DESCEND)
            {
                /* 836b: remapped to 0x23 then gate -> type62 / type83 / explode.
                 * Gate miss: type35 init does ALC+ev17+4a6a (no pre-SFX). */
                if (descender_on_death(e))
                    return;
                become_expl(e, 61);
                return;
            }
            if (kind == KIND_GROUND)
            {
                /* type 44 handler 0x82D0 is airborne (4898, not 8f25).
                 * Death -> type 35. Must not 88ed-stamp ground wreck tiles. */
                become_expl(e, slot_msx_type(e));
            }
            else if (kind == KIND_BASE)
            {
                /* 8b9a: type 79 (+18==0x4F) SET +05.1 and keep 0xCF; others 8baa. */
                if (drop == 79)
                {
                    e->aux = (u8)(e->aux | 0x02);
                    e->hp = 0;
                    return;
                }
                base_finish_death(e);
            }
            else
            {
                /* entity_post -> type 0x23: type35 first frame ALC+SFX+4a6a. */
                become_expl(e, slot_msx_type(e));
            }
        }
        return;
    }
}

static void collide_shots_enemies(void)
{
    u8 i;
    for (i = 0; i < SHOT_SLOTS; i++)
    {
        Slot *s = &s_shot[i];
        if (!s->alive)
            continue;
        collide_bolt_enemies(s, 0);
    }
    if (s_fire.alive)
    {
        u8 fn = player_fire_num();
        u8 persist = 0;

        if (fn == 2)
            persist = 1;
        else if (fn == 4)
            persist = 2;
        else if (fn == 1 || fn == 3 || fn == 5 || fn == 7)
            persist = 3;
        else if (fn == 6)
            persist = 4;
        collide_bolt_enemies(&s_fire, persist);
    }
}

static void collide_player(void)
{
    u8 j;
    s16 px;
    s16 py;

    /* 44ea: LD A,(E300) / CP 0x81 / JR NZ,453c. I-frames keep type 0x81
     * (7710 XOR +04 / DEC +1B only). Death is type 60, so 44B0/44A6 do
     * not run. Do not gate the whole loop on s_invuln — that blocked
     * 44B0 pickups and 453E enemy remap. player_hit() still no-ops on
     * s_invuln (type 60 86a4 cancel). */
    if (player_dead() || player_is_over())
        return;

    px = player_x();
    py = player_y();

    for (j = 0; j < ENEMY_SLOTS; j++)
    {
        Slot *e = &s_en[j];
        u8 et;
        u8 pf;
        u8 cls;
        if (!e->alive)
            continue;
        if (e->kind == KIND_BOX && !e->clock)
            continue;          /* 782c: no entity_post / SAT is countdown */
        if (e->kind == KIND_CIRCLE && !(e->aux & 0x40))
            continue;          /* 83ee: idle XOR only, no 44BA */
        if (e->kind == KIND_GROUND)
            continue;          /* ship AABB ignores ground (44CA) */
        /* 0x453E path: only types on a ship leg (44BA/44B0/44A6) count.
         * Shots-only structures (44CA) and no-post types are ignored. */
        et = slot_msx_type(e);
        pf = post_flags(et);
        if (!(pf & POST_SHIP))
            continue;
        {
            /* 4560 SAT vs SAT. Ship AABB still skips KIND_GROUND (44CA). */
            if (!hit_overlap_slot(px, py, SAT_PLAYER, e))
                continue;
        }
        if (pf & POST_PICK)
        {
            /* 44B0 + 453E remaps both; pickup handler restores player (0x81). */
            if (e->kind == KIND_CHIP)
            {
                /* 78bf ev17; 78cc SET 7 +05; 78d0 +1B=0x40; 78d4 bfc8;
                 * 78d7 INC E10B. Type 60 86a4 restores 0x81 while bit7 set. */
                player_add_shot_level();
                sound_play_event(SND_EV_PICKUP);
                player_grant_iframes();
                entity_inc_encounter_b();
                spr_kill(e);
                return;
            }
            if (e->kind == KIND_RISER)
            {
                /* 8752 ship-only 44b0; on clear: INC E10A + ev8 + status. */
                player_grant_life();
                spr_kill(e);
                return;
            }
            if (e->kind == KIND_FIREUP)
            {
                /* 8e89: player type 0x81, +0x1b=0, E148-=5, SET 7 +5,
                 * 48d0, bfc8, fire_select(+0x1c). +1B=0 is not 0x40;
                 * 8e9f latch is the 86a4 cancel (7710 DEC wraps 0→255). */
                player_e148_sub5();
                player_fireup_latch();
                player_fire_select(e->variant);
                entity_inc_encounter_b();
                spr_kill(e);
                return;
            }
            if (e->kind == KIND_ORB)
            {
                u16 dest = e->dest;
                u8 yellow = e->script;
                spr_kill(e);
                if (yellow)
                {
                    /* 8a26 explode_enemies + ev19. Types >=0x46 stay. */
                    entity_explode_airborne();
                    sound_play_event(SND_EV_PLASMA);
                }
                else
                    map_script_warp(dest);
                return;
            }
            /* Unknown pickup-class type: despawn only (CLS_CLEAR). */
            spr_kill(e);
            return;
        }
        /* Hostile ship overlap: 453E maps player->60 and enemy->class;
         * 7904 then DEC HP and restores enemy from +0x18 if HP remains. */
        cls = death_class(et);
        player_hit();
        if (e->hp > 1)
        {
            e->hp--;
            sound_play_event(SND_EV_BASEHIT);
            return;
        }
        if (e->kind == KIND_BOX)
        {
            /* 44BA -> 453E -> 7904 Z -> 7878 (same as shot kill). */
            box_kill_7878(e);
        }
        else if (cls == CLS_EXPL)
        {
            /* 453E -> 0x23; type35 first frame ALC+ev17+4a6a(+0x18). */
            become_expl(e, slot_msx_type(e));
        }
        else
            spr_kill(e);  /* CLS_CLEAR bullets (20/37/38/41/42/43) */
        return;
    }
}

/* TMS9918 approx sRGB. Fire 7 72de INC cycles SAT colour; MSX writes
 * one SAT byte. MD tile remap every frame starves NT DMA (blue tear).
 * Bind comet tiles to PAL2[13] once and cycle that CRAM index. */
#define FIRE7_CRAM_NIB  13
static const u16 k_tms_vdp[16] = {
    RGB24_TO_VDPCOLOR(0x000000), RGB24_TO_VDPCOLOR(0x000000),
    RGB24_TO_VDPCOLOR(0x21C842), RGB24_TO_VDPCOLOR(0x5EDC78),
    RGB24_TO_VDPCOLOR(0x5455ED), RGB24_TO_VDPCOLOR(0x7D76FC),
    RGB24_TO_VDPCOLOR(0xD4524D), RGB24_TO_VDPCOLOR(0x42EBF5),
    RGB24_TO_VDPCOLOR(0xFC5554), RGB24_TO_VDPCOLOR(0xFF7978),
    RGB24_TO_VDPCOLOR(0xD4C154), RGB24_TO_VDPCOLOR(0xE6CE80),
    RGB24_TO_VDPCOLOR(0x21B03B), RGB24_TO_VDPCOLOR(0xC95BBA),
    RGB24_TO_VDPCOLOR(0xCCCCCC), RGB24_TO_VDPCOLOR(0xFFFFFF)
};

static void fire7_cram_restore(void)
{
    if (!s_fire7_cram)
        return;
    PAL_setColor((u16)((PAL2 * 16) + FIRE7_CRAM_NIB), k_tms_vdp[FIRE7_CRAM_NIB]);
    s_fire7_cram = 0;
    s_fire7_col = 0;
}

/* Paint every nonzero comet nibble to PAL2[13]. Remap-from-15 misses a
 * packed index and leaves the shot on nibble 1 (TMS black). */
static void fire7_paint_cram_tiles(Slot *f)
{
    Sprite *sp = f->spr;
    TileSet *ts;
    u16 nbytes;
    u16 vaddr;
    const u8 *src;
    u8 *buf;
    u8 want = FIRE7_CRAM_NIB;

    if (!sp || !sp->frame)
        return;
    ts = sp->frame->tileset;
    if (!ts || !ts->numTile)
        return;
    nbytes = (u16)(ts->numTile * 32);
    vaddr = (u16)((sp->attribut & TILE_INDEX_MASK) * 32);
    src = (const u8 *)FAR_SAFE(ts->tiles, nbytes);
    buf = DMA_allocateAndQueueDma(DMA_VRAM, vaddr, (u16)(nbytes / 2), 2);
    if (!buf)
    {
        static u8 s_pad[128];

        if (nbytes > sizeof(s_pad))
            nbytes = sizeof(s_pad);
        orb_paint_body_nibbles(s_pad, src, nbytes, want);
        DMA_queueDma(DMA_VRAM, s_pad, vaddr, (u16)(nbytes / 2), 2);
    }
    else
        orb_paint_body_nibbles(buf, src, nbytes, want);
    f->vram_fr = f->frame;
    f->vram_nib = want;
}

static void fire7_bind_cram(Slot *f)
{
    /* 72bc LD 0x80, then 72de INC -> 0x81. Bind tiles to PAL2[13] and
     * KEEP sat_col there. Restoring 0x81 lets spr_upload_color remap
     * the comet back to nibble 1 (black-only; CRAM[13] never visible). */
    s_fire7_col = 0x81;
    f->sat_col = (u8)(0x80 | FIRE7_CRAM_NIB);
    fire7_paint_cram_tiles(f);
    PAL_setColor((u16)((PAL2 * 16) + FIRE7_CRAM_NIB),
                 k_tms_vdp[s_fire7_col & 0x0F]);
    s_fire7_cram = 1;
}

static void fire7_cycle_cram(Slot *f)
{
    /* Japan 72de: INC A; AND 0x8F. EC stays. Do not walk sat_col --
     * tiles stay on nibble 13 so this CRAM write is what the player sees. */
    (void)f;
    s_fire7_col = (u8)((s_fire7_col + 1) & 0x8F);
    PAL_setColor((u16)((PAL2 * 16) + FIRE7_CRAM_NIB),
                 k_tms_vdp[s_fire7_col & 0x0F]);
}

void entity_init(void)
{
    memset(s_shot, 0, sizeof(s_shot));
    memset(&s_fire, 0, sizeof(s_fire));
    memset(s_en, 0, sizeof(s_en));
    s_flash_left = 0;
    mode_backdrop_flash(0);

    orb_cache_reset();
    remap_cache_reset();
    s_rng = 0xA351;
    s_spawn_ctrl = 0x02;          /* stream active */
    s_spawn_base = 0;
    s_e135 = 0;
    s_e136 = 0;
    s_stream_slot = 0;
    s_e124 = 6;
    s_e125 = 0;
    s_fireup_seq = 0;
    s_fire7_life_ticked = 0;
    s_fire7_cram = 0;
    s_fire7_col = 0;
    memset(s_shot_init_ret, 0, sizeof(s_shot_init_ret));
    memset(s_riser_init_ret, 0, sizeof(s_riser_init_ret));
    memset(s_ebullet_init_ret, 0, sizeof(s_ebullet_init_ret));
    s_base_left = 0;
    s_e150 = 0;
    s_e130 = 0;
    s_e141 = 0;
    s_e142 = 0;
    s_desc_cycle = 0;
    s_pat_rr = 0;
    s_alc_shots = 0;
    s_alc_events = 0;
    s_fyoff = s_fxoff = s_fvy = s_fvx = s_faccel = s_fanchor = 0;
    s_fdir = s_fexpire = 0;
    entity_alc_reset();
    /* BE27 via alc_recompute already armed E137/E138 from BE76[0]=0x38. */

    /* Objs share PAL2 with the ship so index 15 stays TMS white.
     * PAL1 index 15 remains ROUND/HUD gold (set in game/title). */
    PAL_setPalette(PAL2, spr_objs.palette->data, CPU);
    /* PAL2[2] and PAL2[3] used to be overridden to half brightness so the
     * flyers would read against the map. That was compensation for a palette
     * bug, not fidelity: RGB24_TO_VDPCOLOR collapsed TMS 2 and TMS 12 onto one
     * Mega Drive colour, which flattened the whole 2/12 ground stipple into a
     * single bright green and left a light-green flyer invisible on it. With
     * the ground rendering its real texture the flyer reads at its own colour,
     * and darkening it is now the defect: 0x83 came out a muddy green that
     * turned the interlocked primary/complement pair into a smudge. Compared
     * against the same enemy in openMSX, undimmed matches and dimmed does not. */
}

void entity_update(void)
{
    flash_tick();
    spawn_tick();
    update_shots();
    update_fire();
    update_enemies();
    collide_shots_enemies();
    collide_player();
}

void entity_release(void)
{
    u8 i;

    s_flash_left = 0;
    mode_backdrop_flash(0);
    for (i = 0; i < SHOT_SLOTS; i++)
        spr_kill(&s_shot[i]);
    spr_kill(&s_fire);
    for (i = 0; i < ENEMY_SLOTS; i++)
        spr_kill(&s_en[i]);
}

void entity_on_spawn_ctrl(u8 ctrl)
{
    s_spawn_ctrl = ctrl;
    /* If a later round actually enables the stream, don't stall. */
    if ((ctrl & 0x02) && s_spawn_timer > s_spawn_reload)
        s_spawn_timer = s_spawn_reload;
}

void entity_on_spawn_pace(s8 nudge)
{
    s16 v;

    /* cmd 12: E132 += nn sat; if nn<0 also E12E += nn; SET 0,(E12D). */
    v = (s16)s_e132 + (s16)nudge;
    if (v < 0)
        v = 0;
    if (v > 255)
        v = 255;
    s_e132 = (u8)v;
    if (nudge < 0)
    {
        v = (s16)s_spawn_pos_hi + (s16)nudge;
        if (v < 0)
            v = 0;
        if (v > 255)
            v = 255;
        s_spawn_pos_hi = (u8)v;
    }
    /* SET 0,(E12D) -- BE27 on next ground_struct_spawn_ctrl. */
    s_spawn_ctrl = (u8)(s_spawn_ctrl | 0x01);
}

void entity_alc_reset(void)
{
    s_spawn_pos_hi = 0;
    s_spawn_pos_lo = 0;
    s_e131 = 0;
    s_e132 = 0;
    alc_recompute();
}

void entity_alc_complete(void)
{
    /* LAB_414d 0x4152: LD HL,E132 / ADD A,0x20 / JR NC / LD (HL),0xFF.
     * reset_entities 0x40D6 already zeroed E132, so live result is 0x20. */
    u16 v = (u16)s_e132 + 0x20;

    s_e132 = (v > 255) ? 0xFF : (u8)v;
}

void entity_alc_ease(void)
{
    /* 90a6: E12E -= E12E/4; E132 -= 8, sat 0.
     * Caller (90bf) then dec_encounter_a SETs bit0 for sticky BE27. */
    s_spawn_pos_hi = (u8)(s_spawn_pos_hi - (s_spawn_pos_hi >> 2));
    if (s_e132 >= 8)
        s_e132 = (u8)(s_e132 - 8);
    else
        s_e132 = 0;
}

void entity_dec_encounter_a(void)
{
    /* BFB3 / 90bf: DEC E12E if nonzero, then SET 0,(E12D).
     * Sticky -- BE27 runs in ground_struct_spawn_ctrl, not here. */
    if (s_spawn_pos_hi)
        s_spawn_pos_hi--;
    s_spawn_ctrl = (u8)(s_spawn_ctrl | 0x01);
}

static void entity_inc_encounter_a(void)
{
    /* BFAB: INC E12E sat 255 unless E150 bit1, then SET 0,(E12D).
     * Sticky -- BE27 runs in ground_struct_spawn_ctrl, not here. */
    if (!(s_e150 & 2))
    {
        s_spawn_pos_hi++;
        if (!s_spawn_pos_hi)
            s_spawn_pos_hi--;
    }
    s_spawn_ctrl = (u8)(s_spawn_ctrl | 0x01);
}

void entity_dec_encounter_b(void)
{
    /* BFBF / 9329: DEC E130 if nonzero. Display tail omitted. */
    if (s_e130)
        s_e130--;
}

void entity_timeout_alc(void)
{
    /* 932c-9334 while E150 bit1 still set: E12E += 0x10, then BFAB
     * (bit1 skips INC, still SETs sticky E12D bit0 for BE27). */
    s_spawn_pos_hi = (u8)(s_spawn_pos_hi + 0x10);
    entity_inc_encounter_a();
}



void entity_spawn_res3(void)
{
    /* 90c5: RES 3,E12D immediately before LD (E150),0. */
    s_spawn_ctrl = (u8)(s_spawn_ctrl & (u8)~0x08);
}

void entity_inc_encounter_b(void)
{
    /* SUB_bfc8 0xBFC8: if E150 bit1, skip INC (HUD-only). Else E130++ sat 255. */
    if (!(s_e150 & 2))
    {
        s_e130++;
        if (!s_e130)
            s_e130--;
    }
}

u8 entity_e12e(void)
{
    return s_spawn_pos_hi;
}

u8 entity_e132(void)
{
    return s_e132;
}

u8 entity_e130(void)
{
    return s_e130;
}

void entity_zero_e130(void)
{
    s_e130 = 0;
}

void entity_on_shot_fired(u8 cadence)
{
    u8 adv;
    u16 w;
    u16 lo;

    /* player_ship_update 0x7691: cadence>=0x12 -> 1, else table[E13F-2]. */
    if (cadence >= 0x12)
        adv = 1;
    else if (cadence < 2)
        adv = k_shot_rate[0];
    else
        adv = k_shot_rate[cadence - 2];

    /* 76a7: E12F += adv; C -> inc_encounter_a (SET bit0 sticky BE27).
     * Unlike table-spawn BF7A, shot carry does not silent-INC E12E alone. */
    lo = (u16)s_spawn_pos_lo + adv;
    s_spawn_pos_lo = (u8)lo;
    if (lo > 0xFF)
        entity_inc_encounter_a();

    w = (u16)s_e131 + adv;
    s_e131 = (u8)w;
    /* 0x76b5: carry -> SUB_bfc8 (E130++, gated by E150 bit1). */
    if (w > 255)
        entity_inc_encounter_b();

    /* 0x76bc: INC E141 sat 255 (shots since last type35 ALC dump). */
    s_e141++;
    if (!s_e141)
        s_e141--;

    if (s_alc_events < 255)
        s_alc_events++;
    /* 0x76e8 E140: INC (wrap) only on successful spawn -- entity_spawn_shot. */
}

bool entity_spawn_shot(s16 x, s16 y)
{
    u8 i;
    u8 live = 0;
    u8 lvl;
    u8 cap;
    u8 frame;
    u8 n;
    u8 free_i = 0;
    Slot *free = NULL;

    lvl = player_shot_level();
    if (lvl > 5)
        lvl = 5;
    cap = k_shot_power[lvl][1];
    n = k_shot_power[lvl][0];
    frame = k_shot_power[lvl][2];

    for (i = 0; i < SHOT_SLOTS; i++)
    {
        if (s_shot[i].alive)
            live++;
        else if (!free)
        {
            free = &s_shot[i];
            free_i = i;
        }
    }
    if (live >= cap || !free)
        return FALSE;

    /* Reuse the hardware sprite. spr_place sets the SAT name and
     * uploads before the sprite is visible (frame 0 is shot). */
    free->alive = 1;
    free->kind = KIND_SHOT;
    free->x = x;
    free->y = y;
    free->vx = 0;
    free->vy = 0;
    /* 7246 CPL E10E: Yvel high = ~n = -(n+1). 8.8 00|(~n)<<8, +0c=1. */
    free->dest = 0;
    free->bind = (u16)((u16)(u8)(~n) << 8);
    free->script = 0;
    free->timer = 0;
    /* shot_handler 0x7237: SAT colour 0x8F (EC) before the sprite is
     * placed, copied from ship SAT X at 0x76e1. */
    free->sat_col = 0x8F;
    spr_place(free, frame);
    if (!free->spr)
    {
        free->alive = 0;
        return FALSE;
    }
    /* 7221: type is now 0x82 (SET 7) but 4898 waits until next dispatch. */
    s_shot_init_ret[free_i] = 1;
    /* 0x76e8: INC (E140) after a free slot actually spawned. Z80 wrap
     * 255→0. E141 at 76bc is the saturating counter (INC / JR NZ / DEC);
     * E140 has no such restore. Type 61 gate 8374 is (E140&0x3F)==
     * (E103&0x3F); a stuck 0xFF makes &0x3F==0x3F, which packed BCD
     * E103 never matches, so the type-62 extra-life riser dies. */
    s_alc_shots++;
    return TRUE;
}

void entity_try_spawn_fire(s16 x, s16 y, u8 xvel_sel)
{
    u8 fn;
    u8 dir;
    u16 frame;

    fn = player_fire_num();
    if (s_fire.alive)
        return;

    if (xvel_sel > 8)
        xvel_sel = 8;

    spr_kill(&s_fire);
    s_fire.alive = 1;
    s_fire.kind = KIND_FIRE;
    s_fire.variant = fn;
    s_fire.hp = 1;
    s_fire.timer = 0;
    s_fire.script = 0;
    s_fire.x = x;
    s_fire.y = y;
    s_fexpire = 0;
    /* 0x72bc fire 0/1/2/7 start 0x80 (EC); 0x7335/0x73d2 fire 3/4/5/6
     * are 0x8F. Bit7 must be set before spr_place so the first frame shifts. */
    s_fire.sat_col = 0x8F;

    if (fn == 1)
    {
        /* Straight 0x72A8: fire_dec_ammo, +0x0C=1 Y-only, Yvel 0xFE00,
         * pat 2. 4cf7 skipped (C=0); 72ea -> 4898. */
        s_fire.vx = 0;
        s_fire.vy = 0;
        s_fire.dest = 0;
        s_fire.bind = 0xFE00;
        frame = FRAME_COMET;
        player_fire_dec_ammo();
    }
    else if (fn == 2)
    {
        /* Field Shutter 0x729D: +0x0C=0, pat 9, follows ship. */
        s_fire.vx = 0;
        s_fire.vy = 0;
        s_fire.y = (s16)(y - 8);
        frame = FRAME_CIRCLE;
    }
    else if (fn == 3)
    {
        /* Circular 0x7331: SAT 0x10 pat 4, +0x0C=0, off 0xC000/0xF600, dir 0xFF. */
        s_fyoff = (s16)0xC000;
        s_fxoff = (s16)0xF600;
        s_fdir = 0xFF;
        s_fire.vx = 0;
        s_fire.vy = 0;
        frame = FRAME_SNOW;
    }
    else if (fn == 4)
    {
        /* Vibrator 0x73CE/0x73F1: SAT 0x24, vy=-1, vx=-12, accel=+4, +0x1C=70. */
        s16 ax;
        s16 max_x;
        const ModeAssets *a = mode_assets();

        player_fire_dec_ammo();
        max_x = (s16)(a->playfield_w - (256 - 0xA0));
        if (max_x < 0xA0)
            max_x = 0xA0;
        ax = clamp16(x, 0x50, max_x);
        s_fanchor = ax;
        s_fire.x = (s16)(ax + 0x18);
        if (y < 0x50)
            s_fire.y = 0x50;
        s_fire.vx = 0;
        s_fire.vy = -1;
        s_fvx = (s16)0xF400;
        s_faccel = (s16)0x0400;
        s_fire.timer = 0x46;
        s_fexpire = 0x3C;           /* 7435 +1b; 74e2 DECs per hit */
        frame = FRAME_CIRCLE;
    }
    else if (fn == 5)
    {
        /* Rewinder 0x73C8: SAT 0x0C, vy=0xFE00, Y-only, then 0x7464. */
        player_fire_dec_ammo();
        s_fire.vx = 0;
        s_fire.vy = 0;
        s_fvy = (s16)0xFE00;
        frame = FRAME_FIRE;
    }
    else if (fn == 6)
    {
        /* Plasma 0x73CE: SAT 0x10, color 0x8F, Yvel 0xFE00, +0c=1,
         * fire_dec_ammo, JP 7494 -> 4898. 7511 is type19 expire. */
        s_fire.vx = 0;
        s_fire.vy = 0;
        s_fire.dest = 0;
        s_fire.bind = 0xFE00;
        frame = FRAME_SNOW;
        player_fire_dec_ammo();
    }
    else if (fn == 7)
    {
        /* High Speed 0x728F: CALL 730B first; underflow skips 72bc.
         * SAT 0x08 comet, fire0_dir_table, +17=0xC3.
         * 4cf7 at 72db (not 7306): bit6*3, bit7*4, count 3 -> *36
         * = 18 px/frame cardinal 8.8. Do not drop bit6 (that is 6 px).
         * 7253 BIT 7: this frame is init, not 7306. Flag skips update 730B. */
        if (player_fire_life_tick())
            return;
        s_fire7_life_ticked = 1;
        dir = k_fire7_dir[xvel_sel];
        apply_dir_4cf7(&s_fire, dir, 0xC3);
        frame = FRAME_COMET;
    }
    else
    {
        /* Fire 0 All-Range 0x72B3: xvel_table[E10C] (copied to IX+0x1A).
         * +17=0xC2. 4cf7: bit6*3, bit7*4, count 2, unit 128 -> 12 px
         * cardinal 8.8 (same cardinal as the old integer *6). */
        dir = k_xvel_dir[xvel_sel];
        apply_dir_4cf7(&s_fire, dir, 0xC2);
        frame = FRAME_FIRE;
    }

    if (fn == 0 || fn == 1 || fn == 2 || fn == 7)
        s_fire.sat_col = 0x81;      /* 0x72bc 0x80 then 0x72de INC; EC stays */
    spr_place(&s_fire, frame);
    if (!s_fire.spr)
    {
        s_fire.alive = 0;
        return;
    }
    /* 72de weapons share one PAL2[13] CRAM cycle. Bind the live frame
     * (FIRE / COMET / CIRCLE) once; later ticks only write CRAM. */
    if (fn == 0 || fn == 1 || fn == 2 || fn == 7)
        fire7_bind_cram(&s_fire);
    /* 7331/73ce SAT 0x10. FRAME_SNOW is pat 4; 4560 uses +03. */
    if (fn == 3 || fn == 6)
        s_fire.sat = 0x10;
    sound_play_event(SND_EV_FIRE);
}

void entity_kill_fire(void)
{
    fire7_cram_restore();
    spr_kill(&s_fire);
}

void entity_fire2_special(void)
{
    /* fire_select 0x7579: HL = 0x752F + E10B*3; E701>=5 -> +3; CALL 97bc.
     * 97bc: check_col_clear CF skip; NC type 0x45 + LDIR emit/count/interval. */
    u8 lvl;
    u8 idx;
    const u8 *r;
    const MapScript *ms;

    lvl = player_shot_level();
    if (lvl > 5)
        lvl = 5;
    idx = (u8)(lvl * 3);
    ms = map_script_state();
    if (ms && ms->round >= 5)
        idx = (u8)(idx + 3);
    if (idx > 18)
        idx = 18;
    r = &k_fire2_special[idx];
    if (!entity_check_col_clear())
        return;
    entity_place_ground(0x45, (s16)r[1], (s16)r[0], r[2]);
}

u8 entity_shot_count(void)
{
    u8 i, n = 0;
    for (i = 0; i < SHOT_SLOTS; i++)
        if (s_shot[i].alive)
            n++;
    return n;
}

u8 entity_enemy_count(void)
{
    u8 i, n = 0;
    for (i = 0; i < ENEMY_SLOTS; i++)
        if (s_en[i].alive)
            n++;
    return n;
}

/* check_col_clear 0x9B22.
 * MSX scans entity slots 5..25 (21 entries, stride -32 from 0xE620).
 * CF set = blocked (skip place); CF clear = ok (HL = destination slot).
 * Phase 1: any type==0 -> NC. Phase 2: type in {0x14,0x25,0x26} -> NC
 * (overwrite). Phase 3: type 0x27 or >=0x46 are blocking; any other -> NC;
 * if all blocking -> SCF.
 * MD: type39 is a second hardware sprite (primary_only + FRAME_*_C from
 * gfx_sprite_patterns). Count each marker as virtual 0x27 so dual-SAT
 * rows pressure the 21-entry window. Pairdesc 57/58 occupy without art. */
u8 entity_check_col_clear(void)
{
    u8 occ[ENEMY_SLOTS * 2];
    u8 n = 0;
    u8 i;
    u8 t;

    for (i = 0; i < ENEMY_SLOTS; i++)
    {
        Slot *e = &s_en[i];
        if (!e->alive)
            continue;
        t = e->variant ? e->variant : e->kind;
        if (n < (u8)sizeof(occ))
            occ[n++] = t;
        /* type39 col-marker sibling (71f6) occupies a real MSX slot. */
        {
            u8 m;

            for (m = 0; m < e->marker && n < (u8)sizeof(occ); m++)
                occ[n++] = 0x27;
        }
    }

    /* Phase 1: empty slot in the 21-wide window. */
    if (n < 0x15)
        return 1;

    /* Phase 2: overwriteable types 20 / 37 / 38. */
    for (i = 0; i < 0x15 && i < n; i++)
    {
        t = (u8)(occ[i] & 0x7F);
        if (t == 0x14 || t == 0x25 || t == 0x26)
            return 1;
    }

    /* Phase 3: non-blocking type can be overwritten; else SCF. */
    for (i = 0; i < 0x15 && i < n; i++)
    {
        t = (u8)(occ[i] & 0x7F);
        if (t == 0x27 || t >= 0x46)
            continue;
        return 1;
    }
    return 0;
}

u8 entity_place_ground(u8 type, s16 x, s16 y, u16 dest)
{
    Slot *e;
    const ModeAssets *a = mode_assets();

    /* cmd 1 97CA: type 69 with (+01 emit, +02 count, +03 interval), not XY. */
    if (type == 69 || type == 0x45)
    {
        e = free_enemy();
        if (!e)
            return 0;
        spawn_spawner_cmd1(e, (u8)y, (u8)x, (u8)dest);
        return 1;
    }

    if (x < -16)
        x = -16;
    if (x > (s16)(a->playfield_w - 8))
        x = (s16)(a->playfield_w - 8);

    /* 8f25 / 8a5a types keep unsigned SAT Y (0xE0-0xFF walk +8 until
     * wrap or E150.1). 88ed punch is (u8)SAT_Y-0x10; C>=0x18 skips.
     * Type 44 is 82d0 airborne (signed Y ok; death is type35, no 88ed).
     * Other ground uses signed so 0xF0 appears at the top. */
    if (!(type == 70 || type == 71 || type == 81 || type == 82
          || (type >= 73 && type <= 79)
          || (type >= 84 && type <= 89)))
    {
        if (y >= 192)
            y = (s16)(y - 256);
    }

    e = free_enemy();
    if (!e)
        return 0;
    if (type == 80)
        spawn_husk_at(e, x, y);
    else if (type == 70 || type == 71 || type == 81
        || type == 84 || type == 85 || type == 86
        || type == 87 || type == 88 || type == 89)
        spawn_wide_at(e, type, x, y, dest);
    else if (type == 82)
        spawn_wide_at(e, 82, x, y, dest);
    else if (type >= 73 && type <= 79)
        spawn_base_seg(e, type, x, y);
    else
        spawn_ground_fall(e, type, x, y, dest);
    return 1;
}

void entity_base_open(u8 n)
{
    u16 v = (u16)s_base_left + n;
    if (v > 255)
        v = 255;
    s_base_left = (u8)v;
    /* place_tile_group 0x966F: E150 := 1 when ctrl bit7. */
    if (n)
        s_e150 = 1;
}

void entity_base_arm(void)
{
    u8 i;
    u8 pat;

    /* LAB_8fca: E150 := 2. Per-segment SET 7 (+0x10 / 8948) is in base_step. */
    s_e150 = 2;
    /*
     * 8fde / base_attack_patterns 0x93AB: reset E717 to table head, then for
     * each E780 attack-list body (port: live KIND_BASE in slot order) write
     * the next pattern descriptor (+0x0F/+0x10), clear +0x0E fire accum,
     * stamp +0x1C = sequential index, wrap every 8 patterns. Hold frames
     * jump to 9028 and skip this - one-shot at approach->hold only.
     */
    pat = 0;
    for (i = 0; i < ENEMY_SLOTS; i++)
    {
        Slot *e = &s_en[i];

        if (!e->alive || e->kind != KIND_BASE)
            continue;
        /* dest: low3=pat, mid5=rec, hi8=fire_acc (+0x14). Fresh pattern. */
        e->dest = pat;
        e->timer = 0;                   /* +0x0E phase-rate accum */
        e->clock = pat;                 /* +0x1C attack-list index */
        /* Keep SET7 if somehow already armed; clear phase / dir bits. */
        e->script = (u8)(e->script & 0x80);
        pat++;
        if (pat >= 8)
            pat = 0;
    }
    s_pat_rr = pat;
}

void entity_base_or_flags(u8 bits)
{
    s_e150 = (u8)(s_e150 | bits);
}

void entity_base_set(u8 v)
{
    s_e150 = v;
}

u8 entity_base_flags(void)
{
    return s_e150;
}

static void flash_begin(void)
{
    /* 8A26: WRTVDP BC=0x0F07, wait_frames 5, convert, WRTVDP 0x0107. */
    s_flash_left = 5;
    mode_backdrop_flash(1);
}

static void flash_tick(void)
{
    if (!s_flash_left)
        return;
    s_flash_left--;
    if (!s_flash_left)
        mode_backdrop_flash(0);
}

void entity_explode_airborne(void)
{
    u8 i;

    /* explode_enemies 0x8A26: AND 0x7F, skip 0 / >=0x46 / ==0x28, else
     * write type 0x23 (bit7 clear) and +0x18 = that unmasked type.
     * Live type 35 (0xA3) is in range: init 8446 re-runs (ALC, ev17,
     * 4a6a of type 35, E124). Type 60 (0x3C) is too; type 40 is not.
     * become_expl script=0 is the bit7-clear. Live type 35 is converted. */
    flash_begin();
    for (i = 0; i < ENEMY_SLOTS; i++)
    {
        Slot *e = &s_en[i];
        u8 t;

        if (!e->alive)
            continue;
        t = (u8)(slot_msx_type(e) & 0x7F);
        if (!t)
            continue;
        if (t >= 0x46)
            continue;
        if (t == 0x28)
            continue;
        become_expl(e, t);
    }
}

void entity_clear_enemies(void)
{
    u8 i;
    for (i = 0; i < ENEMY_SLOTS; i++)
        spr_kill(&s_en[i]);
    s_base_left = 0;
    if (s_e150)
        map_script_resume_scroll();
    s_e150 = 0;
}

void entity_convert_clear_types(void)
{
    u8 i;

    /* 90dc: type&0x7F in {82,84,85,86} -> type 80, +0x18=0. Then 8e14. */
    for (i = 0; i < ENEMY_SLOTS; i++)
    {
        Slot *e = &s_en[i];
        u8 t;

        if (!e->alive)
            continue;
        t = (u8)(e->variant & 0x7F);
        if (t == 0x53)
            continue;
        if (t < 0x52)
            continue;
        if (t >= 0x57)
            continue;
        e->kind = KIND_HUSK;
        e->variant = 80;
        e->script = 0;
        e->hp = 0;
        e->timer = 0;
        e->vx = 0;
        e->vy = 0;
        e->ground = 1;
        e->dest = 0;
    }
}
