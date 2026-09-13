#!/usr/bin/env python3
"""0x9183 stage-clear BONUS banner: skip-N bit6, 0x3966 + 0x49B5.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  0x9183  BIT 6,(IX+0x57) / JR NZ 9198
          LD HL,0x3966 / CALL 0x5C25   ; SETWRT + inline "BONUS"
          bytes 42 4F 4E 55 53 00
          LD DE,0x396B
  0x91AF  BIT 6 again skips 0x49B5
          HL = 0x4AEC + award*3 (high byte of 0x4AEA triplet)
          CALL 0x49B5                  ; 6 digits, lead 0->0x20, then 0x30
  0x91C1  CALL 0x4A74 add_score

  47 of 48 live cmd-B E157 values have bit6 clear (only R8 0xF0 skips).
  Port used to add the 0x9302 award and never print.

Usage (from zanac-md):
    python tools/test_bonus_9183.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
PLY = ROOT / "src" / "player.c"
PLYH = ROOT / "inc" / "player.h"
HUD = ROOT / "src" / "hud.c"
BLOB = ROOT / "res" / "map_blob.bin"
BLOB_BASE = 0x9B64
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]

K_CLEAR = [
    0x0A, 0x0C, 0x0D, 0x10, 0x0E, 0x0F, 0x0E, 0x0F,
    0x0F, 0x10, 0x11, 0x11, 0x00, 0x00, 0x00, 0x11,
    0x12, 0x13, 0x14,
]
K_AWARD = (
    0, 1, 6, 10, 17, 20, 30, 50, 80, 100,
    200, 400, 800, 1000, 1500, 2000, 3000, 4000, 5000, 10000, 200000,
)


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


def format_bonus_score(n: int) -> str:
    """0x49B5: 6 digits, lead 0 -> space, then trailing 0x30."""
    if n > 999999:
        n = 999999
    s = f"{n:06d}"
    out = []
    nz = False
    for ch in s:
        if ch != "0" or nz:
            out.append(ch)
            nz = True
        else:
            out.append(" ")
    return "".join(out) + "0"


def main() -> int:
    fails = 0
    mapc = MAPC.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")
    plyh = PLYH.read_text(encoding="utf-8")
    hud = HUD.read_text(encoding="utf-8")

    asm = load_asm()
    if asm:
        if not re.search(r"BIT\s+0x6,\s*\(IX\+0x57\)\s*;\s*0x9183", asm):
            fail("ASM 9183 must BIT 6,E157")
            fails += 1
        else:
            print("  ASM 9183: BIT 6,E157")
        if not re.search(r"LD\s+HL,\s*0x3966\s*;\s*0x9189", asm):
            fail("ASM 9189 must SETWRT 0x3966")
            fails += 1
        else:
            print("  ASM 9189: HL=0x3966")
        if not re.search(r"LD\s+DE,\s*0x396b\s*;\s*0x9195", asm):
            fail("ASM 9195 must DE=0x396B")
            fails += 1
        else:
            print("  ASM 9195: DE=0x396B")
        if not re.search(r"LD\s+HL,\s*0x4aec\s*;\s*0x91b9", asm):
            fail("ASM 91B9 must index 0x4AEC (high byte of 0x4AEA)")
            fails += 1
        else:
            print("  ASM 91B9: HL=0x4AEC")
        if not re.search(r"CALL\s+0x49b5\s*;\s*0x91bd", asm):
            fail("ASM 91BD must CALL 0x49B5")
            fails += 1
        else:
            print("  ASM 91BD: CALL 0x49B5")
        # Inline BONUS after CALL 0x5C25 at 0x918C: 42 4F 4E 55 53 00
        chunk = asm[asm.find("0x9189") : asm.find("0x9189") + 800] if "0x9189" in asm else ""
        if "0x42" in chunk or "BONUS" in mapc:
            print("  ASM/port: BONUS string present")
        else:
            fail("BONUS bytes not found near 0x9189")
            fails += 1
    else:
        print("  ASM: not found (C checks only)")

    draw = fn_span(mapc, "static void bonus_draw(u8 award_idx)")
    if not draw:
        fail("bonus_draw not found")
        fails += 1
    else:
        if "s_e157 & 0x40" not in draw:
            fail("bonus_draw must skip when E157 bit6 set")
            fails += 1
        else:
            print("  bonus_draw: BIT 6 skip")
        if 'hud_draw_str(BG_A, 6, mode_text_row(11), "BONUS")' not in draw:
            fail("BONUS must be BG_A col 6 row 11 (0x3966)")
            fails += 1
        else:
            print("  bonus_draw: BG_A col 6 row 11 BONUS")
        if "hud_draw_str(BG_A, 11, mode_text_row(11), score)" not in draw:
            fail("score must be BG_A col 11 row 11 (0x396B)")
            fails += 1
        else:
            print("  bonus_draw: BG_A col 11 row 11 score")
        if "MODE_ORIGINAL" not in draw:
            fail("BONUS is Original-only (like ROUND)")
            fails += 1
        else:
            print("  bonus_draw: Original only")

    fmt = fn_span(mapc, "static void format_bonus_score(char *out, u32 n)")
    if not fmt or "out[6] = '0'" not in fmt:
        fail("format_bonus_score must append 0x49D6 trailing 0")
        fails += 1
    else:
        print("  format_bonus_score: trailing 0 (0x49D6)")

    if format_bonus_score(200) != "   2000":
        fail(f"200 display want '   2000' got {format_bonus_score(200)!r}")
        fails += 1
    else:
        print("  display 200 -> '   2000' (R1 first base 0x9302[0]=0x0A)")
    if format_bonus_score(0) != "      0":
        fail(f"0 display want '      0' got {format_bonus_score(0)!r}")
        fails += 1
    else:
        print("  display 0 -> '      0'")

    cleared = fn_span(mapc, "void map_script_base_cleared(void)")
    if not cleared or "bonus_draw" not in cleared:
        fail("map_script_base_cleared must bonus_draw")
        fails += 1
    else:
        print("  map_script_base_cleared: bonus_draw")
    if cleared and "player_add_score" not in cleared:
        fail("KEEP: still player_add_score from 0x9302")
        fails += 1
    else:
        print("  KEEP: 0x9302 award still added")

    finish = fn_span(mapc, "static void base_clear_finish(void)")
    if not finish or "bonus_clear" not in finish:
        fail("base_clear_finish must bonus_clear")
        fails += 1
    else:
        print("  base_clear_finish: bonus_clear")

    clr = fn_span(mapc, "static void bonus_clear(void)")
    if not clr or "hud_fill_tile(BG_A, 6, mode_text_row(11), 0, 12)" not in clr:
        fail("bonus_clear must wipe 12 BG_A tiles at col 6 row 11 with tile 0")
        fails += 1
    else:
        print("  bonus_clear: tile 0 x12 (not opaque 0x20)")

    if "player_award_points" not in plyh or "player_award_points" not in ply:
        fail("player_award_points must expose 0x4AEA")
        fails += 1
    else:
        print("  player_award_points: 0x4AEA getter")

    # KEEP: ROUND banner path
    if "hud_draw_str(BG_A, 8, mode_text_row(10), s_ms.banner)" not in mapc:
        fail("KEEP: ROUND banner 0x3948")
        fails += 1
    else:
        print("  KEEP: ROUND banner BG_A col 8 row 10")
    if "hud_fill_tile(BG_A, 8, mode_text_row(10), 0, 9)" not in mapc:
        fail("KEEP: ROUND banner clear")
        fails += 1
    else:
        print("  KEEP: ROUND banner clear tile 0")

    # KEEP: write_e701 includes 0; credits 47AA skip-N
    if "s_continue_round = round" not in mapc:
        fail("KEEP: write_e701 copies 0..8")
        fails += 1
    else:
        print("  KEEP: write_e701 0..8")
    if "0x47AA" not in mapc:
        fail("KEEP: credits 47AA")
        fails += 1
    else:
        print("  KEEP: credits 47AA")

    if "TIME" not in hud or "0x3AB9" not in hud:
        fail("KEEP: TIME HUD 0x901A")
        fails += 1
    else:
        print("  KEEP: TIME still HUD 0x3AB9")

    # Live cmd-B: R1 first base E157=0 -> award 0x0A -> 200
    if K_CLEAR[0] != 0x0A or K_AWARD[0x0A] != 200:
        fail("R1 first-base award must be 200")
        fails += 1
    else:
        print("  R1 row 300 E157=0 -> 0x9302[0]=0x0A -> 200")

    if fails:
        print(f"{fails} FAIL(S)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
