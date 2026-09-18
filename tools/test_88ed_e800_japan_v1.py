#!/usr/bin/env python3
"""Japan v1 88ed dest writes E800[(E714+Y/8) mod 24] then VRAM (8948).

88ed is the punch routine at 0x88ED (CALL 42ed), not a dest blob.
Dests live at 88b1/88b8/88c2/88cb/88d8; 88ab is the type84-86 word table.

PR #85 hide-SAT left live tiles in wrap RAM. When dma_nt_row copies e800
on wrap, the original ground-enemy face scrolls back in — half leftover
if only one dest row missed the wrap write.

Type 70/71 8833 has no JP 88ed (CALL bfc8 / 4a6a / type 72). Do not
punch a 3x2 of 0x28 onto the yellow totem (blue/white junk).

Fails on 8428438: no punch_cell, no e800 persist in nt_put.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MS = (ROOT / "src" / "map_script.c").read_text(encoding="utf-8", errors="replace")
MH = (ROOT / "inc" / "map_script.h").read_text(encoding="utf-8", errors="replace")
JAPAN_V1_SHA1 = "46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2"
ROM_CANDIDATES = [
    pathlib.Path("/tmp/zanac-japan-v1.rom"),
    pathlib.Path("/tmp/refs/zanac-japan-v1.rom"),
    pathlib.Path("/tmp/zanac.rom"),
    pathlib.Path("/tmp/zanac-jp.bin"),
    ROOT.parent / "zanac.rom",
]
ASM_CANDIDATES = [
    pathlib.Path("/tmp/zanac-re/source/zanac.asm"),
    pathlib.Path("/tmp/refs/zanac-re/source/zanac.asm"),
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]

# Japan v1 dests (row count, then per row: width + tiles).
DEST_88B1 = bytes([0x02, 0x02, 0x3B, 0x3C, 0x02, 0x3A, 0x3D])
DEST_88B8 = bytes([0x03, 0x02, 0x3B, 0x3C, 0x02, 0x3E, 0x3E, 0x02, 0x3A, 0x3D])
DEST_88C2 = bytes([0x02, 0x03, 0x3B, 0x3E, 0x3C, 0x03, 0x3A, 0x3E, 0x3D])


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_japan_v1() -> bytes | None:
    for p in ROM_CANDIDATES:
        if not p.is_file():
            continue
        data = p.read_bytes()
        if len(data) == 262144 and hashlib.sha1(data).hexdigest() == JAPAN_V1_SHA1:
            return data
    return None


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def main() -> None:
    if "static void punch_cell(" not in MS:
        fail("need punch_cell: write e800 wrap row THEN displayed NT (MSX 8948)")
    if "s_e800[(u8)((s_e714 + screen_row) % BOOT_ROWS)][col] = tid" not in MS:
        fail("punch_cell must persist wreckage at e800[(e714+Y/8)%24]")
    punch = MS.split("static void punch_cell(", 1)[1][:900]
    if "VDP_setTileMapXY" not in punch and "stamp_vram(" not in punch:
        fail("punch_cell must also poke displayed NT")
    if "s_e800[s_e714][col] = tid" not in MS:
        fail("nt_put must persist wrap RAM even when vis>=24 (letterbox/wrap)")
    if "map_script_clear_totem_face" in MH or "map_script_clear_totem_face" in MS:
        fail("8833 has no 88ed — do not punch totem face to 0x28")
    if "punch_cell(col, srow, 0x28)" in MS:
        fail("0x28 on the yellow totem is the blue/white junk")
    if "SPR_setVisibility(sp, HIDDEN)" in MS:
        fail("do not re-ship SAT-hide as the wreckage fix")

    if "k_88ab_84[] = { 2, 2, 0x3B, 0x3C, 2, 0x3A, 0x3D }" not in MS:
        fail("k_88ab_84 must stay Japan v1 88b1 dest")
    if "k_88ab_85[] = { 3, 2, 0x3B, 0x3C, 2, 0x3E, 0x3E, 2, 0x3A, 0x3D }" not in MS:
        fail("k_88ab_85 must stay Japan v1 88b8 dest")
    if "k_88ab_86[] = { 2, 3, 0x3B, 0x3E, 0x3C, 3, 0x3A, 0x3E, 0x3D }" not in MS:
        fail("k_88ab_86 must stay Japan v1 88c2 dest")

    asm = load_asm()
    if asm:
        if "CALL	 0xbfc8						; 0x8833" not in asm:
            fail("zanac-re 8833 must stay CALL bfc8 (no 88ed)")
        if "JP	 0x88ed						; 0x8833" in asm:
            fail("zanac-re 8833 must not JP 88ed")
        if "JP	 0x88ed						; 0x8871" not in asm:
            fail("zanac-re 8854/8871 must JP 88ed")
        if "LD	 BC, 0xe800					; 0x897b" not in asm:
            fail("zanac-re 8948 must compute E800[(E714+Y/8) mod 24]")

    rom = load_japan_v1()
    if rom:
        if rom[0x88B1 : 0x88B1 + len(DEST_88B1)] != DEST_88B1:
            fail("Japan v1 88b1 dest mismatch")
        if rom[0x88B8 : 0x88B8 + len(DEST_88B8)] != DEST_88B8:
            fail("Japan v1 88b8 dest mismatch")
        if rom[0x88C2 : 0x88C2 + len(DEST_88C2)] != DEST_88C2:
            fail("Japan v1 88c2 dest mismatch")
        if rom[0x88ED] != 0xCD:  # CALL
            fail("Japan v1 88ed must be the punch routine (CD), not dest data")
        print("PASS (MD locks + Japan v1 ROM dests + zanac-re 8833/8948)")
        return

    print("PASS (MD locks + dest tables; Japan v1 ROM not in candidates)")


if __name__ == "__main__":
    main()
