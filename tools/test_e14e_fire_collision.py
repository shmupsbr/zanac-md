#!/usr/bin/env python3
"""E14E gates fire vs 44CA structures and 44A6 bullets.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  fire_init_table 0x751F (E14D, E14E) per fire_num:
    0: 00 02   1: 64 03   2: 64 01   3: C8 01
    4: 1E 01   5: 64 03   6: 0F 03   7: FA 03

  44D4 check_hit_player: AND 0x01,E14E then E380 CP 0x83.
  44F9 check_hit_shots: three CP 0x82 slots, then BIT 1,E14E / E380 CP 0x83.
  44CA: CALL 45A0 / CALL 44F9 only (8806 wide/idol, 8b7a base).
  44A6: CALL 45A0 / CALL 44D4 only (84fe type37, 85c9 type38/41, 869b type20).
  44BA: 44D4 then 44F9 (airborne + type 44).

  So fire 2/3/4 (E14E=0x01) never hit 44CA structures.
  Fire 0 (E14E=0x02) never hits 44A6 bullets.
  Fire 1/5/6/7 (E14E=0x03) hit both.

  Old port wrote s_fire_mode from the table and never read it, so every
  live fire damaged idols/bases and no fire ate 20/37/38/41/42/43.

  Type 44 stays 44BA for fire and ship (82ff JP 44BA).
  7609 CALL BFD6 stays unported.

Usage (from zanac-md):
    python tools/test_e14e_fire_collision.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
PLAYER = ROOT / "src" / "player.c"
PLAYER_H = ROOT / "inc" / "player.h"
ENTITY_H = ROOT / "inc" / "entity.h"
SPAWN = ROOT / "src" / "data" / "spawn_table.c"
MAPC = ROOT / "src" / "map_script.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]

WANT_INIT = [
    (0x00, 0x02),
    (0x64, 0x03),
    (0x64, 0x01),
    (0xC8, 0x01),
    (0x1E, 0x01),
    (0x64, 0x03),
    (0x0F, 0x03),
    (0xFA, 0x03),
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


def parse_fire_init(src: str) -> list[tuple[int, int]] | None:
    m = re.search(
        r"static const u8 k_fire_init\[8\]\[2\] = \{(.+?)\n\};", src, re.S
    )
    if not m:
        return None
    nums = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+", m.group(1))]
    if len(nums) != 16:
        return None
    return [(nums[i], nums[i + 1]) for i in range(0, 16, 2)]


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    eh = ENTITY_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        m = re.search(
            r"fire_init_table:.*?DB\s+([0-9A-Fa-fxhH,\s]+);\s*0x751f",
            asm,
            re.I | re.S,
        )
        if not m:
            fail("zanac.asm fire_init_table 0x751F not found")
            fails += 1
        else:
            nums = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", m.group(1))]
            pairs = [(nums[i], nums[i + 1]) for i in range(0, min(16, len(nums)), 2)]
            if pairs != WANT_INIT:
                fail(f"ASM 751F {pairs} want {WANT_INIT}")
                fails += 1
            else:
                print("  ASM 751F: fire_init_table E14D/E14E")
        if not re.search(
            r"LD\s+A,\s*\(0xe14e\)\s*;\s*0x44d4", asm, re.I
        ) or not re.search(r"AND\s+0x01\s*;\s*0x44d7", asm, re.I):
            fail("zanac.asm 44D4 is not AND 1,E14E")
            fails += 1
        else:
            print("  ASM 44D4: AND 0x01 E14E (fire vs 44BA/44A6)")
        if not re.search(
            r"LD\s+A,\s*\(0xe14e\)\s*;\s*0x4526", asm, re.I
        ) or not re.search(r"BIT\s+1,\s*A\s*;\s*0x4529", asm, re.I):
            fail("zanac.asm 44F9 tail is not BIT 1,E14E")
            fails += 1
        else:
            print("  ASM 4526: BIT 1,E14E (fire vs 44F9/44CA)")
        if not re.search(r"CALL\s+0x44f9\s*;\s*0x44cd", asm, re.I):
            fail("zanac.asm 44CA is not CALL 44F9")
            fails += 1
        else:
            print("  ASM 44CA: shots+fire-bit1 only")
        if not re.search(r"CALL\s+0x44d4\s*;\s*0x44a9", asm, re.I):
            fail("zanac.asm 44A6 is not CALL 44D4")
            fails += 1
        else:
            print("  ASM 44A6: fire-bit0 + ship only")
        if not re.search(r"CALL\s+0x44ca\s*;\s*0x8806", asm, re.I):
            fail("zanac.asm 8806 is not CALL 44CA")
            fails += 1
        else:
            print("  ASM 8806: wide/idol/firebox 44CA")
        if not re.search(r"CALL\s+0x44ca\s*;\s*0x8b7a", asm, re.I):
            fail("zanac.asm 8b7a is not CALL 44CA")
            fails += 1
        else:
            print("  ASM 8b7a: base 44CA")
        if not re.search(r"JP\s+0x44a6\s*;\s*0x84fe", asm, re.I):
            fail("zanac.asm 84fe is not JP 44A6")
            fails += 1
        else:
            print("  ASM 84fe: type 37 44A6")
        if not re.search(r"JP\s+0x44a6\s*;\s*0x85c9", asm, re.I):
            fail("zanac.asm 85c9 is not JP 44A6")
            fails += 1
        else:
            print("  ASM 85c9: type 38/41 44A6")
        if not re.search(r"JP\s+0x44a6\s*;\s*0x869b", asm, re.I):
            fail("zanac.asm 869b is not JP 44A6")
            fails += 1
        else:
            print("  ASM 869b: type 20 44A6")
        if re.search(r"CALL\s+0x44d4\s*;\s*0x44cd", asm, re.I):
            fail("44CA must not CALL 44D4")
            fails += 1
    else:
        print("  ASM: zanac.asm not in tree (table/bytes checked in port)")

    init = parse_fire_init(ply)
    if init != WANT_INIT:
        fail(f"k_fire_init {init} want {WANT_INIT}")
        fails += 1
    else:
        print("  k_fire_init: matches 0x751F")

    if not re.search(r"u8\s+player_fire_mode\s*\(\s*void\s*\)\s*;", hdr):
        fail("player.h must declare player_fire_mode (E14E)")
        fails += 1
    else:
        print("  player.h: player_fire_mode")

    mode_fn = fn_span(ply, "u8 player_fire_mode(void)")
    if not mode_fn or "return s_fire_mode" not in mode_fn:
        fail("player_fire_mode must return s_fire_mode (E14E)")
        fails += 1
    else:
        print("  player_fire_mode: returns s_fire_mode")

    takes = fn_span(ent, "static int enemy_takes_fire(const Slot *e)")
    if not takes:
        fail("enemy_takes_fire not found")
        fails += 1
    else:
        if "player_fire_mode()" not in takes:
            fail("enemy_takes_fire must read E14E via player_fire_mode")
            fails += 1
        if "0x01" not in takes or "0x02" not in takes:
            fail("enemy_takes_fire must test E14E bit0 and bit1")
            fails += 1
        if "et == 20" not in takes or "et == 37" not in takes:
            fail("enemy_takes_fire must 44A6-gate types 20/37/38/41")
            fails += 1
        if "et == 70" not in takes or "et == 82" not in takes:
            fail("enemy_takes_fire must 44CA-gate types 70/71/73-79/81/82/84-89")
            fails += 1
        if "KIND_GROUND" in takes and "return 0" in takes[
            takes.find("KIND_GROUND") : takes.find("KIND_GROUND") + 80
        ]:
            fail("type 44 is 44BA for fire; do not 44CA-skip KIND_GROUND")
            fails += 1
        print("  enemy_takes_fire: E14E bit0 44A6 / bit1 44CA")

    bolt = fn_span(ent, "static void collide_bolt_enemies(Slot *bolt, u8 persist)")
    if not bolt:
        fail("collide_bolt_enemies not found")
        fails += 1
    elif "enemy_takes_fire" not in bolt or "s_fire" not in bolt:
        fail("collide_bolt_enemies must use enemy_takes_fire for s_fire")
        fails += 1
    elif "enemy_takes_shots" not in bolt:
        fail("shots must still use enemy_takes_shots (44F9 always)")
        fails += 1
    else:
        print("  collide_bolt_enemies: fire E14E / shots 44F9")

    collide = fn_span(ent, "static void collide_player(void)")
    if not collide:
        fail("collide_player not found")
        fails += 1
    elif re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide):
        fail("type 44 is 44BA; collide_player must not skip KIND_GROUND")
        fails += 1
    else:
        print("  type 44 44BA: collide_player does not skip KIND_GROUND")

    # KEEP: shipped items and leave-alones this hunt must not revert.
    resp = fn_span(ply, "static void respawn(void)")
    if not resp or "entity_zero_e130" not in resp:
        fail("respawn 7606 E130 zero was reverted")
        fails += 1
    else:
        print("  KEEP: respawn 7606 zeroes E130")
    if "void entity_zero_e130(void);" not in eh:
        fail("entity.h must keep entity_zero_e130")
        fails += 1

    if "tick_e124_84bc" not in ent:
        fail("type 80/35 husk E124 helper was reverted")
        fails += 1
    else:
        print("  KEEP: tick_e124_84bc")

    boom = fn_span(ent, "void entity_explode_airborne(void)")
    if not boom or "become_expl" not in boom:
        fail("8A26 explode was reverted")
        fails += 1
    else:
        print("  KEEP: explode_enemies 8A26")

    if "s_fire7_life_ticked" not in ent:
        fail("fire 7 730B-once flag was reverted")
        fails += 1
    else:
        print("  KEEP: fire 7 730B once")

    stealth = fn_span(ent, "static void spawn_stealth(Slot *e, u8 type)")
    if not stealth or "e->clock = 48" not in stealth:
        fail("type 65 spawn clock=48 was reverted")
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
        print("  KEEP: fire_reset 7544 zeroes E14F")

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

    grant = fn_span(ply, "void player_grant_iframes(void)")
    if not grant or "s_invuln = PLAYER_IFRAMES" not in grant:
        fail("chip/spawn +1B=0x40 was reverted")
        fails += 1
    else:
        print("  KEEP: chip/spawn SET latch + +1B=0x40")

    fireup = None
    if collide:
        m = re.search(r"if \(e->kind == KIND_FIREUP\)\s*\{", collide)
        if m:
            i = m.end() - 1
            depth = 0
            for j in range(i, len(collide)):
                if collide[j] == "{":
                    depth += 1
                elif collide[j] == "}":
                    depth -= 1
                    if depth == 0:
                        fireup = collide[i : j + 1]
                        break
    if not fireup or "player_fire_select" not in fireup or "player_fire_reset" in fireup:
        fail("KIND_FIREUP must still player_fire_select (8eaf JP 7548)")
        fails += 1
    else:
        print("  KEEP: type 83 still player_fire_select (7548)")

    riser = fn_span(ent, "static void become_riser(Slot *e)")
    grant_life = fn_span(ply, "void player_grant_life(void)")
    if not riser or "player_fire_select" in riser or "fire_select" in riser:
        fail("type 62 must stay lives-only")
        fails += 1
    elif grant_life and ("fire_select" in grant_life or "player_fire_select" in grant_life):
        fail("player_grant_life must stay lives-only")
        fails += 1
    else:
        print("  KEEP: type 62 lives-only")

    if not collide or "if (player_dead() || player_is_over())" not in collide:
        fail("collide_player must skip only dead/over")
        fails += 1
    elif re.search(r"if\s*\(\s*player_invincible", collide):
        fail("collide_player must not skip on s_invuln")
        fails += 1
    else:
        print("  KEEP: collide_player skips only dead/over")

    complete = fn_span(ent, "void entity_alc_complete(void)")
    if not complete or "0x20" not in complete:
        fail("entity_alc_complete E132+=0x20 was reverted")
        fails += 1
    else:
        print("  KEEP: warp entity_alc_complete E132+=0x20")
    alc_reset = fn_span(ent, "void entity_alc_reset(void)")
    if not alc_reset or "0x20" in alc_reset:
        fail("entity_alc_reset must not bake +0x20")
        fails += 1
    else:
        print("  KEEP: alc_reset no +0x20")

    if "e->sat_col = 0x89" not in ent:
        fail("type 10 sat_col 0x89 was reverted")
        fails += 1
    else:
        print("  KEEP: type 10 sat_col 0x89")

    if "0xBFD6" in ent or "0xbfd6" in ent or "0xBFD6" in ply or "0xbfd6" in ply:
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

    if "mode_letter_attr" in mapc and "fill" in mapc:
        # Never playfield-wide mode_letter_attr fill — only fail if a wide fill appears.
        if re.search(r"mode_letter_attr\s*\([^)]*32", mapc):
            fail("must not playfield-wide mode_letter_attr fill")
            fails += 1

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
