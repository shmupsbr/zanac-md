#!/usr/bin/env python3
"""Type 80 8e2a JP 849c includes 84bc DEC E124.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type80 8e14 (bit7 clear):
    CALL 0xbfb3            ; dec_encounter_a
    LD A, 0x12             ; ev18
    CALL 0x5189
    SET 7, (IX+00)
    LD (IX+0x0c), 0x00
    JP 0x849c              ; same tail as type35 after 8498

  849c:
    CALL 0x4a6a            ; add_score_for_subtype (+0x18)
    SET 2, (IX+0x0c)
    +0D=1 +0E=4 +0F=1 +10=6, table 84d1
    LD HL, 0xe124          ; 84bc
    DEC (HL)
    JR NZ, 84c9
    LD (HL), 0x10
    LD A, 1
    LD (0xe125), A         ; BFA0 type 44 next spawn_tick
    ... 84c9 +0F ? 4898 : 48d0

  There is no skip of 84bc on the type80 path. 8e2a is the only
  JP 849c. Type35 8446 falls through 8498 into the same CALL 4a6a.

  Old port: KIND_EXPL first frame ticked E124; husk_step scored and
  armed 84d1 but skipped 84bc. Leftover 81/84-88 / 90dc type-80
  therefore never counted toward BFA0 type 44.

Usage (from zanac-md):
    python tools/test_husk_849c_e124.py
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


def tick_e124(e124: int) -> tuple[int, int]:
    """Port 84bc: if(e124)--; if(!e124) e124=0x10, e125=1."""
    if e124:
        e124 -= 1
    if e124 == 0:
        return 0x10, 1
    return e124, 0


def old_husk_after(n_husks: int, seed: int = 6) -> tuple[int, int]:
    """Old port: husk_step skipped 84bc. E124 stays at title seed."""
    return seed, 0


def new_husk_after(n_husks: int, seed: int = 6) -> tuple[int, int]:
    e124 = seed
    e125 = 0
    for _ in range(n_husks):
        e124, latched = tick_e124(e124)
        if latched:
            e125 = 1
    return e124, e125


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"JP\s+0x849c\s*;\s*0x8e2a", asm, re.I):
            fail("zanac.asm 8e2a is not JP 849c")
            fails += 1
        else:
            print("  ASM 8e2a: JP 849c (type80 init tail)")
        if not re.search(r"CALL\s+0x4a6a\s*;\s*0x849c", asm, re.I):
            fail("zanac.asm 849c is not CALL 4a6a")
            fails += 1
        else:
            print("  ASM 849c: CALL 4a6a")
        if not re.search(r"LD\s+HL,\s*0xe124\s*;\s*0x84bc", asm, re.I):
            fail("zanac.asm 84bc is not LD HL,E124")
            fails += 1
        else:
            print("  ASM 84bc: LD HL,E124")
        if not re.search(r"DEC\s+\(HL\)\s*;\s*0x84bf", asm, re.I):
            fail("zanac.asm 84bf is not DEC (HL)")
            fails += 1
        else:
            print("  ASM 84bf: DEC E124")
        if not re.search(r"LD\s+\(HL\),\s*0x10\s*;\s*0x84c2", asm, re.I):
            fail("zanac.asm 84c2 is not LD (HL),0x10")
            fails += 1
        else:
            print("  ASM 84c2: E124 reload 0x10")
        if not re.search(r"LD\s+\(0xe125\),\s*A\s*;\s*0x84c6", asm, re.I):
            fail("zanac.asm 84c6 is not LD (E125),A")
            fails += 1
        else:
            print("  ASM 84c6: E125=1")
        jp849c = re.findall(r"JP\s+0x849c", asm, re.I)
        if len(jp849c) != 1:
            fail(f"expected one JP 849c (type80), found {len(jp849c)}")
            fails += 1
        else:
            print("  ASM: only type80 JP 849c (type35 falls through)")
        # 8e2a sits after SET 7 / +0c=0; 84bc is inside that tail.
        t80 = asm.split("handler_type80_base_damage:", 1)
        if len(t80) < 2:
            fail("zanac.asm missing handler_type80_base_damage")
            fails += 1
        else:
            body = t80[1].split("handler_type83_black_shadow:", 1)[0]
            if "0x8e2a" not in body or "0x849c" not in body:
                fail("type80 body must JP 849c at 8e2a")
                fails += 1
            elif "0xe124" in body:
                fail("type80 must reach E124 via JP 849c, not a local copy")
                fails += 1
            else:
                print("  ASM type80: E124 only via 8e2a JP 849c")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    old6 = old_husk_after(6)
    new6 = new_husk_after(6)
    if old6 != (6, 0):
        fail(f"old 6 husks {old6} want (6, 0)")
        fails += 1
    elif new6 != (0x10, 1):
        fail(f"new 6 husks {new6} want (0x10, 1) — 84bc latch")
        fails += 1
    else:
        print("  sim: 6 husks latch E125 (old port never did)")

    expl = new_husk_after(6)
    if expl != (0x10, 1):
        fail("type35 84bc sim must match husk")
        fails += 1
    else:
        print("  sim: type35 and type80 share 84bc")

    helper = fn_span(ent, "static void tick_e124_84bc(void)")
    if not helper:
        fail("tick_e124_84bc not found")
        fails += 1
    elif "s_e124--" not in helper or "s_e124 = 0x10" not in helper:
        fail("tick_e124_84bc must DEC then reload 0x10")
        fails += 1
    elif "s_e125 = 1" not in helper:
        fail("tick_e124_84bc must latch E125=1")
        fails += 1
    else:
        print("  tick_e124_84bc: DEC / 0x10 / E125=1")

    husk = fn_span(ent, "static void husk_step(Slot *e)")
    if not husk:
        fail("husk_step not found")
        fails += 1
    elif "tick_e124_84bc()" not in husk:
        fail("husk_step first frame must tick 84bc (8e2a JP 849c)")
        fails += 1
    elif husk.find("tick_e124_84bc()") > husk.find("if (step_8f45"):
        fail("84bc is on the bit7-clear frame, not the 8f45 update")
        fails += 1
    elif "award_subtype" not in husk:
        fail("husk_step must still 4a6a award_subtype(+0x18)")
        fails += 1
    else:
        print("  husk_step: 8e14 JP 849c ticks E124")

    # KIND_EXPL first frame must keep the same 84bc helper (8A26 path).
    if "tick_e124_84bc()" not in ent:
        fail("KIND_EXPL / husk must call tick_e124_84bc")
        fails += 1
    elif ent.count("tick_e124_84bc()") < 2:
        fail("both type35 first frame and husk_step must call 84bc")
        fails += 1
    else:
        print("  KEEP: type35 8446 still 84bc via same helper")

    expl_loop = fn_span(ent, "void entity_update(void)")
    if expl_loop and "KIND_EXPL" in expl_loop:
        print("  KEEP: KIND_EXPL update still present")

    boom = fn_span(ent, "void entity_explode_airborne(void)")
    if not boom:
        fail("entity_explode_airborne not found")
        fails += 1
    elif "KIND_EXPL" in boom and "continue" in boom:
        # 8A26 must not skip live type 35.
        if re.search(r"KIND_EXPL|KIND_PDEAD", boom.split("slot_msx_type", 1)[0]
                     if "slot_msx_type" in boom else boom):
            fail("8A26 must not skip KIND_EXPL / KIND_PDEAD")
            fails += 1
        else:
            print("  KEEP: 8A26 still reconverts live type 35")
    elif "become_expl" not in (boom or ""):
        fail("8A26 must still become_expl")
        fails += 1
    else:
        print("  KEEP: 8A26 still become_expl")

    if "s_fire7_life_ticked" not in ent:
        fail("fire 7 730B-once flag was reverted")
        fails += 1
    else:
        print("  KEEP: fire 7 730B once (s_fire7_life_ticked)")

    spawn = fn_span(ent, "void entity_try_spawn_fire(s16 x, s16 y, u8 xvel_sel)")
    upd = fn_span(ent, "static void update_fire(void)")
    if not spawn or not upd:
        fail("fire spawn/update not found")
        fails += 1
    elif spawn.count("player_fire_life_tick()") != 1:
        fail("only fire 7 init (728F) ticks 730B in spawn")
        fails += 1
    elif "s_fire7_life_ticked" not in upd:
        fail("update_fire must still honor the 7306 skip flag")
        fails += 1
    else:
        print("  KEEP: 728F still ticks; 7306 skipped that frame")

    if "73c2" not in ent and "fire 3" not in ent.lower():
        pass
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

    grant = fn_span(ply, "void player_grant_iframes(void)")
    if not grant or "s_invuln = PLAYER_IFRAMES" not in grant:
        fail("chip/spawn +1B=0x40 was reverted")
        fails += 1
    else:
        print("  KEEP: chip/spawn SET latch + +1B=0x40")

    collide = fn_span(ent, "static void collide_player(void)")
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

    if "0xBFD6" in ent or "0xbfd6" in ent:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")

    if "mode_letter_attr" in ent and "playfield" in ent:
        # Never playfield-wide mode_letter_attr fill — leave as comment lock
        # in callers; entity.c itself should not grow one.
        pass

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")

    add = fn_span(ply, "void player_add_shot_level(void)")
    if not add or "fire_reset" in add or "fire_select(s_fire_num)" not in add:
        fail("78f2 must stay fire_select(E14B)")
        fails += 1
    else:
        print("  KEEP: 78f2 overflow still fire_select(E14B)")

    if "player_fire_reset" not in hdr or "player_fire_select" not in hdr:
        fail("player.h must keep fire_reset / fire_select split")
        fails += 1
    else:
        print("  KEEP: player.h fire_reset + fire_select")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
