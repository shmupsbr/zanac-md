#!/usr/bin/env python3
"""Type 44 ground uses 4898 unsigned wrap Y>=0xD0 / X>=0xD1, not playfield cull.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type44_ground_structure 0x82d0:
    BIT 7, (IX+00)
    JR NZ, 0x82f9                ; armed
    CALL 0x71da                  ; spawn_col_marker
    LD (HL), 0x44
    CALL 0x71c5                  ; Y=0, random X
    LD A,R / AND 0x03 / INC A
    LD (IX+0x17), A              ; speed 1..4
    CALL 0x4c8b                  ; aim + set_velocity_from_dir
    LD (IX+0x0c), 0x03           ; X|Y 8.8
    +03=0x40 +04=0x83
    SET 7
    CALL 0x4898                  ; 0x82f9 entity_update
    CALL 0x71f6 / JP 0x44ba

  Y_motion_sub 0x48de:
    ADD HL,DE
    LD A,H / CP 0xD0 / RET C
    JP 0x48d0                    ; entity_clear

  X_motion_sub 0x48f8:
    ADD HL,DE
    LD A,H / CP 0xD1 / RET C
    JP 0x48d0

  Original playfield_w=256 playfield_h=192.
  Old KIND_GROUND used signed s32 then shared pass:
    max_y = playfield_h+8 = 200  -> Y>200 dies
    max_x = playfield_w-16 = 240 -> X>256 dies
  Y=201..207 and X=0xD1..0xFF stay live on MSX.

Usage (from zanac-md):
    python tools/test_type44_4898_wrap.py
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


def step_4898(x: int, xf: int, y: int, yf: int, vx: int, vy: int) -> tuple[int, int, bool]:
    """u8 8.8 ADD then unsigned Y>=0xD0 / X>=0xD1."""
    xpos = ((((x & 0xFF) << 8) | (xf & 0xFF)) + (vx & 0xFFFF)) & 0xFFFF
    ypos = ((((y & 0xFF) << 8) | (yf & 0xFF)) + (vy & 0xFFFF)) & 0xFFFF
    x = (xpos >> 8) & 0xFF
    y = (ypos >> 8) & 0xFF
    return x, y, y >= 0xD0 or x >= 0xD1


def old_playfield_cull(x: int, y: int, max_x: int = 240, max_y: int = 200) -> bool:
    """Old port: shared pass e->x > max_x+16 or e->y > playfield_h+8."""
    return x < -16 or x > max_x + 16 or y > max_y or y < -24


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        t44 = asm.split("handler_type44_ground_structure:", 1)
        if len(t44) < 2:
            fail("zanac.asm missing handler_type44_ground_structure")
            fails += 1
        else:
            body = t44[1].split("handler_type61_large_descender:", 1)[0]
            if not re.search(r"CALL\s+0x4898\s*;\s*0x82f9", body, re.I):
                fail("type44 armed must CALL 4898 at 82f9")
                fails += 1
            else:
                print("  ASM 82f9: CALL 4898")
            if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x03\s*;\s*0x82e9", body, re.I):
                fail("type44 init must set +0c=3 (X|Y)")
                fails += 1
            else:
                print("  ASM 82e9: +0c=3 X|Y")
            if not re.search(r"CALL\s+0x4c8b\s*;\s*0x82e6", body, re.I):
                fail("type44 init must CALL 4c8b (aim+set_vel)")
                fails += 1
            else:
                print("  ASM 82e6: CALL 4c8b aim+set_vel")
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
        _, _, culled = step_4898(0x78, 0, y, 0, 0, 0)
        if culled:
            fail(f"4898 must keep Y={y} (< 0xD0)")
            fails += 1
        if not old_playfield_cull(0x78, y):
            fail(f"old playfield cull must kill Y={y} (> 200)")
            fails += 1
    # X=0xD1..0xFF: playfield X>256 keeps; 4898 clears.
    for x in range(0xD1, 0x100):
        _, _, culled = step_4898(x, 0, 0x50, 0, 0, 0)
        if not culled:
            fail(f"4898 must clear X={x:#x} (>= 0xD1)")
            fails += 1
        if old_playfield_cull(x, 0x50):
            fail(f"old playfield cull must keep X={x:#x} (<= 256)")
            fails += 1
    # Rising wrap: Y=0 + Yvel 0xFF00 -> Y=0xFF, 4898 clears; signed lives.
    _, y, culled = step_4898(0x78, 0, 0, 0, 0, 0xFF00)
    if (y, culled) != (0xFF, True):
        fail(f"4898 rise wrap 0+FF00 -> Y={y:#x} cull={culled}, want 0xFF True")
        fails += 1
    if old_playfield_cull(0x78, -1):
        fail("old signed rise to Y=-1 must still be inside playfield cull")
        fails += 1
    print("  sim: Y=201..207 live on 4898; X>=0xD1 clears; rise wrap dies")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        ground = re.search(
            r"else if \(e->kind == KIND_GROUND\)\s*\{([^}]+)\}",
            upd,
        )
        if not ground:
            fail("KIND_GROUND block not found")
            fails += 1
        elif "step_88_4898" not in ground.group(1):
            fail("KIND_GROUND must use step_88_4898 (4898 X|Y wrap-cull)")
            fails += 1
        elif "s32 xpos" in ground.group(1) or "ypos +=" in ground.group(1):
            fail("KIND_GROUND must not keep signed s32 motion")
            fails += 1
        else:
            print("  update_enemies: KIND_GROUND step_88_4898")
        if "e->kind != KIND_GROUND" not in upd:
            fail("KIND_GROUND must be excluded from playfield max_y cull")
            fails += 1
        else:
            print("  update_enemies: KIND_GROUND excluded from max_y cull")
        if "type44 ground" not in upd:
            fail("cull comment must list type44 ground with 4898 wrap set")
            fails += 1
        else:
            print("  update_enemies: type44 in 4898 wrap set")

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

    spawn = fn_span(ent, "static void spawn_ground_fall(Slot *e, u8 type, s16 x, s16 y, u16 dest)")
    if not spawn:
        fail("spawn_ground_fall not found")
        fails += 1
    elif "apply_dir_88" not in spawn:
        fail("spawn_ground_fall must still aim+set_vel 8.8")
        fails += 1
    elif "e->hp = 3" not in spawn:
        fail("type 44 HP 3 was reverted")
        fails += 1
    elif "e->sat_col = 0x83" not in spawn:
        fail("type 44 SAT color 0x83 was reverted")
        fails += 1
    else:
        print("  spawn_ground_fall: aim 8.8 HP 3 SAT 0x83")

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

    flash = fn_span(ent, "static void flash_step(Slot *e)")
    if not flash or "step_88_y_4898" not in flash:
        fail("type 36 flash_step step_88_y_4898 was reverted")
        fails += 1
    else:
        print("  KEEP: type 36 flash_step step_88_y_4898")

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

    if "ebullet_apply_vis" not in ent:
        fail("type 21 8659 was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 8659 via ebullet_apply_vis")

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
        if 44 not in vals:
            fail("spawn_type_list must still include type 44")
            fails += 1
        else:
            print("  spawn_type_list still includes type 44")

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

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
