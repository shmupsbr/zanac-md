#!/usr/bin/env python3
"""40DA plays Japan's 4177 nametable walk (blank then reveal).

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  40DA  CALL 40BA
        E722==0 -> 414d
        stop / ev11
        LD (E800),0 / LDIR BC=0x23F     ; blank circular NT
        CALL 4177                       ; walk 24x24 onto VRAM
        LD B,0x64 / CALL 5BEC           ; wait AFTER the blank
        CALL 940c / 9ae4 / 946e
        CALL 4177                       ; reveal dest
        4163 / ev10

  4177  HL=0,0  BC=0x240
        8948(H*8,L*8) write one E800 cell
        DEC H; if sign H=0x17 DEC L
        L -= 5; if sign L += 24

KEEP #93: dest is not loaded before wait_frames. 4177 blank is before
the wait; 4177 reveal is after 940c. No 0xBFD6. No letter 0x20 fill.

Usage (from zanac-md):
    python tools/test_warp_4177.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
GAME = ROOT / "src" / "game.c"
ENTITY = ROOT / "src" / "entity.c"
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


def walk_4177(n: int = 0x240) -> list[tuple[int, int]]:
    h = 0
    l = 0
    out = []
    for _ in range(n):
        out.append((h, l))
        if h == 0:
            h = 0x17
            l = (l - 1) & 0xFF
        else:
            h -= 1
        a = (l - 5) & 0xFF
        if a >= 0x80:
            a = (a + 0x18) & 0xFF
        l = a
    return out


def main() -> int:
    fails = 0
    mapc = MAPC.read_text(encoding="utf-8")
    game = GAME.read_text(encoding="utf-8")
    ent = ENTITY.read_text(encoding="utf-8")
    asm = load_asm()

    cells = walk_4177()
    if len(cells) != 0x240:
        fail(f"sim walk length {len(cells)}")
        fails += 1
    uniq = set(cells)
    if len(uniq) != 0x240:
        fail(f"4177 walk is not a 24x24 permutation ({len(uniq)} unique)")
        fails += 1
    else:
        print("  sim: 4177 visits 576 unique cells")
    if (0, 0) != cells[0]:
        fail("4177 must start at (0,0)")
        fails += 1
    if cells[1] != (23, 18):
        fail(f"4177 second cell must be (23,18) (got {cells[1]})")
        fails += 1
    else:
        print("  sim: (0,0) then DEC-H wrap + L-5 -> (23,18)")

    if asm:
        if not re.search(r"LD\s+\(HL\),\s*0x00\s*;\s*0x40fb", asm, re.I):
            fail("zanac.asm 40FB is not LD (E800),0")
            fails += 1
        else:
            print("  ASM 40FB: E800 blank is 0, not 0x28")
        if not re.search(r"CALL\s+0x4177\s*;\s*0x4105", asm, re.I):
            fail("zanac.asm 4105 is not CALL 4177")
            fails += 1
        else:
            print("  ASM 4105: 4177 before wait_frames")
        if not re.search(r"CALL\s+0x4177\s*;\s*0x4147", asm, re.I):
            fail("zanac.asm 4147 is not CALL 4177")
            fails += 1
        else:
            print("  ASM 4147: 4177 after 946e")

    if "dump4177_begin" not in mapc:
        fail("40DA must walk 4177 (dump4177_begin)")
        fails += 1
    else:
        print("  map_script: 4177 walk present")
    if "DUMP4177_CELLS      0x240" not in mapc and "DUMP4177_CELLS 0x240" not in mapc:
        fail("4177 must visit BC=0x240 cells")
        fails += 1
    if "s_dump_h = 0x17" not in mapc:
        fail("4177 DEC-H wrap must reload H=0x17")
        fails += 1
    if "a + 0x18" not in mapc:
        fail("4177 L-=5 wrap must ADD 0x18")
        fails += 1

    warp = fn_span(mapc, "void map_script_warp(u16 dest)")
    if not warp:
        fail("map_script_warp not found")
        return 1
    if "memset(s_e800, 0" not in warp:
        fail("map_script_warp must LDIR E800=0 before 4177 blank")
        fails += 1
    else:
        print("  map_script_warp: E800 blank")
    if "dump4177_begin(1)" not in warp:
        fail("map_script_warp must start 4177 blank before wait")
        fails += 1
    if "script_boot" in warp or "map_script_start_ending" in warp:
        fail("KEEP #93: do not load dest before wait_frames")
        fails += 1
    else:
        print("  KEEP #93: no load before wait")

    tick = fn_span(mapc, "static void warp_jingle_tick(void)")
    if not tick:
        fail("warp_jingle_tick not found")
        fails += 1
    else:
        if tick.find("dump4177_begin(2)") < 0:
            fail("reveal 4177 must start after warp_commit_load")
            fails += 1
        if tick.find("warp_commit_load") > tick.find("dump4177_begin(2)"):
            fail("940c must run before 4177 reveal")
            fails += 1
        else:
            print("  warp_jingle_tick: load then 4177 reveal")
        if "s_warp_jwait = 0x64" not in tick and "s_warp_jwait = 0x64" not in mapc:
            fail("wait_frames 0x64 was reverted")
            fails += 1
        if tick.find("warp_commit_load") > tick.find("SND_EV_THEME"):
            fail("4163/ev10 must run after 940c, not before")
            fails += 1

    if "s_defer_nt_flush" not in mapc:
        fail("script_boot must defer the instant 24-row flush for 4177")
        fails += 1
    else:
        print("  script_boot: flush deferred so 4177 can reveal")

    if "0xBFD6" in ent or "0xbfd6" in ent or "0xBFD6" in mapc:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")
    if "map_script_warp_waiting" not in game:
        fail("game_update must skip 9393 during 40DA")
        fails += 1

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
