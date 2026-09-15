#!/usr/bin/env python3
"""Type 21 active 8659 writes R-nibble|0x80 (Early Clock).

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type21_light_bar 0x8635:
    BIT 7,(IX+00) / JR NZ,0x8659
  init 0x863b:
    +17=4, SAT name 0x18, dir=+1a&0x0F, 4cf7, +0c=3, SET 7, ev0x16
    does NOT write +04
  active 0x8659:
    LD A,R / AND 0x0F / OR 0x80 / LD (IX+04),A
    CALL 0x4898 / JP 0x44ba

  TMS SAT colour bit7 = Early Clock (draw at SAT_X-32). Port mode_draw_x
  uses sat_col bit7. spr_kill zeros sat_col; init 863b still writes none.
  Without 8659 the bar stays sat_col=0 and draws 32px right of SAT X.

  Init "no +04" stays. Types 20/37/38/41/42/43 still +04=0x8F.
  dest 0xA6F4 cmd 9 is still a 941b jump. Cmd 9 still never alc_reset.

Usage (from zanac-md):
    python tools/test_type21_8659.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
MAPC = ROOT / "src" / "map_script.c"
PLAYER = ROOT / "src" / "player.c"
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


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    ply = PLAYER.read_text(encoding="utf-8")

    asm = load_asm()
    if asm:
        if not re.search(r"JR\s+NZ,\s*0x8659\s*;\s*0x8639", asm, re.I):
            fail("zanac.asm 8639 is not JR NZ 0x8659")
            fails += 1
        else:
            print("  ASM 8639: JR NZ 0x8659 (active)")
        if re.search(r"LD\s+\(IX\+0x04\).*0x863b", asm, re.I):
            fail("zanac.asm 863b must not write +04")
            fails += 1
        else:
            print("  ASM 863b: init writes no +04")
        if not re.search(r"LD\s+A,\s*R\s*;\s*0x8659", asm, re.I):
            fail("zanac.asm 8659 is not LD A,R")
            fails += 1
        else:
            print("  ASM 8659: LD A,R")
        if not re.search(r"AND\s+0x0f\s*;\s*0x865b", asm, re.I):
            fail("zanac.asm 865b is not AND 0x0F")
            fails += 1
        else:
            print("  ASM 865b: AND 0x0F")
        if not re.search(r"OR\s+0x80\s*;\s*0x865d", asm, re.I):
            fail("zanac.asm 865d is not OR 0x80")
            fails += 1
        else:
            print("  ASM 865d: OR 0x80 (EC bit7)")
        if not re.search(r"LD\s+\(IX\+0x04\),\s*A\s*;\s*0x865f", asm, re.I):
            fail("zanac.asm 865f is not LD (IX+04),A")
            fails += 1
        else:
            print("  ASM 865f: +04 = R-nibble|0x80")
        if not re.search(r"CALL\s+0x4898\s*;\s*0x8662", asm, re.I):
            fail("zanac.asm 8662 is not CALL 0x4898")
            fails += 1
        else:
            print("  ASM 8662: CALL 4898 after 8659")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    init = fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not init:
        fail("init_frag not found")
        return 1
    if "ebullet_apply_vis" not in init:
        fail("init_frag must arm type 21 colour via ebullet_apply_vis")
        fails += 1
    elif re.search(r"if\s*\(\s*variant\s*==\s*21\s*\)\s*\n\s*e->sat_col", init):
        fail("init_frag must not invent a private type 21 +04")
        fails += 1
    else:
        print("  init_frag: type 21 colour via apply_vis")

    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)")
    if not apply or "options_bullet_high" not in apply:
        fail("type 21 8659 must gate on BULLET VISIBILITY via apply_vis")
        fails += 1
    else:
        print("  update: type 21 8659 R-nibble|0x80 on HIGH vis")

    # 8659 must run before 4898 (MSX order), still inside the 21-group.
    step = re.search(
        r"e->variant == 21 \|\| e->variant == 37.*?"
        r"e->variant == 45\).*?"
        r"ebullet_apply_vis\(e\).*?"
        r"if \(step_88_4898\(e\)\)",
        ent,
        re.S,
    )
    if not step:
        fail("8659/apply_vis must sit in the 21/37/38/42/43/45 step before 4898")
        fails += 1
    else:
        print("  update: apply_vis before 4898 in the 21-group")

    # KEEP: PR #51 SAT +04; PR #57 cmd 9 dest 0xA6F4 is a 941b jump.
    if "e->sat_col = 0x89" not in ent:
        fail("type 10 sat_col 0x89 was reverted")
        fails += 1
    else:
        print("  KEEP: type 10 sat_col 0x89")
    if ent.count("sat_col = 0x8F") < 3:
        fail("types 20/37/38/41 sat_col 0x8F was reverted")
        fails += 1
    else:
        print("  KEEP: type 20/37/38/41 sat_col 0x8F")

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

    warp = fn_span(mapc, "void map_script_warp(u16 dest)")
    if not warp or "MAP_ENDING_STREAM" not in warp:
        fail("map_script_warp dest 0xA6F4 must still arm ending")
        fails += 1
    elif "entity_alc_complete" not in warp:
        fail("warp must still entity_alc_complete (E132+=0x20)")
        fails += 1
    else:
        print("  KEEP: warp dest 0xA6F4 / alc_complete")

    if "player_fireup_latch" not in ply:
        fail("KIND_FIREUP player_fireup_latch was reverted")
        fails += 1
    else:
        latch = fn_span(ply, "void player_fireup_latch(void)")
        if not latch or "s_invuln = 0" not in latch or "s_if_latch = 1" not in latch:
            fail("player_fireup_latch must be +1B=0 + SET 7")
            fails += 1
        else:
            print("  KEEP: player_fireup_latch +1B=0 + SET 7")

    if "0xBFD6" in ent or "0xbfd6" in ent:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
