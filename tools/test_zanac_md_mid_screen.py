#!/usr/bin/env python3
"""Zanac MD mid-screen duplicate/broken garbage after #159+#160.

Filipe after 94b594b: "Tem coisa saindo duplicada e quebrada no meio
da tela." Root cause was the 24→28 nametable row-dup plus a *224/192
camera: wrap NT skipped plane rows, wrap-1 overwrote live cells.

#161 dropped the Y dup. Filipe after d1af518: scenery still bad.
24→30 whole-tile column dup (every 4th source col twice) plus PAL0
gutter/wrap bars *is* that leftover stretched/repeating map. This
file now locks the scenery path (1:1 centered, sky gutters, 64-wide
plane) together with the Y 1:1 wrap locks.

KEEP: MODE_ORIGINAL 256×192 letterbox + HUD; LEAD_MD_SPEED 4.

Usage (from zanac-md):
    python tools/test_zanac_md_mid_screen.py
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    scenery = ROOT / "tools" / "test_zanac_md_scenery.py"
    ns = runpy.run_path(str(scenery), run_name="not_main")
    return int(ns["main"]())


if __name__ == "__main__":
    sys.exit(main())
