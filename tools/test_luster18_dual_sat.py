#!/usr/bin/env python3
"""Type 18 luster is the yellow yo-yo: 0x8B, X-home, opens 0x74->0x78.

Japan v1 handler_type18 0x7CB3:
  C=0x8B, +0c=0x13, X-home tgt FF/00 accel 0x0e, sides 60/90.
  Shared 7c14 SAT 0x74 / marker 0x7C (pat 29 / 31).
  7cfc +1d==8: SAT 0x78 / IY+03 0x80 (pat 30 / 32) then type37.

71f6 writes complement SAT X = parent IX+02, color 0x81 (EC).
Primary +04 0x8B is also EC, so both hardware X = SAT-32.
Port: spr_sync uses one draw X for the pair (primary sat_col EC).
Do not draw black at SAT-32 while colour sits at SAT X.

Usage (from zanac-md):
    python tools/test_luster18_dual_sat.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
REB = ROOT / "tools" / "rebuild_sprites.py"
PNG = ROOT / "res" / "sprites" / "objs.png"
ASM_CANDIDATES = (
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
)


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


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
    ent = ENT.read_text(encoding="utf-8")
    reb = REB.read_text(encoding="utf-8")

    spawn = fn_span(ent, "static void spawn_luster(Slot *e, u8 type)")
    if not spawn:
        return fail("spawn_luster not found")
    if "e->sat_col = 0x8B" not in spawn:
        return fail("type 18 7ccd +04 must be 0x8B")
    if "FRAME_LUSTER_A" not in spawn or "FRAME_LUSTER_A_C" not in spawn:
        return fail("type 18 start SAT 0x74 / 0x7C (pat 29 / 31)")
    print("  spawn type 18: 0x8B + FRAME_LUSTER_A / _C")

    step = fn_span(ent, "static void luster_step(Slot *e)")
    if not step:
        return fail("luster_step not found")
    if "spr_place(e, FRAME_LUSTER)" not in step:
        return fail("7cfc open must spr_place FRAME_LUSTER (SAT 0x78)")
    if "FRAME_LUSTER_C" not in step:
        return fail("7cfc open complement is SAT 0x80 FRAME_LUSTER_C")
    if "e->clock == 8" not in step:
        return fail("7cfc open telegraph is +1d==8")
    print("  7cfc: FRAME_LUSTER + FRAME_LUSTER_C at +1d==8")

    sync = fn_span(ent, "static void spr_sync(Slot *s)")
    if not sync:
        return fail("spr_sync not found")
    if "mdx = dx" not in sync:
        return fail("71f6 pair must share the primary draw X (same EC)")
    if "mode_draw_x(s->x, 0x81)" in sync:
        return fail("do not recompute complement X from 0x81 (32px split if +04 loses EC)")
    print("  spr_sync: complement X = primary X")

    place = fn_span(ent, "static void marker_place(Slot *s, u16 frame)")
    if not place:
        return fail("marker_place not found")
    if "mode_draw_x(s->x, s->sat_col)" not in place:
        return fail("marker_place must use primary sat_col for draw X")
    if "mode_draw_x(s->x, 0x81)" in place:
        return fail("marker_place must not use a separate 0x81 EC path")
    print("  marker_place: same SAT X as primary")

    if "(30, 14, False)" not in reb:
        return fail("FRAME_LUSTER is pat 30 (SAT 0x78)")
    if "(32, 1, True)" not in reb:
        return fail("FRAME_LUSTER_C is pat 32 (SAT 0x80)")
    if "(29, 11, False)" not in reb:
        return fail("FRAME_LUSTER_A is pat 29 (SAT 0x74)")
    if "(31, 1, True)" not in reb:
        return fail("FRAME_LUSTER_A_C is pat 31 (SAT 0x7C)")
    print("  rebuild: pats 29/31 closed, 30/32 open")

    try:
        from PIL import Image
    except ImportError:
        return fail("Pillow required to prove objs.png luster pair")

    im = Image.open(PNG)
    # FRAME_LUSTER=3, FRAME_LUSTER_C=29, FRAME_LUSTER_A=53, FRAME_LUSTER_A_C=54
    def bbox(i: int) -> tuple[int, int, int, int]:
        fr = im.crop((i * 16, 0, (i + 1) * 16, 16))
        xs, ys = [], []
        for y in range(16):
            for x in range(16):
                if fr.getpixel((x, y)):
                    xs.append(x)
                    ys.append(y)
        return (min(xs), min(ys), max(xs), max(ys))

    b3, b29 = bbox(3), bbox(29)
    b53, b54 = bbox(53), bbox(54)
    if b3[0] != 0 or b29[0] != 0:
        return fail("open pair must share left origin 0 (not a trimmed shift)")
    if b53[0] != 0 or b54[0] != 0:
        return fail("closed pair must share left origin 0")
    print("  objs.png: closed/open pairs share x=0 origin")

    asm_path = next((p for p in ASM_CANDIDATES if p.is_file()), None)
    if asm_path:
        asm = asm_path.read_text(encoding="utf-8", errors="replace")
        if "0x7cfc" in asm and "0x78" in asm and "0x80" in asm:
            print("  zanac.asm: 7cfc SAT 0x78 / 0x80")
        if "LD	 C, 0x8b" in asm or "0x7ccd" in asm:
            print("  zanac.asm: type 18 C=0x8B")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    print("ok: type 18 yellow yo-yo dual-SAT shares one EC draw X")
    return 0


if __name__ == "__main__":
    sys.exit(main())
