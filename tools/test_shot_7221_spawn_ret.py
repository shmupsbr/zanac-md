#!/usr/bin/env python3
"""Shot 7221 init RET: no 4898 on the spawn frame.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  shot_handler 0x7221:
    BIT 7,(IX+0x00)
    JP NZ, 0x4898          ; armed (type 0x82) only
    ... SAT / CPL E10E / +0c=1 ...
    SET 7,(IX+0x00)        ; 0x724e  type 2 -> 0x82
    RET                    ; 0x7252  no motion

  player_ship_update 0x76C3 writes (HL)=0x02 + ship Y/X. Does not SET 7.
  entity_dispatch walks E300 then E320: same pass inits the new shot
  and RETs. 44F9 CP 0x82 then collides at spawn SAT, not one vel-step up.

  Fire 7253 SET 7 then init dispatch; fire 0/1/7 fall into 72de+4898
  on that same frame. Only shots skip the first 4898.

  Old port: entity_spawn_shot in player_update, then update_shots
  always step_88_y_4898. Level 0 CPL 4 = -5 px the spawn frame early.

Usage (from zanac-md):
    python tools/test_shot_7221_spawn_ret.py
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
        if not re.search(r"BIT\s+7,\s*\(IX\+0x00\)\s*;\s*0x7221", asm, re.I):
            fail("zanac.asm 7221 is not BIT 7,(IX+00)")
            fails += 1
        else:
            print("  ASM 7221: BIT 7,(IX+00)")
        if not re.search(r"JP\s+NZ,\s*0x4898\s*;\s*0x7225", asm, re.I):
            fail("zanac.asm 7225 is not JP NZ,4898")
            fails += 1
        else:
            print("  ASM 7225: JP NZ 4898 (armed only)")
        if not re.search(r"SET\s+7,\s*\(IX\+0x00\)\s*;\s*0x724e", asm, re.I):
            fail("zanac.asm 724e is not SET 7")
            fails += 1
        elif not re.search(r"RET\s*;\s*0x7252", asm, re.I):
            fail("zanac.asm 7252 is not RET")
            fails += 1
        else:
            print("  ASM 724e/7252: SET 7 RET (no 4898)")
        if not re.search(r"LD\s+\(HL\),\s*0x02\s*;\s*0x76d9", asm, re.I):
            fail("zanac.asm 76d9 is not LD (HL),2")
            fails += 1
        else:
            print("  ASM 76d9: write type 2, bit7 clear")
        # Fire contrast: init falls into 72de / 4898. Do not treat 7221
        # as a fire skip.
        if not re.search(r"SET\s+7,\s*\(IX\+0x00\)\s*;\s*0x725a", asm, re.I):
            fail("zanac.asm 725a is not SET 7 (fire init)")
            fails += 1
        elif not re.search(r"JP\s+0x4898\s*;\s*0x72e7", asm, re.I):
            fail("zanac.asm 72de tail is not JP 4898")
            fails += 1
        else:
            print("  ASM 725a/72e7: fire init still 4898 same frame")
        if re.search(r"JP\s+0x4898\s*;\s*0x7252", asm, re.I):
            fail("shot 7252 must be RET, not JP 4898")
            fails += 1
    else:
        print("  ASM: zanac.asm not in tree (bytes checked in port)")

    if "s_shot_init_ret" not in ent:
        fail("port must keep s_shot_init_ret (7221 spawn-frame RET)")
        fails += 1
    else:
        print("  port: s_shot_init_ret")

    spawn = fn_span(ent, "bool entity_spawn_shot(s16 x, s16 y)")
    if not spawn:
        fail("entity_spawn_shot not found")
        fails += 1
    elif "s_shot_init_ret[free_i] = 1" not in spawn:
        fail("entity_spawn_shot must arm s_shot_init_ret")
        fails += 1
    elif "step_88_y_4898" in spawn:
        fail("entity_spawn_shot must not 4898 (that is 7225)")
        fails += 1
    else:
        print("  entity_spawn_shot: arm skip, no 4898")

    upd = fn_span(ent, "static void update_shots(void)")
    if not upd:
        fail("update_shots not found")
        fails += 1
    else:
        if "s_shot_init_ret[i]" not in upd:
            fail("update_shots must honor s_shot_init_ret")
            fails += 1
        skip = re.search(
            r"if\s*\(\s*s_shot_init_ret\[i\]\s*\)\s*\{([^}]+)\}", upd
        )
        if not skip:
            fail("update_shots spawn-skip block not found")
            fails += 1
        else:
            body = skip.group(1)
            if "step_88_y_4898" in body:
                fail("spawn-skip must not call 4898")
                fails += 1
            if "s_shot_init_ret[i] = 0" not in body:
                fail("spawn-skip must clear the flag")
                fails += 1
        if "step_88_y_4898" not in upd:
            fail("armed shots must still 4898")
            fails += 1
        else:
            print("  update_shots: init RET then 4898")

    # Fire 0/1/7 still move on the spawn frame (72de -> 4898).
    fire = fn_span(ent, "static void update_fire(void)")
    if not fire:
        fail("update_fire not found")
        fails += 1
    elif "s_shot_init_ret" in fire:
        fail("update_fire must not use the shot 7221 skip")
        fails += 1
    else:
        print("  update_fire: no 7221 skip")

    spawn_fire = fn_span(ent, "void entity_try_spawn_fire(s16 x, s16 y, u8 xvel_sel)")
    if not spawn_fire:
        fail("entity_try_spawn_fire not found")
        fails += 1
    elif "s_shot_init_ret" in spawn_fire:
        fail("fire spawn must not arm shot 7221 skip")
        fails += 1
    else:
        print("  entity_try_spawn_fire: fire still 72de/4898")

    # KEEP: E14E just shipped. Ship AABB still skips KIND_GROUND.
    if "player_fire_mode" not in hdr:
        fail("player.h must keep player_fire_mode (E14E)")
        fails += 1
    takes = fn_span(ent, "static int enemy_takes_fire(const Slot *e)")
    if not takes or "player_fire_mode()" not in takes:
        fail("E14E enemy_takes_fire was reverted")
        fails += 1
    else:
        print("  KEEP: E14E enemy_takes_fire")

    collide = fn_span(ent, "static void collide_player(void)")
    if not collide:
        fail("collide_player not found")
        fails += 1
    elif re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide):
        fail("type 44 is 44BA; collide_player must not skip KIND_GROUND")
        fails += 1
    else:
        print("  type 44 44BA: collide_player does not skip KIND_GROUND")

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

    if "mode_letter_attr" in mapc and re.search(r"mode_letter_attr\s*\([^)]*32", mapc):
        fail("must not playfield-wide mode_letter_attr fill")
        fails += 1

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
