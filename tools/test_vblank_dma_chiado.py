#!/usr/bin/env python3
"""Uncapped VRAM DMA snows the top ~1/5 of the 224-line display.

NTSC vblank is ~38 lines. SGDK's default DMA_setMaxTransferSize is 7200
bytes so the flush finishes before active display. MaxTransferSize(0)
lets a 16KB queue run into the next frame: those scanlines show random
pixels (chiado) from the top down — about 40px ≈ 1/5 of 224.

MSX has no MD VRAM DMA; Original 256x192 + HUD + letterbox must not
pay that port-only snow. Autoflush stays off (extra wait = 30Hz). Soft
colour defer at 4096 already parks leftover nibble DMA in the queue.

Usage (from zanac-md):
    python tools/test_vblank_dma_chiado.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "main.c"
ENT = ROOT / "src" / "entity.c"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def main() -> int:
    main_c = MAIN.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")

    if "DMA_setAutoFlush(FALSE)" not in main_c:
        return fail("autoflush on waits a second vblank (30Hz hitch)")
    if "DMA_setMaxTransferSize(0)" in main_c:
        return fail("MaxTransferSize(0) uncapped DMA is the top-fifth chiado")
    m = re.search(r"DMA_setMaxTransferSize\((\d+)\)", main_c)
    if not m:
        return fail("DMA_setMaxTransferSize must be a vblank-safe cap")
    cap = int(m.group(1))
    if cap > 7200:
        return fail("cap %d exceeds SGDK NTSC vblank ~7200 B (still snows)" % cap)
    if cap < 4096:
        return fail("cap %d is below DMA_NIBBLE_SOFT_CAP; SAT/NT would drop" % cap)
    print("  DMA cap %d B (vblank); autoflush off" % cap)

    if "DMA_NIBBLE_SOFT_CAP  4096" not in ent and "DMA_NIBBLE_SOFT_CAP 4096" not in ent:
        return fail("KEEP: colour remap defer at 4096")
    if main_c.count("SYS_doVBlankProcess()") != 1:
        return fail("exactly one wait_one_frame per tick")
    if not re.search(
        r"SPR_update\(\);\s*"
        r"SYS_doVBlankProcess\(\);.*\n"
        r"\s*DMA_flushQueue\(\);",
        main_c,
    ):
        return fail("flush after the wait, still in that vblank")
    print("  KEEP: 60Hz loop; colour defer; flush after wait")
    print("ok: vblank DMA cap; top-fifth chiado cannot be uncapped flush")
    return 0


if __name__ == "__main__":
    sys.exit(main())
