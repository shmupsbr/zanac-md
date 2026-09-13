#!/usr/bin/env python3
"""0x49B5 SCORE/TOP print is 6 BCD digits + 0x49D6 trailing 0x30.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  render_score_bcd 0x49B5:
    B=3 bytes from HL downward; each nibble -> '0'+d or 0x20 if still
    leading zero. After the 6 digits:
      0x49D6  LD A,0x30
      0x49D8  OUT (C),A

  Callers (all share that trailing 0):
    0x4996 render_lives_score   title SCORE @0x3809 / TOP @0x3815
    0x49AF render_score_row2    HUD SCORE @0x3918
    0x49A7 render_topscore_row2 HUD TOP   @0x38B8
    0x4AB5 score_display_update flash SHOW (same 0x38B8)
    0x91BD BONUS                already locked by test_bonus_9183.py

  Flash blank 0x4ABE FILVRM BC=7 at 0x38B8 — 7 cells, not 6.

  Port HUD/title printed 6 digits and dropped 0x49D6. Score 0 was six
  spaces on the HUD (no visible 0). BONUS already appended the 0.

Usage (from zanac-md):
    python tools/test_score_49b5_trail.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUD = ROOT / "src" / "hud.c"
TITLE = ROOT / "src" / "title.c"
MAPC = ROOT / "src" / "map_script.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source/zanac.asm",
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


def format_49b5(n: int) -> str:
    """6 lead-blank digits + trailing 0x30."""
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
    hud = HUD.read_text(encoding="utf-8")
    title = TITLE.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")

    asm = load_asm()
    if asm:
        if not re.search(r"LD\s+A,\s*0x30\s*;\s*0x49d6", asm):
            fail("ASM 49D6 must LD A,0x30")
            fails += 1
        else:
            print("  ASM 49D6: LD A,0x30")
        if not re.search(r"OUT\s+\(C\),\s*A\s*;\s*0x49d8", asm):
            fail("ASM 49D8 must OUT (C),A")
            fails += 1
        else:
            print("  ASM 49D8: OUT trailing 0")
        if not re.search(r"LD\s+BC,\s*0x7\s*;\s*0x4abe", asm):
            fail("ASM 4ABE flash blank must FILVRM 7")
            fails += 1
        else:
            print("  ASM 4ABE: FILVRM BC=7")
        if not re.search(r"LD\s+DE,\s*0x3809\s*;\s*0x4999", asm):
            fail("ASM 4999 title SCORE digits at 0x3809")
            fails += 1
        else:
            print("  ASM 4999: title SCORE @0x3809")
        if not re.search(r"LD\s+DE,\s*0x3815\s*;\s*0x49a2", asm):
            fail("ASM 49A2 title TOP digits at 0x3815")
            fails += 1
        else:
            print("  ASM 49A2: title TOP @0x3815")
        if not re.search(r"LD\s+DE,\s*0x3918\s*;\s*0x49b2", asm):
            fail("ASM 49B2 HUD SCORE at 0x3918")
            fails += 1
        else:
            print("  ASM 49B2: HUD SCORE @0x3918")
        if not re.search(r"LD\s+DE,\s*0x38b8\s*;\s*0x49a7", asm):
            fail("ASM 49A7 HUD TOP at 0x38B8")
            fails += 1
        else:
            print("  ASM 49A7: HUD TOP @0x38B8")
    else:
        print("  ASM: not found (C checks only)")

    score6 = fn_span(hud, "static void hud_score6(u16 col, u16 row, u32 score)")
    if not score6:
        fail("hud_score6 not found")
        fails += 1
    else:
        if "col + 6" not in score6 or "'0'" not in score6:
            fail("hud_score6 must write the 0x49D6 trailing 0 at col+6")
            fails += 1
        else:
            print("  hud_score6: trailing 0 at col+6")
        if "i == 5" in score6:
            fail("hud_score6 must not force the ones place (0x49DD lead-blank)")
            fails += 1

    if "hud_fill_tile(WINDOW, HUD_COL, hud_y(5), ' ', 7)" not in hud:
        fail("TOP flash blank must stay FILVRM 7 (0x4ABE)")
        fails += 1
    else:
        print("  hud_draw_player: flash blank 7 cells")

    top = fn_span(title, "static void draw_score_top(void)")
    if not top:
        fail("draw_score_top not found")
        fails += 1
    else:
        if "buf[6] = '0'" not in top:
            fail("title SCORE/TOP must append 0x49D6 trailing 0")
            fails += 1
        else:
            print("  draw_score_top: trailing 0")
        if "i == 5" in top:
            fail("title must not force the ones place (n==0 is six spaces + 0)")
            fails += 1
        else:
            print("  draw_score_top: lead-blank includes ones place")
        if "draw_str_pal(buf, 9, row, PAL3)" not in top:
            fail("title SCORE digits must stay col 9 (0x3809)")
            fails += 1
        if "draw_str_pal(buf, 21, row, PAL3)" not in top:
            fail("title TOP digits must stay col 21 (0x3815)")
            fails += 1

    if "out[6] = '0'" not in mapc:
        fail("do not drop BONUS 0x49D6 trailing 0")
        fails += 1
    else:
        print("  format_bonus_score: trailing 0 kept")

    if format_49b5(0) != "      0":
        fail(f"0 display want '      0' got {format_49b5(0)!r}")
        fails += 1
    else:
        print("  display 0 -> '      0'")
    if format_49b5(1) != "     10":
        fail(f"1 display want '     10' got {format_49b5(1)!r}")
        fails += 1
    else:
        print("  display 1 -> '     10'")
    if format_49b5(100000) != "1000000":
        fail(f"100000 display want '1000000' got {format_49b5(100000)!r}")
        fails += 1
    else:
        print("  display 100000 -> '1000000'")
    if format_49b5(200) != "   2000":
        fail(f"200 display want '   2000' got {format_49b5(200)!r}")
        fails += 1
    else:
        print("  display 200 -> '   2000'")

    if fails:
        print(f"{fails} failure(s)", file=sys.stderr)
        return 1
    print("ok: 0x49B5 HUD/title SCORE/TOP include the 0x49D6 trailing 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
