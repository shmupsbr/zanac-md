#!/usr/bin/env python3
"""Gun fire SAT 0x4C is a COLOURED primary, not a black complement.

Japan v1 816d:
  LD (IX+0x03),0x4C     ; pat 19 onto the PRIMARY, +04 colour stays
  marker +03 := 0x54    ; pat 21, colour 0x81 (71f6)

FRAME_LOGA_C is unfolded as complement-only (nibble 1). Using it as the
gun primary without remapping to sat_col left a black silhouette sitting
off the coloured idle body -- the "some enemies" 71f6 desync. Other
pairs stay same-X / Y-0x11. Ship Y+2 stays 7735-only.

Usage (from zanac-md):
    python tools/test_gun_816d_primary.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PLAYER = ROOT / "src" / "player.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]


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


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    player = PLAYER.read_text(encoding="utf-8")
    asm = load_asm()

    if asm:
        if not re.search(r"LD\s+\(IX\+0x03\),\s*0x4c\s*;\s*0x816d", asm, re.I):
            return fail("zanac.asm 816d is not LD (IX+03),0x4C")
        print("  ASM 816d: primary SAT name 0x4C")
        if not re.search(r"LD\s+\(HL\),\s*0x54\s*;\s*0x817a", asm, re.I):
            return fail("zanac.asm 817a is not marker SAT 0x54")
        print("  ASM 817a: marker SAT 0x54")
        if not re.search(r"SUB\s+0x11\s*;\s*0x71fd", asm, re.I):
            return fail("zanac.asm 71f6 is not SUB 0x11")
        print("  ASM 71fd: complement Y = parentY-0x11")
        if not re.search(r"ADD\s+A,\s*0xf1\s*;\s*0x7735", asm, re.I):
            return fail("zanac.asm 7735 is not ADD 0xF1 (ship Y+2)")
        print("  ASM 7735: ship complement Y+2")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)")
    if not up:
        return fail("spr_upload_color not found")
    if "KIND_GUN" not in up or "FRAME_LOGA_C" not in up:
        return fail("816d FRAME_LOGA_C as gun primary must remap to sat_col")
    if "want = (u8)(s->sat_col & 0x0F)" not in up:
        return fail("gun 0x4C primary must use +04 colour, not baked black")
    print("  spr_upload_color: 816d paints pat 19 in sat_col")

    fire = fn_span(ent, "static void gun_fire(Slot *e)")
    if not fire:
        return fail("gun_fire not found")
    if "FRAME_LOGA_C" not in fire or "FRAME_LOGA_D" not in fire:
        return fail("816d must still be primary 0x4C + marker 0x54")
    print("  gun_fire: FRAME_LOGA_C + FRAME_LOGA_D")

    sync = fn_span(ent, "static void spr_sync(Slot *s)")
    if not sync:
        return fail("spr_sync not found")
    if "mode_draw_x(s->x, 0x81)" not in sync:
        return fail("71f6 complement X must stay parent X / colour 0x81")
    if "mdy = dy" not in sync:
        return fail("71f6 flyer complement Y must match primary draw Y")
    if "+ 2" in sync:
        return fail("do not apply ship Y+2 to flyer complements")
    print("  spr_sync: flyers same X/Y; no blanket Y+2")

    if "ship_compl_draw_y" not in player or "+ 2" not in player:
        return fail("ship 7735 Y+2 KEEP was reverted")
    print("  KEEP: ship Y+2 only")

    print("ok: 816d coloured primary; other 71f6 pairs unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
