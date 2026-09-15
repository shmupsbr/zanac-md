#!/usr/bin/env python3
"""Type 67 med_circle armed path uses 4898 unsigned wrap Y>=0xD0 / X>=0xD1.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type67_med_circle 0x839f:
    BIT 7, (IX+00)
    JR NZ, 0x83d8                 ; armed
    prng Y=0x10+(L&7F) X=0x40+(H&7F)
    +04=0x86 +03=0x20 +0c=3 +19=5 +17=3
    +1b=0x78 +1c=0x1e
    SET 7
    ; fall into 83d8

  83d8 XOR +03 0x34 / XOR +04 0x0c
  83e8 DEC +1b
  83eb JP Z, 83f7                 ; first +1b Z: SET +05.0, reaim
  83ee BIT 0, (IX+05)
  83f2 JP Z, 48b8                 ; idle: SAT write only, no 4898
  83f5 JR 841d                    ; bit0 set: 44ba then 4898

  841d CALL 44ba
  8420 BIT 7, (IX+00)
  8424 JP NZ, 4898                ; +0c=3 Y_motion + X_motion

  Y_motion_sub 0x48de:
    ADD HL,DE
    LD A,H / CP 0xD0 / RET C
    JP 0x48d0                    ; entity_clear

  X_motion_sub 0x48f8:
    ADD HL,DE
    LD A,H / CP 0xD1 / RET C
    JP 0x48d0

  Original playfield_w=256 playfield_h=192.
  Old circle_step used signed s32 then shared pass:
    max_y = playfield_h+8 = 200  -> Y>200 dies
    max_x = playfield_w-16 = 240 -> X>256 dies
  Y=201..207 and X=0xD1..0xFF stay live on MSX.
  Rise-wrap (Y=2 + 0xFE00) is unsigned 0xFF >= 0xD0 clear,
  not signed Y=-2 then playfield y<-24.

Usage (from zanac-md):
    python tools/test_type67_4898_wrap.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
PLAYER = ROOT / "src" / "player.c"
PLAYER_H = ROOT / "inc" / "player.h"
SPAWN = ROOT / "src" / "data" / "spawn_table.c"
MAPC = ROOT / "src" / "map_script.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def fn_span(src: str, sig: str) -> str | None:
    m = re.search(rf"{re.escape(sig)}\s*\{{", src)
    if not m:
        return None
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
    return None


def parse_spawn_list(src: str) -> list[int] | None:
    m = re.search(
        r"const u8 spawn_type_list\[SPAWN_TYPE_LEN\] = \{([^}]+)\}", src
    )
    if not m:
        return None
    return [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", m.group(1))]


def step_xy_4898(x: int, y: int, xf: int, yf: int, vx: int, vy: int) -> tuple[int, int, bool]:
    """u8 8.8 ADD then unsigned Y>=0xD0 / X>=0xD1."""
    xpos = ((((x & 0xFF) << 8) | (xf & 0xFF)) + (vx & 0xFFFF)) & 0xFFFF
    ypos = ((((y & 0xFF) << 8) | (yf & 0xFF)) + (vy & 0xFFFF)) & 0xFFFF
    x = (xpos >> 8) & 0xFF
    y = (ypos >> 8) & 0xFF
    return x, y, y >= 0xD0 or x >= 0xD1


def old_signed_then_playfield(
    x: int, y: int, xf: int, yf: int, vx: int, vy: int, max_y: int = 200
) -> tuple[int, int, bool]:
    """Old port: signed s32 then Y>200 / X>256."""
    xpos = (x << 8) | (xf & 0xFF)
    ypos = (y << 8) | (yf & 0xFF)
    # signed 16-bit vel
    vx_s = vx if vx < 0x8000 else vx - 0x10000
    vy_s = vy if vy < 0x8000 else vy - 0x10000
    xpos += vx_s
    ypos += vy_s
    x = xpos >> 8
    y = ypos >> 8
    culled = x < -16 or x > 256 or y > max_y or y < -24
    return x, y, culled


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        t67 = asm.split("handler_type67_med_circle:", 1)
        if len(t67) < 2:
            fail("zanac.asm missing handler_type67_med_circle")
            fails += 1
        else:
            body = t67[1].split("handler_type35_projectile:", 1)[0]
            if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x03\s*;\s*0x83c0", body, re.I):
                fail("type67 init must set +0c=3 (X|Y)")
                fails += 1
            else:
                print("  ASM 83c0: +0c=3 X|Y")
            if not re.search(r"JP\s+Z,\s*0x48b8\s*;\s*0x83f2", body, re.I):
                fail("type67 idle must JP 48b8 at 83f2 (no 4898)")
                fails += 1
            else:
                print("  ASM 83f2: idle JP 48b8 (no 4898)")
            if not re.search(r"JP\s+NZ,\s*0x4898\s*;\s*0x8424", body, re.I):
                fail("type67 armed must JP NZ 4898 at 8424")
                fails += 1
            else:
                print("  ASM 8424: JP NZ 4898")
            if not re.search(r"CALL\s+0x44ba\s*;\s*0x841d", body, re.I):
                fail("type67 armed must CALL 44ba at 841d")
                fails += 1
            else:
                print("  ASM 841d: CALL 44ba")
            if not re.search(r"LD\s+\(IX\+0x1b\),\s*0x78\s*;\s*0x83cc", body, re.I):
                fail("type67 init must set +1b=0x78")
                fails += 1
            else:
                print("  ASM 83cc: +1b=0x78")
        if not re.search(r"CP\s+0xd0\s*;\s*0x48f2", asm, re.I):
            fail("Y_motion_sub 48f2 is not CP 0xD0")
            fails += 1
        else:
            print("  ASM 48f2: Y_motion_sub CP 0xD0")
        if not re.search(r"CP\s+0xd1\s*;\s*0x490c", asm, re.I):
            fail("X_motion_sub 490c is not CP 0xD1")
            fails += 1
        else:
            print("  ASM 490c: X_motion_sub CP 0xD1")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    # Y=201..207: playfield max_y=200 kills; 4898 does not.
    for y in range(201, 208):
        _, _, culled = step_xy_4898(0x80, y, 0, 0, 0, 0)
        if culled:
            fail(f"4898 must keep Y={y} (< 0xD0)")
            fails += 1
        _, _, old = old_signed_then_playfield(0x80, y, 0, 0, 0, 0)
        if not old:
            fail(f"old playfield cull must kill Y={y} (> 200)")
            fails += 1
    # X=0xD1..0xFF: 4898 clears; old playfield X>256 does not.
    for x in range(0xD1, 0x100):
        _, _, culled = step_xy_4898(x, 0x80, 0, 0, 0, 0)
        if not culled:
            fail(f"4898 must clear X={x:#x} (>= 0xD1)")
            fails += 1
        _, _, old = old_signed_then_playfield(x, 0x80, 0, 0, 0, 0)
        if old:
            fail(f"old playfield cull must keep X={x:#x} (<= 256)")
            fails += 1

    x, y, culled = step_xy_4898(0x80, 0xCF, 0, 0x80, 0, 0x0080)
    if (y, culled) != (0xD0, True):
        fail(f"4898 at Y=0xCF.80 + 0x0080 -> Y={y:#x} cull={culled}, want 0xD0 True")
        fails += 1
    else:
        print("  sim: Y=201..207 live on 4898; old max_y=200 kills; 0xD0 clears")

    x, y, culled = step_xy_4898(0x02, 0x02, 0, 0, 0, 0xFE00)
    if (y, culled) != (0x00, False):
        fail(f"4898 Y=2 + 0xFE00 first step -> Y={y:#x} cull={culled}, want 0 live")
        fails += 1
    x, y, culled = step_xy_4898(0x02, 0x00, 0, 0, 0, 0xFE00)
    if (y, culled) != (0xFE, True):
        fail(f"4898 rise-wrap Y=0 + 0xFE00 -> Y={y:#x} cull={culled}, want 0xFE True")
        fails += 1
    else:
        print("  sim: rise-wrap Y=0+FE00 -> 0xFE >= 0xD0 clear")

    ox, oy, old = old_signed_then_playfield(0x02, 0x00, 0, 0, 0, 0xFE00)
    if oy >= 0 or old:
        fail(f"old signed rise-wrap should go negative and stay live, got y={oy} cull={old}")
        fails += 1
    else:
        print("  sim: old signed rise-wrap Y=-2 lives (y>-24)")

    circ = fn_span(ent, "static void circle_step(Slot *e)")
    if not circ:
        fail("circle_step not found")
        fails += 1
    elif "step_88_4898" not in circ:
        fail("circle_step must use step_88_4898 (4898 X|Y CP 0xD0/0xD1)")
        fails += 1
    elif "playfield" in circ or "max_y" in circ:
        fail("circle_step must not invent a playfield cull")
        fails += 1
    elif "ypos +=" in circ or "xpos +=" in circ:
        fail("circle_step must not keep signed s32 (invented cull)")
        fails += 1
    else:
        print("  circle_step: step_88_4898 (unsigned Y>=0xD0 / X>=0xD1)")

    spawn = fn_span(ent, "static void spawn_med_circle(Slot *e)")
    if not spawn:
        fail("spawn_med_circle not found")
        fails += 1
    elif "e->clock = 0x78" not in spawn:
        fail("spawn_med_circle must keep +1b=0x78")
        fails += 1
    elif "e->aux = 0x1E" not in spawn:
        fail("spawn_med_circle must keep +1c=0x1e")
        fails += 1
    elif "e->hp = 5" not in spawn:
        fail("spawn_med_circle must keep HP 5")
        fails += 1
    elif "e->sat_col = 0x86" not in spawn:
        fail("spawn_med_circle must keep SAT 0x86")
        fails += 1
    else:
        print("  spawn_med_circle: +1b=0x78 +1c=0x1e HP 5 SAT 0x86")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        if "e->kind != KIND_CIRCLE" not in upd:
            fail("KIND_CIRCLE must be excluded from playfield max_y cull")
            fails += 1
        else:
            print("  update_enemies: KIND_CIRCLE excluded from max_y cull")
        if not re.search(
            r"else if \(e->kind == KIND_CIRCLE\)\s*\{\s*"
            r"(?:/\*[^*]*\*+(?:[^/*][^*]*\*+)*/\s*)*"
            r"circle_step\(e\);\s*"
            r"if \(!e->alive\)\s*continue;",
            upd,
        ):
            fail("KIND_CIRCLE must continue after 4898 clear")
            fails += 1
        else:
            print("  update_enemies: circle_step then continue if dead")
        if "type67 med_circle" not in upd:
            fail("cull comment must list type67 med_circle with 4898 wrap set")
            fails += 1
        else:
            print("  update_enemies: type67 in 4898 wrap set")

    xy4898 = fn_span(ent, "static int step_88_4898(Slot *e)")
    if (
        not xy4898
        or "(u8)e->y >= 0xD0" not in xy4898
        or "(u8)e->x >= 0xD1" not in xy4898
    ):
        fail("step_88_4898 must still unsigned-cull Y>=0xD0 / X>=0xD1")
        fails += 1
    else:
        print("  step_88_4898: unsigned Y>=0xD0 / X>=0xD1")

    # Type 44 / 36 KEEP
    if "e->kind != KIND_GROUND" not in (upd or ""):
        fail("KIND_GROUND playfield-cull exclude was reverted")
        fails += 1
    else:
        print("  KEEP: KIND_GROUND excluded from playfield cull")

    flash = fn_span(ent, "static void flash_step(Slot *e)")
    if not flash or "step_88_y_4898" not in flash:
        fail("type 36 flash_step step_88_y_4898 was reverted")
        fails += 1
    else:
        print("  KEEP: type 36 flash_step step_88_y_4898")

    collide = fn_span(ent, "static void collide_player(void)")
    if not collide:
        fail("collide_player not found")
        fails += 1
    elif re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide):
        fail("type 44 is 44BA (82ff); collide_player must not skip KIND_GROUND")
        fails += 1
    elif "if (player_dead() || player_is_over())" not in collide:
        fail("collide_player must skip only dead/over")
        fails += 1
    elif re.search(r"if\s*\(\s*player_invincible", collide):
        fail("collide_player must not skip on s_invuln")
        fails += 1
    else:
        print("  type 44 44BA: collide_player does not skip KIND_GROUND")

    if "s_ebullet_init_ret" not in ent:
        fail("s_ebullet_init_ret for 21/37/38/41/42/43 was reverted")
        fails += 1
    else:
        print("  KEEP: s_ebullet_init_ret still armed")

    if "s_shot_init_ret" not in ent:
        fail("s_shot_init_ret was reverted")
        fails += 1
    else:
        print("  KEEP: s_shot_init_ret")

    if "s_riser_init_ret" not in ent:
        fail("s_riser_init_ret was reverted")
        fails += 1
    else:
        print("  KEEP: s_riser_init_ret")

    if "s_fire7_life_ticked" not in ent:
        fail("fire 7 730B-once flag was reverted")
        fails += 1
    else:
        print("  KEEP: fire 7 730B once")

    stealth = fn_span(ent, "static void spawn_stealth(Slot *e, u8 type)")
    if not stealth or "e->clock = 48" not in stealth:
        fail("type 65 7ff0 +1D=0x30 seed was reverted")
        fails += 1
    else:
        print("  KEEP: spawn_stealth clock=48")

    step = fn_span(ent, "static void stealth_step(Slot *e)")
    if not step or "(e->variant == 65) ? 32 : 48" not in step:
        fail("stealth_step +0D reload 32/48 was reverted")
        fails += 1
    else:
        print("  KEEP: stealth_step reload 32/48")

    md = re.search(r"static const u8 k_stealth_dir\[4\] = \{([^}]+)\}", ent)
    if not md:
        fail("k_stealth_dir not found")
        fails += 1
    else:
        ds = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", md.group(1))]
        if ds != [2, 6, 4, 4]:
            fail(f"k_stealth_dir {ds} want [2, 6, 4, 4]")
            fails += 1
        else:
            print("  KEEP: stealth dir[0]=2")

    if stealth and "e->sat_col = 0x85" not in stealth:
        fail("type 65 SAT 0x85 was reverted")
        fails += 1
    elif stealth and "e->hp = (type == 65) ? 4 : 7" not in stealth:
        fail("type 65 HP 4 was reverted")
        fails += 1
    else:
        print("  KEEP: type 65 SAT 0x85 HP 4")

    rst = fn_span(ply, "static void fire_reset(void)")
    if not rst or "s_e14f = 0" not in rst or "fire_select(0)" not in rst:
        fail("fire_reset 7544 E14F wipe was reverted")
        fails += 1
    else:
        print("  KEEP: fire_reset 7544 zeroes E14F then fire_select(0)")

    sel = fn_span(ply, "static void fire_select(u8 n)")
    if not sel or "s_e14f" in sel:
        fail("7548 fire_select must not touch E14F")
        fails += 1
    else:
        print("  KEEP: player_fire_select is 7548")

    shot = fn_span(ent, "bool entity_spawn_shot(s16 x, s16 y)")
    if not shot or "s_alc_shots++" not in shot or re.search(
        r"s_alc_shots\s*<\s*255", shot
    ):
        fail("E140 76e8 wrap was reverted")
        fails += 1
    else:
        print("  KEEP: E140 76e8 still wraps")

    alc = fn_span(ent, "void entity_on_shot_fired(u8 cadence)")
    if not alc or "s_e141++" not in alc or "s_e141--" not in alc:
        fail("E141 76bc saturate was reverted")
        fails += 1
    else:
        print("  KEEP: E141 still saturates")

    gate = fn_span(ent, "static int descender_on_death(Slot *e)")
    if not gate or "(s_alc_shots & 0x3F) == (player_score_lo() & 0x3F)" not in gate:
        fail("type 61 gate 8374 was reverted")
        fails += 1
    else:
        print("  KEEP: type 61 gate 8374")

    box = fn_span(ent, "static void box_step(Slot *e)")
    if not box or "e->bind = 0x00C0" not in box:
        fail("box reveal 7841 00C0 was reverted")
        fails += 1
    else:
        print("  KEEP: box reveal bind=0x00C0")

    if "while (nt == 64 && guard < 8)" not in ent:
        fail("type 64 8279 re-roll was reverted")
        fails += 1
    else:
        print("  KEEP: type 64 8279 re-roll")

    if not re.search(
        r"e->variant == 21(?:\s*&&\s*options_bullet_high\(\))?\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        fail("type 21 8659 was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 8659 R-nibble|0x80")

    initf = fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not initf or "variant != 21" not in initf:
        fail("init_frag type 21 no +04 (863b) was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 init still no +04")

    jump = fn_span(mapc, "static void cmd_script_jump(u8 cmd, const u8 *ops)")
    if not jump:
        fail("cmd_script_jump not found")
        fails += 1
    elif "MAP_ENDING_STREAM" in jump:
        fail("cmd_script_jump must not special-case 0xA6F4")
        fails += 1
    elif "entity_alc_reset" in jump:
        fail("cmd 9 must still never alc_reset")
        fails += 1
    else:
        print("  KEEP: cmd 9 dest 0xA6F4 is a 941b jump; no alc_reset")

    latch = fn_span(ply, "void player_fireup_latch(void)")
    if not latch or "s_invuln = 0" not in latch or "s_if_latch = 1" not in latch:
        fail("player_fireup_latch must stay +1B=0 + SET 7")
        fails += 1
    else:
        print("  KEEP: player_fireup_latch +1B=0")

    complete = fn_span(ent, "void entity_alc_complete(void)")
    if not complete or "0x20" not in complete:
        fail("entity_alc_complete E132+=0x20 was reverted")
        fails += 1
    else:
        print("  KEEP: warp entity_alc_complete E132+=0x20")

    if "e->sat_col = 0x89" not in ent:
        fail("type 10 sat_col 0x89 was reverted")
        fails += 1
    else:
        print("  KEEP: type 10 sat_col 0x89")

    if "0xBFD6" in ent or "0xbfd6" in ent:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")
        if 67 not in vals:
            fail("spawn_type_list must still include type 67")
            fails += 1
        else:
            print("  spawn_type_list still includes type 67")

    if "player_fire_reset" not in hdr or "player_fire_select" not in hdr:
        fail("player.h must keep fire_reset / fire_select split")
        fails += 1
    else:
        print("  KEEP: player.h fire_reset + fire_select")

    husk = fn_span(ent, "static void husk_step(Slot *e)")
    if not husk or "tick_e124_84bc()" not in husk:
        fail("husk_step must still tick 84bc (8e2a JP 849c)")
        fails += 1
    else:
        print("  KEEP: type 80/35 tick_e124_84bc")

    zero = fn_span(ent, "void entity_zero_e130(void)")
    if not zero:
        fail("entity_zero_e130 missing")
        fails += 1
    else:
        print("  KEEP: respawn 7606 zeroes E130")

    if "enemy_takes_fire" not in ent:
        fail("E14E enemy_takes_fire was reverted")
        fails += 1
    else:
        print("  KEEP: E14E enemy_takes_fire")

    takes = fn_span(ent, "static int enemy_takes_shots(const Slot *e)")
    if not takes or "KIND_CIRCLE && !(e->aux & 0x40)" not in takes:
        fail("idle type 67 must still skip 44BA (83ee JP 48b8)")
        fails += 1
    else:
        print("  KEEP: idle type 67 no 44BA")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
