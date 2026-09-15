#!/usr/bin/env python3
"""Type 62 8709 init RET: no 8728 / 4898 on the first handler visit.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  type 61 death 0x8385:
    LD (IX+0x00), 0x3E     ; type 62, bit7 clear
    RET                    ; 0x8389  no type-62 handler this dispatch

  handler_type62 0x8709:
    BIT 7,(IX+0x00)
    JR NZ, 0x8728          ; armed: +0d tick / poke / 4898
    ... Yvel FF80 / SAT 0 / +0c=1 ...
    SET 7,(IX+0x00)        ; 0x8723
    RET                    ; 0x8727  no 8728, no 4898

  Next armed entry is 8728 INC +0d then 874a CALL 4898.

  Port: become_riser is the 8385 write (collide after updates).
  Old port ran riser_step (8728+4898) on the next entity_update —
  one frame early vs the init RET. s_riser_init_ret skips that visit.

  Shot 7221 stays the shot-only skip. Fire still 4898 same frame.

Usage (from zanac-md):
    python tools/test_type62_8727_ret.py
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
        if not re.search(r"LD\s+\(IX\+0x00\),\s*0x3e\s*;\s*0x8385", asm, re.I):
            fail("zanac.asm 8385 is not LD (IX+00),0x3E")
            fails += 1
        else:
            print("  ASM 8385: write type 0x3E, bit7 clear")
        if not re.search(r"RET\s*;\s*0x8389", asm, re.I):
            fail("zanac.asm 8389 is not RET")
            fails += 1
        else:
            print("  ASM 8389: RET (no type-62 handler this dispatch)")
        if not re.search(r"BIT\s+7,\s*\(IX\+0x00\)\s*;\s*0x8709", asm, re.I):
            fail("zanac.asm 8709 is not BIT 7,(IX+00)")
            fails += 1
        else:
            print("  ASM 8709: BIT 7,(IX+00)")
        if not re.search(r"JR\s+NZ,\s*0x8728\s*;\s*0x870d", asm, re.I):
            fail("zanac.asm 870d is not JR NZ,8728")
            fails += 1
        else:
            print("  ASM 870d: JR NZ 8728 (armed only)")
        if not re.search(r"SET\s+7,\s*\(IX\+0x00\)\s*;\s*0x8723", asm, re.I):
            fail("zanac.asm 8723 is not SET 7")
            fails += 1
        elif not re.search(r"RET\s*;\s*0x8727", asm, re.I):
            fail("zanac.asm 8727 is not RET")
            fails += 1
        else:
            print("  ASM 8723/8727: SET 7 RET (no 8728, no 4898)")
        if not re.search(r"CALL\s+0x4898\s*;\s*0x874a", asm, re.I):
            fail("zanac.asm 874a is not CALL 4898")
            fails += 1
        else:
            print("  ASM 874a: 4898 is the armed path")
        if re.search(r"CALL\s+0x4898\s*;\s*0x8727", asm, re.I):
            fail("type 62 8727 must be RET, not CALL 4898")
            fails += 1
        # Shot 7221 contrast stays shipped; fire still 4898 same frame.
        if not re.search(r"RET\s*;\s*0x7252", asm, re.I):
            fail("shot 7252 RET was lost")
            fails += 1
        else:
            print("  ASM 7252: shot 7221 RET stays")
        if not re.search(r"SET\s+7,\s*\(IX\+0x00\)\s*;\s*0x725a", asm, re.I):
            fail("zanac.asm 725a is not SET 7 (fire init)")
            fails += 1
        else:
            print("  ASM 725a: fire init still falls through")
    else:
        print("  ASM: zanac.asm not in tree (bytes checked in port)")

    if "s_riser_init_ret" not in ent:
        fail("port must keep s_riser_init_ret (8727 first-visit RET)")
        fails += 1
    else:
        print("  port: s_riser_init_ret")

    become = fn_span(ent, "static void become_riser(Slot *e)")
    if not become:
        fail("become_riser not found")
        fails += 1
    elif "s_riser_init_ret" not in become:
        fail("become_riser must arm s_riser_init_ret")
        fails += 1
    elif "step_88_y_4898" in become or "riser_step" in become:
        fail("become_riser must not 4898 / riser_step (that is 8728)")
        fails += 1
    else:
        print("  become_riser: arm skip, no 4898")

    if "KIND_RISER" not in ent or "s_riser_init_ret[i]" not in ent:
        fail("update_enemies must honor s_riser_init_ret")
        fails += 1
    else:
        skip = re.search(
            r"if\s*\(\s*s_riser_init_ret\[i\]\s*\)\s*\{([^}]+)\}", ent
        )
        if not skip:
            fail("KIND_RISER spawn-skip block not found")
            fails += 1
        else:
            body = skip.group(1)
            if "step_88_y_4898" in body or "riser_step" in body:
                fail("riser skip must not call 8728/4898")
                fails += 1
            if "s_riser_init_ret[i] = 0" not in body:
                fail("riser skip must clear the flag")
                fails += 1
            if "continue" not in body:
                fail("riser skip must continue (8727 RET)")
                fails += 1
            print("  update_enemies: init RET then 8728+4898")

    step = fn_span(ent, "static void riser_step(Slot *e)")
    if not step or "step_88_y_4898" not in step:
        fail("armed riser_step must still 4898")
        fails += 1
    elif "s_riser_init_ret" in step:
        fail("riser_step is the armed path; skip lives in update_enemies")
        fails += 1
    else:
        print("  riser_step: armed 8728+4898")

    # Shot 7221 must stay; fire must not use the riser skip.
    if "s_shot_init_ret" not in ent:
        fail("shot 7221 s_shot_init_ret was reverted")
        fails += 1
    else:
        print("  KEEP: shot 7221 s_shot_init_ret")

    fire = fn_span(ent, "static void update_fire(void)")
    if not fire:
        fail("update_fire not found")
        fails += 1
    elif "s_riser_init_ret" in fire or "s_shot_init_ret" in fire:
        fail("update_fire must not use shot/riser init-RET skips")
        fails += 1
    else:
        print("  KEEP: fire still 4898 same frame")

    # KEEP: type 62 lives-only (875a INC E10A, no fire_select).
    grant_life = fn_span(ply, "void player_grant_life(void)")
    if not become or "player_fire_select" in become or "fire_select" in become:
        fail("type 62 must stay lives-only")
        fails += 1
    elif grant_life and ("fire_select" in grant_life or "player_fire_select" in grant_life):
        fail("player_grant_life must stay lives-only")
        fails += 1
    else:
        print("  KEEP: type 62 lives-only")

    gate = fn_span(ent, "static int descender_on_death(Slot *e)")
    if not gate or "become_riser" not in gate:
        fail("type 61 gate 8374 become_riser was reverted")
        fails += 1
    elif "player_score_lo" not in gate:
        fail("type 61 gate 8374 must still compare E140 vs E103")
        fails += 1
    else:
        print("  KEEP: type 61 gate 8374")

    if "s_alc_shots++" not in ent:
        fail("E140 wrap INC was reverted")
        fails += 1
    else:
        print("  KEEP: E140 wrap")

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

    if "player_fire_life_tick" not in ent:
        fail("Fire 3 73c2 update-only tick was reverted")
        fails += 1
    else:
        print("  KEEP: Fire 3 update-only 73c2")

    stealth = fn_span(ent, "static void spawn_stealth(Slot *e, u8 type)")
    if not stealth or "e->clock = 48" not in stealth:
        fail("type 65 spawn clock=48 was reverted")
        fails += 1
    else:
        print("  KEEP: spawn_stealth clock=48")
    ststep = fn_span(ent, "static void stealth_step(Slot *e)")
    if not ststep or "(e->variant == 65) ? 32 : 48" not in ststep:
        fail("stealth_step +0D reload 32/48 was reverted")
        fails += 1
    else:
        print("  KEEP: stealth_step reload 32/48")

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
