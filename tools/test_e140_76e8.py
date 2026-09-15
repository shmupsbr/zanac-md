#!/usr/bin/env python3
"""E140 0x76e8 INC wraps; it does not saturate like E141.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  76e5  LD HL, 0xE140
  76e8  INC (HL)              ; wrap 255→0; no JR NZ / DEC restore

  Contrast E141 at 76bc (saturating):
  76bc  LD HL, 0xE141
  76bf  INC (HL)
  76c0  JR NZ, 76c3
  76c2  DEC (HL)              ; stay 255

  Type 61 death gate 0x8374:
  8374  LD A,(E140) / AND 0x3F
  837A  LD A,(E103) / AND 0x3F
  837F  CP B
  8380  JR NZ, 838A           ; else become type 62
  838A  E148>=5 → type 83

  Packed BCD E103 is 00–99. AND 0x3F never yields 0x3F.
  A stuck E140=0xFF makes the extra-life riser unreachable.

  Old port: if (s_alc_shots < 255) s_alc_shots++. After 255
  successful shots the gate died for the rest of the credit.

Usage (from zanac-md):
    python tools/test_e140_76e8.py
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


def pack_bcd(n: int) -> int:
    return ((n // 10) << 4) | (n % 10)


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"LD\s+HL,\s*0xe140\s*;\s*0x76e5", asm, re.I):
            fail("zanac.asm 76e5 is not LD HL, E140")
            fails += 1
        else:
            print("  ASM 76e5: LD HL, E140")
        if not re.search(r"INC\s+\(HL\)\s*;\s*0x76e8", asm, re.I):
            fail("zanac.asm 76e8 is not INC (HL)")
            fails += 1
        else:
            print("  ASM 76e8: INC (HL)")
        # Next opcode after 76e8 must not be the E141 saturate restore.
        if re.search(r"INC\s+\(HL\)\s*;\s*0x76e8\s*\n\s*JR\s+NZ", asm, re.I):
            fail("E140 76e8 must not be followed by JR NZ saturate")
            fails += 1
        else:
            print("  ASM 76e8: no JR NZ saturate (unlike E141)")
        if not re.search(r"INC\s+\(HL\)\s*;\s*0x76bf", asm, re.I):
            fail("zanac.asm 76bf E141 INC (HL) missing")
            fails += 1
        elif not re.search(r"DEC\s+\(HL\)\s*;\s*0x76c2", asm, re.I):
            fail("zanac.asm 76c2 E141 DEC (HL) saturate missing")
            fails += 1
        else:
            print("  ASM 76bc: E141 INC / JR NZ / DEC saturates")
        if not re.search(r"LD\s+A,\s*\(0xe140\)\s*;\s*0x8374", asm, re.I):
            fail("zanac.asm 8374 is not LD A,(E140)")
            fails += 1
        else:
            print("  ASM 8374: type 61 gate reads E140")
        if not re.search(r"AND\s+0x3f\s*;\s*0x8377", asm, re.I):
            fail("zanac.asm 8377 is not AND 0x3F")
            fails += 1
        else:
            print("  ASM 8377: E140 & 0x3F")
        if not re.search(r"LD\s+A,\s*\(0xe103\)\s*;\s*0x837a", asm, re.I):
            fail("zanac.asm 837a is not LD A,(E103)")
            fails += 1
        else:
            print("  ASM 837a: vs E103")
        if not re.search(r"LD\s+\(IX\+0x00\),\s*0x3e\s*;\s*0x8385", asm, re.I):
            fail("zanac.asm 8385 is not type 62 (0x3E)")
            fails += 1
        else:
            print("  ASM 8385: match → type 62")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    # Packed BCD E103 & 0x3F never equals 0x3F.
    masked = {pack_bcd(n) & 0x3F for n in range(100)}
    if 0x3F in masked:
        fail("BCD E103 & 0x3F unexpectedly includes 0x3F")
        fails += 1
    else:
        print("  BCD E103 & 0x3F never 0x3F (stuck 0xFF closes the gate)")

    # Z80 wrap vs invented saturate.
    wrap = (255 + 1) & 0xFF
    if wrap != 0 or (wrap & 0x3F) != 0:
        fail(f"wrap sim {wrap} want 0")
        fails += 1
    else:
        print("  INC wrap 255→0; &0x3F==0 can match score 00")

    spawn = fn_span(ent, "bool entity_spawn_shot(s16 x, s16 y)")
    if not spawn:
        fail("entity_spawn_shot not found")
        fails += 1
    elif re.search(r"s_alc_shots\s*<\s*255", spawn):
        fail("E140 must not saturate at 255 (76e8 is bare INC)")
        fails += 1
    elif "s_alc_shots++" not in spawn:
        fail("entity_spawn_shot must INC s_alc_shots (76e8)")
        fails += 1
    else:
        print("  entity_spawn_shot: s_alc_shots++ wraps")

    # E141 must still saturate (76bc). Do not "fix" the wrong byte.
    alc = fn_span(ent, "void entity_on_shot_fired(u8 cadence)")
    if not alc or "s_e141++" not in alc or "s_e141--" not in alc:
        fail("E141 76bc saturate (INC / JR NZ / DEC) was reverted")
        fails += 1
    else:
        print("  KEEP: E141 still saturates (76bc)")

    gate = fn_span(ent, "static int descender_on_death(Slot *e)")
    if not gate:
        fail("descender_on_death not found")
        fails += 1
    elif "(s_alc_shots & 0x3F) == (player_score_lo() & 0x3F)" not in gate:
        fail("type 61 gate must stay (E140&0x3F)==(E103&0x3F)")
        fails += 1
    elif "become_riser" not in gate:
        fail("gate match must still become type 62")
        fails += 1
    else:
        print("  8374: gate still (E140&0x3F)==(E103&0x3F) → 62")

    lo = fn_span(ply, "u8 player_score_lo(void)")
    if not lo or "<< 4" not in lo:
        fail("player_score_lo must stay packed BCD E103")
        fails += 1
    else:
        print("  player_score_lo: packed BCD E103")

    # KEEP: fire_reset 7544 / 7548 split just shipped.
    rst = fn_span(ply, "static void fire_reset(void)")
    if not rst or "s_e14f = 0" not in rst or "fire_select(0)" not in rst:
        fail("fire_reset 7544 E14F wipe was reverted")
        fails += 1
    else:
        print("  KEEP: fire_reset 7544 zeroes E14F then fire_select(0)")

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
        print("  KEEP: 78f2 overflow still fire_select(E14B)")

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
    if not fireup or "player_fire_select" not in fireup:
        fail("KIND_FIREUP must still player_fire_select (8eaf JP 7548)")
        fails += 1
    elif "player_fire_reset" in fireup:
        fail("type 83 8eaf is 7548, not fire_reset")
        fails += 1
    else:
        print("  KEEP: type 83 still player_fire_select (7548)")

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

    riser = fn_span(ent, "static void become_riser(Slot *e)")
    grant_life = fn_span(ply, "void player_grant_life(void)")
    if not riser:
        fail("become_riser not found")
        fails += 1
    elif "player_fire_select" in riser or "fire_select" in riser:
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

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")

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
