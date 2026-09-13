#!/usr/bin/env python3
"""PAL3[8] red-pink ground is darkened; BONUS / enemy reds stay.

Charset tiles 0x17/0x18 (and most of 0x19) are a TMS 6/8 stipple — the
bright half is TMS 8. Digits (BONUS xxxxx) are CT 0x90 = TMS 9 on 0.
Sprites live on PAL2, so SAT 0x88/0x89 asteroids and flyers do not share
the playfield CRAM word.

Old: RGB24_TO_VDPCOLOR(0xFC5554) = 0x066E  (7,3,3)
New: TMS_DARK_RED_PINK           = 0x044C  (6,2,2)  ~ RGB*0.8

Usage (from zanac-md):
    python tools/test_ground_red_cram.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDR = ROOT / "inc" / "map_script.h"
MAP = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
TITLE = ROOT / "src" / "title.c"
CT = ROOT / "res" / "charset_ct.bin"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def rgb24_to_vdp_round(rgb: int) -> int:
    """Per-channel +0x10, saturate, top 3 bits — same rounding as s_tms_pal."""
    r = min(255, ((rgb >> 16) & 0xFF) + 0x10) >> 5
    g = min(255, ((rgb >> 8) & 0xFF) + 0x10) >> 5
    b = min(255, (rgb & 0xFF) + 0x10) >> 5
    return ((b & 7) << 9) | ((g & 7) << 5) | ((r & 7) << 1)


def main() -> int:
    hdr = HDR.read_text(encoding="utf-8")
    mp = MAP.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    title = TITLE.read_text(encoding="utf-8")
    ct = CT.read_bytes()

    if "#define TMS_DARK_RED_PINK  0x044C" not in hdr:
        return fail("TMS_DARK_RED_PINK must be CRAM 0x044C")
    print("  TMS_DARK_RED_PINK 0x044C")

    old = rgb24_to_vdp_round(0xFC5554)
    if old != 0x066E:
        return fail("old TMS 8 rounding must stay 0x066E, got 0x%04X" % old)
    new = rgb24_to_vdp_round(0xCA4443)
    if new != 0x044C:
        return fail("0xCA4443 (TMS8*0.8) must land on 0x044C, got 0x%04X" % new)
    print("  old 0xFC5554 -> 0x066E; *0.8 0xCA4443 -> 0x044C")

    pal = re.search(
        r"static const u16 s_tms_pal\[16\] = \{([^}]+)\}",
        mp,
    )
    if not pal:
        return fail("s_tms_pal not found")
    entries = [ln.strip().rstrip(",") for ln in pal.group(1).splitlines() if ln.strip()]
    if len(entries) != 16:
        return fail("s_tms_pal must have 16 entries, got %d" % len(entries))
    if entries[8] != "TMS_DARK_RED_PINK":
        return fail("PAL3[8] must be TMS_DARK_RED_PINK, got %r" % entries[8])
    if entries[9] != "RGB24_TO_VDPCOLOR(0xFF7978)":
        return fail("PAL3[9] BONUS digits must stay TMS 9 0xFF7978")
    if entries[6] != "RGB24_TO_VDPCOLOR(0xD4524D)":
        return fail("PAL3[6] dark-red stipple half must stay")
    print("  s_tms_pal[8] darkened; [6]/[9] KEEP")

    if "RGB24_TO_VDPCOLOR(0xFC5554)" not in ent:
        return fail("entity k_tms_vdp TMS 8 must stay 0xFC5554 (PAL2 enemies)")
    if "TMS_DARK_RED_PINK" in ent:
        return fail("do not bind enemy/fire CRAM to the ground slot")
    print("  PAL2 k_tms_vdp[8] KEEP 0xFC5554")

    # Title PAL3 is not the scrolling ground; digits there stay TMS 9.
    if "RGB24_TO_VDPCOLOR(0xFF7978)" not in title:
        return fail("title TMS 9 digits must stay")
    print("  title TMS 9 KEEP")

    if len(ct) != 2048:
        return fail("charset_ct.bin size")
    for tid in (0x17, 0x18):
        rows = ct[tid * 8 : tid * 8 + 8]
        if any((b >> 4) != 6 or (b & 0x0F) != 8 for b in rows):
            return fail("tile 0x%02X must stay CT 68 (TMS 6/8 ground)" % tid)
    digit = ct[0x30 * 8 : 0x30 * 8 + 8]
    if digit != bytes([0x90] * 8):
        return fail("digit tiles must stay CT 90 (TMS 9); do not recolor BONUS")
    print("  CT: 0x17/0x18 = 68; digits = 90")

    print("ok: PAL3[8] ground darkened; enemies/BONUS slots unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
