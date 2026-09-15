#!/usr/bin/env python3
"""fire_reset 0x7544 zeroes E14F then fire_select(0).

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  fire_reset 0x7544:
    SUB A
    LD (0xE14F),A          ; chip-overflow progress wiped
    ; fall into fire_select 0x7548 with A=0

  7548 does not write E14F. Chip overflow 78ed/78f2 is
    (E14F)=0 / LD A,(E14B) / CALL 0x7548
  Type 83 collect is JP 0x7548 (not 7544).

  7544 callers:
    731e  fire_life_timer underflow (POP; JP 7544)
    74a1  off-screen + E14D==0 (fire 1/4/5/6)
    74cd  fire 2 expire E14D==0xFF
    750b  fire 4 +1b==0 and E14D==0
    75ff  player_ship_handler spawn
    86b1  type 60 death (port player_hit)

  Old port only zeroed E14F on player_hit. life_tick / offscreen /
  fire-2 expire / respawn called fire_select(0) and kept leftover
  E14F, so 1-4 maxed chips before expiry counted toward the next
  fire_select(E14B).

Usage (from zanac-md):
    python tools/test_fire_reset_7544.py
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


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(
            r"SUB\s+A\s*;\s*0x7544", asm, re.I
        ):
            fail("zanac.asm 7544 is not SUB A")
            fails += 1
        else:
            print("  ASM 7544: SUB A")
        if not re.search(
            r"LD\s+\(0xe14f\),\s*A\s*;\s*0x7545", asm, re.I
        ):
            fail("zanac.asm 7545 is not LD (E14F),A")
            fails += 1
        else:
            print("  ASM 7545: LD (E14F),A")
        if not re.search(
            r"fire_select:\s*\n\s*LD\s+E,\s*A\s*;\s*0x7548", asm
        ):
            fail("zanac.asm 7548 fire_select must follow 7544")
            fails += 1
        else:
            print("  ASM 7548: fire_select falls through from 7544")
        # 7548 body must not store E14F.
        sel_m = re.search(
            r"fire_select:.*?update_fire_display:", asm, re.S
        )
        if not sel_m:
            fail("zanac.asm fire_select span not found")
            fails += 1
        elif re.search(r"0xe14f", sel_m.group(0), re.I):
            fail("zanac.asm 7548 must not write E14F")
            fails += 1
        else:
            print("  ASM 7548: no E14F store")
        if not re.search(
            r"JP\s+0x7544\s*;\s*0x731e", asm, re.I
        ):
            fail("zanac.asm 731e is not JP 7544")
            fails += 1
        else:
            print("  ASM 731e: life_timer underflow JP 7544")
        if not re.search(
            r"JP\s+0x7544\s*;\s*0x74a1", asm, re.I
        ):
            fail("zanac.asm 74a1 is not JP 7544")
            fails += 1
        else:
            print("  ASM 74a1: offscreen E14D==0 JP 7544")
        if not re.search(
            r"JP\s+Z,\s*0x7544\s*;\s*0x74cd", asm, re.I
        ):
            fail("zanac.asm 74cd is not JP Z 7544")
            fails += 1
        else:
            print("  ASM 74cd: fire 2 ammo FF JP 7544")
        if not re.search(
            r"CALL\s+0x7544\s*;\s*0x75ff", asm, re.I
        ):
            fail("zanac.asm 75ff is not CALL 7544")
            fails += 1
        else:
            print("  ASM 75ff: ship spawn CALL 7544")
        if not re.search(
            r"CALL\s+0x7548\s*;\s*0x78f2", asm, re.I
        ):
            fail("zanac.asm 78f2 chip overflow must CALL 7548")
            fails += 1
        else:
            print("  ASM 78f2: chip overflow CALL 7548 (not 7544)")
        if not re.search(
            r"LD\s+\(HL\),\s*0x00\s*;\s*0x78ed", asm, re.I
        ):
            fail("zanac.asm 78ed must zero E14F before 7548")
            fails += 1
        else:
            print("  ASM 78ed: overflow zeros E14F then 7548")
    else:
        print("  ASM: zanac.asm not in tree (port-side checks only)")

    if "void player_fire_reset(void);" not in hdr:
        fail("player.h must declare player_fire_reset")
        fails += 1
    else:
        print("  player.h: player_fire_reset declared")

    reset = fn_span(ply, "static void fire_reset(void)")
    if not reset:
        fail("static fire_reset not found")
        fails += 1
    else:
        if "s_e14f = 0" not in reset:
            fail("fire_reset must assign s_e14f = 0")
            fails += 1
        else:
            print("  fire_reset: s_e14f = 0")
        if "fire_select(0)" not in reset:
            fail("fire_reset must fire_select(0)")
            fails += 1
        else:
            print("  fire_reset: fire_select(0)")

    sel = fn_span(ply, "static void fire_select(u8 n)")
    if not sel:
        fail("fire_select not found")
        fails += 1
    elif "s_e14f" in sel:
        fail("fire_select 7548 must not touch E14F")
        fails += 1
    else:
        print("  fire_select: no E14F (7548)")

    wrap = fn_span(ply, "void player_fire_reset(void)")
    if not wrap or "fire_reset()" not in wrap:
        fail("player_fire_reset must call fire_reset")
        fails += 1
    else:
        print("  player_fire_reset: fire_reset()")

    life = fn_span(ply, "u8 player_fire_life_tick(void)")
    if not life:
        fail("player_fire_life_tick not found")
        fails += 1
    elif "fire_reset()" not in life:
        fail("730B underflow must fire_reset (731e JP 7544)")
        fails += 1
    elif "fire_select(0)" in life:
        fail("life_tick must not fire_select(0) without wiping E14F")
        fails += 1
    else:
        print("  730B: underflow fire_reset")

    hit = fn_span(ply, "void player_hit(void)")
    if not hit or "fire_reset()" not in hit:
        fail("player_hit must fire_reset (type 60 / 7544)")
        fails += 1
    else:
        print("  player_hit: fire_reset")

    resp = fn_span(ply, "static void respawn(void)")
    if not resp or "fire_reset()" not in resp:
        fail("respawn must fire_reset (75ff CALL 7544)")
        fails += 1
    else:
        print("  respawn: fire_reset (75ff)")

    add = fn_span(ply, "void player_add_shot_level(void)")
    if not add:
        fail("player_add_shot_level not found")
        fails += 1
    elif "fire_reset" in add:
        fail("78f2 is CALL 7548, not fire_reset")
        fails += 1
    elif "fire_select(s_fire_num)" not in add:
        fail("chip overflow must fire_select(E14B)")
        fails += 1
    else:
        print("  78f2: overflow still fire_select(E14B)")

    off = fn_span(ent, "static void fire_offscreen_reset(u8 fn)")
    if not off:
        fail("fire_offscreen_reset not found")
        fails += 1
    elif "player_fire_reset()" not in off:
        fail("749c E14D==0 must player_fire_reset")
        fails += 1
    elif "player_fire_select(0)" in off:
        fail("offscreen must not fire_select(0) without wiping E14F")
        fails += 1
    else:
        print("  749c: offscreen player_fire_reset")

    bolt = fn_span(ent, "static void collide_bolt_enemies(Slot *bolt, u8 persist)")
    if not bolt:
        fail("collide_bolt_enemies not found")
        fails += 1
    elif "player_fire_reset()" not in bolt:
        fail("fire 2 74cd must player_fire_reset")
        fails += 1
    else:
        print("  74cd: fire 2 expire player_fire_reset")

    collide = fn_span(ent, "static void collide_player(void)")
    fireup = None
    if collide:
        m = re.search(
            r"if \(e->kind == KIND_FIREUP\)\s*\{", collide
        )
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
    if not fireup or "player_fire_select" not in fireup:
        fail("KIND_FIREUP must still player_fire_select (8eaf JP 7548)")
        fails += 1
    elif "player_fire_reset" in fireup:
        fail("type 83 8eaf is 7548, not fire_reset")
        fails += 1
    else:
        print("  type 83: still player_fire_select (7548)")

    # KEEP: shipped items and leave-alones this hunt must not revert.
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

    init = fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not init or "variant != 21" not in init:
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

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
