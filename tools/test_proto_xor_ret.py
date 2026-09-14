#!/usr/bin/env python3
"""Types 42/43 first-visit XOR+RET: no 4898 on the init handler visit.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  8dd5  LD A,0x2A / JR 8ddb     ; type 42, bit7 clear
  8dd9  LD A,0x2B               ; type 43
  8ddb  IY type=A, +1a=C, copy parent XY, RET

  handler_type42 0x85cc:
    CALL 0x84e3                ; type37 init body (SET 7 RET from CALL)
    LD (IX+00),0xA5            ; 0x85cf  now type 37 armed
    JP 0x85dd                  ; 0x85d3

  handler_type43 0x85d6:
    CALL 0x8507                ; type38 init body (SET 7 RET from CALL)
    LD (IX+00),0xA6            ; 0x85d9  now type 38 armed

  LAB_ram_85dd:
    LD A,R / XOR (IX+0x0a)     ; X vel low
    LD A,R / XOR (IX+0x08)     ; Y vel low
    RET                        ; 0x85ed  no 4898

  Next visit is type 0xA5 / 0xA6 (37/38 armed): CALL 0x4898 at 84fb.

  Old port: init_frag XOR'd vel lows (correct) then update_enemies always
  called step_88_4898 on that first visit. First SAT was one vel-step early.

  Type 20 init falls into 4898; type 45 CALL 850b then 8608/82a4 4898.
  Those stay same-frame. Shot 7221 / type 62 8727 / 21/37/38/41 skips stay.
  Fire still 4898 on the spawn frame. Port keeps variant 42/43 (no convert).

Usage (from zanac-md):
    python tools/test_proto_xor_ret.py
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
        if not re.search(r"CALL\s+0x84e3\s*;\s*0x85cc", asm, re.I):
            fail("zanac.asm 85cc is not CALL 84e3")
            fails += 1
        elif not re.search(r"LD\s+\(IX\+0x00\),\s*0xa5\s*;\s*0x85cf", asm, re.I):
            fail("zanac.asm 85cf is not type:=0xA5")
            fails += 1
        else:
            print("  ASM 85cc/85cf: type 42 CALL 84e3 then type 0xA5")

        if not re.search(r"CALL\s+0x8507\s*;\s*0x85d6", asm, re.I):
            fail("zanac.asm 85d6 is not CALL 8507")
            fails += 1
        elif not re.search(r"LD\s+\(IX\+0x00\),\s*0xa6\s*;\s*0x85d9", asm, re.I):
            fail("zanac.asm 85d9 is not type:=0xA6")
            fails += 1
        else:
            print("  ASM 85d6/85d9: type 43 CALL 8507 then type 0xA6")

        if not re.search(r"XOR\s+\(IX\+0x0a\)\s*;\s*0x85df", asm, re.I):
            fail("zanac.asm 85df is not XOR X vel low")
            fails += 1
        elif not re.search(r"XOR\s+\(IX\+0x08\)\s*;\s*0x85e7", asm, re.I):
            fail("zanac.asm 85e7 is not XOR Y vel low")
            fails += 1
        else:
            print("  ASM 85dd: XOR R into X/Y vel lows")

        if not re.search(r"RET\s*;\s*0x85ed", asm, re.I):
            fail("zanac.asm 85ed is not RET")
            fails += 1
        else:
            print("  ASM 85ed: XOR+RET (no 4898)")
        if re.search(r"CALL\s+0x4898\s*;\s*0x85ed", asm, re.I):
            fail("type 42/43 85ed must be RET, not CALL 4898")
            fails += 1

        if not re.search(r"CALL\s+0x4898\s*;\s*0x84fb", asm, re.I):
            fail("zanac.asm 84fb (37/38 armed, post-convert 42/43) is not CALL 4898")
            fails += 1
        else:
            print("  ASM 84fb: 37/38 armed 4898 is the next visit")

        if not re.search(r"RET\s*;\s*0x84fa", asm, re.I):
            fail("type 37 84fa RET was lost")
            fails += 1
        if not re.search(r"RET\s*;\s*0x8524", asm, re.I):
            fail("type 38 8524 RET was lost")
            fails += 1
        if not re.search(r"LD\s+A,\s*0x2a\s*;\s*0x8dd5", asm, re.I):
            fail("zanac.asm 8dd5 is not type 42")
            fails += 1
        elif not re.search(r"LD\s+A,\s*0x2b\s*;\s*0x8dd9", asm, re.I):
            fail("zanac.asm 8dd9 is not type 43")
            fails += 1
        else:
            print("  ASM 8dd5/8dd9: spawn writes 42/43 bit7-clear")
        if not re.search(r"RET\s*;\s*0x8df0", asm, re.I):
            fail("8ddb must RET after writing type+XY")
            fails += 1

        if not re.search(r"RET\s*;\s*0x7252", asm, re.I):
            fail("shot 7252 RET was lost")
            fails += 1
        if not re.search(r"RET\s*;\s*0x8727", asm, re.I):
            fail("type 62 8727 RET was lost")
            fails += 1
        if not re.search(r"SET\s+7,\s*\(IX\+0x00\)\s*;\s*0x725a", asm, re.I):
            fail("zanac.asm 725a is not SET 7 (fire init)")
            fails += 1
        else:
            print("  ASM: shot 7221 / type 62 RET stay; fire still falls through")
    else:
        print("  ASM: zanac.asm not in tree (bytes checked in port)")

    if "s_ebullet_init_ret" not in ent:
        fail("port must keep s_ebullet_init_ret")
        fails += 1
    else:
        print("  port: s_ebullet_init_ret")

    initf = fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not initf:
        fail("init_frag not found")
        fails += 1
    elif "s_ebullet_init_ret" not in initf:
        fail("init_frag must arm s_ebullet_init_ret")
        fails += 1
    elif "step_88_4898" in initf:
        fail("init_frag must not 4898 (that is the armed visit)")
        fails += 1
    else:
        if not re.search(r"variant == 42", initf) or not re.search(r"variant == 43", initf):
            fail("init_frag must arm 42/43")
            fails += 1
        else:
            print("  init_frag: arm skip for 42/43")
        if "apply_dir_88_xor" not in initf:
            fail("init_frag must still XOR vel lows for 42/43")
            fails += 1
        else:
            print("  init_frag: XOR still at spawn (85dd)")
        if re.search(
            r"if \(variant == 21 \|\| variant == 37 \|\| variant == 38 \|\| variant == 41"
            r"\s*\|\|\s*variant == 45",
            initf,
        ):
            fail("type 45 first visit falls through to 4898; do not skip")
            fails += 1
        if re.search(r"if \(variant == 20 \|\|", initf):
            fail("type 20 must not use the ebullet init-RET skip")
            fails += 1

    skip = re.search(r"s_ebullet_init_ret\[i\]\)\s*\{([^}]+)\}", ent)
    if not skip:
        fail("update_enemies ebullet spawn-skip block not found")
        fails += 1
    else:
        head = ent[max(0, skip.start() - 280) : skip.start()]
        if "variant == 42" not in head or "variant == 43" not in head:
            fail("update_enemies skip must include variants 42/43")
            fails += 1
        body = skip.group(1)
        if "step_88_4898" in body:
            fail("ebullet skip must not call 4898")
            fails += 1
        if "spr_set_sat_col" in body:
            fail("ebullet skip must not 8659")
            fails += 1
        if "k_unit_x" in body or "k_unit_y" in body:
            fail("ebullet skip must not run 857f 4cf7")
            fails += 1
        if "s_ebullet_init_ret[i] = 0" not in body:
            fail("ebullet skip must clear the flag")
            fails += 1
        if "continue" not in body:
            fail("ebullet skip must continue (init RET)")
            fails += 1
        print("  update_enemies: 42/43 init RET then 4898")

    armed = re.search(
        r"else if \(e->kind == KIND_EBULLET\s*"
        r"&& \(e->variant == 21 \|\| e->variant == 37 \|\| e->variant == 38\s*"
        r"\|\| e->variant == 42 \|\| e->variant == 43 \|\| e->variant == 45\)\)",
        ent,
    )
    if not armed:
        fail("armed 8.8 path must still include 42/43")
        fails += 1
    else:
        print("  KEEP: 42/43 armed path is still 8.8 4898")

    if "s_shot_init_ret" not in ent:
        fail("shot 7221 s_shot_init_ret was reverted")
        fails += 1
    else:
        print("  KEEP: shot 7221 s_shot_init_ret")
    if "s_riser_init_ret" not in ent:
        fail("type 62 s_riser_init_ret was reverted")
        fails += 1
    else:
        print("  KEEP: type 62 s_riser_init_ret")

    fire = fn_span(ent, "static void update_fire(void)")
    if not fire:
        fail("update_fire not found")
        fails += 1
    elif (
        "s_ebullet_init_ret" in fire
        or "s_riser_init_ret" in fire
        or "s_shot_init_ret" in fire
    ):
        fail("update_fire must not use shot/riser/ebullet init-RET skips")
        fails += 1
    else:
        print("  KEEP: fire still 4898 same frame")

    if not initf or "variant != 21" not in initf:
        fail("init_frag type 21 no +04 (863b) was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 init still no +04")

    if not re.search(
        r"e->variant == 21\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        fail("type 21 8659 was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 8659 R-nibble|0x80 on armed visit")

    collide = fn_span(ent, "static void collide_player(void)")
    if not collide:
        fail("collide_player not found")
        fails += 1
    elif re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide):
        fail("type 44 is 44BA; collide_player must not skip KIND_GROUND")
        fails += 1
    else:
        print("  type 44 44BA: collide_player does not skip KIND_GROUND")

    if "player_fire_mode" not in hdr:
        fail("player.h must keep player_fire_mode (E14E)")
        fails += 1
    takes = fn_span(ent, "static int enemy_takes_fire(const Slot *e)")
    if not takes or "player_fire_mode()" not in takes:
        fail("E14E enemy_takes_fire was reverted")
        fails += 1
    else:
        print("  KEEP: E14E enemy_takes_fire")

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

    become = fn_span(ent, "static void become_riser(Slot *e)")
    grant_life = fn_span(ply, "void player_grant_life(void)")
    if grant_life and ("fire_select" in grant_life or "player_fire_select" in grant_life):
        fail("player_grant_life must stay lives-only")
        fails += 1
    elif become and ("player_fire_select" in become or "fire_select" in become):
        fail("type 62 must stay lives-only")
        fails += 1
    else:
        print("  KEEP: type 62 lives-only")

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
