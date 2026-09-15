#!/usr/bin/env python3
"""PLAYER EXTEND: extra-life schedule + matching placar score bonus.

Stock first extra is title_screen_init E111=0, E112=0x20, E113=0 → 2000
in E103 units. HUD 0x49B5 appends a trailing 0, so the placar reads 20000.
That displayed first extra is X.

Primary: extra_life_check / E111-E113 bump / life grants follow the mode
table (every X / 2X / 3X, once, twice, or none).

Secondary: the listed % is added to every score that enters the placar
so extends fire on the inflated total. Default EVERY X = stock lives + 0%.

Filipe bonuses: 2X TWICE = 60%, X TWICE = 50%.

NO EXTENDS also grants a flat 500000 on the visible placar at
player_init (50000 internal; same ×10 as X). The +100% must not
run on that grant.

Usage (from zanac-md):
    python tools/test_player_extend.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPT_C = ROOT / "src" / "options.c"
OPT_H = ROOT / "inc" / "options.h"
PLY = ROOT / "src" / "player.c"
PLY_H = ROOT / "inc" / "player.h"
TITLE = ROOT / "src" / "title.c"

EXTEND_X = 2000
EXTEND_X_DISPLAY = 20000

MODES = {
    "EVERY_X": 0,
    "EVERY_2X": 1,
    "EVERY_3X": 2,
    "X_ONCE": 3,
    "X_TWICE": 4,
    "2X_ONCE": 5,
    "2X_TWICE": 6,
    "3X_ONCE": 7,
    "3X_TWICE": 8,
    "NONE": 9,
}

BONUS = {
    "EVERY_X": 0,
    "EVERY_2X": 20,
    "EVERY_3X": 30,
    "X_ONCE": 60,
    "X_TWICE": 50,
    "2X_ONCE": 80,
    "2X_TWICE": 70,
    "3X_ONCE": 100,
    "3X_TWICE": 90,
    "NONE": 100,
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


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


def bcd_bin(b: int) -> int:
    return ((b >> 4) * 10) + (b & 0x0F)


def daa_add(res: int, half: int, cry: int) -> tuple[int, int]:
    t = res
    if half or ((t & 0x0F) > 9):
        t += 0x06
    c = 0
    if cry or t > 0x99:
        t += 0x60
        c = 1
    return t & 0xFF, c


def bump(e111: int, e112: int, e113: int) -> tuple[int, int, int]:
    if e113 == 0 and e112 == 0x20:
        return e111, 0x60, e113
    raw = e112 + 0x60
    c_add = 1 if raw > 0xFF else 0
    e112, c_daa = daa_add(raw & 0xFF, 0, c_add)
    raw = e113 + c_daa
    c_add = 1 if raw > 0xFF else 0
    h = 1 if ((e113 & 0x0F) + c_daa) > 0x0F else 0
    e113, _ = daa_add(raw & 0xFF, h, c_add)
    return e111, e112, e113


def stock_thresh(e111: int, e112: int, e113: int) -> int:
    return bcd_bin(e111) + bcd_bin(e112) * 100 + bcd_bin(e113) * 10000


def stock_sequence(n: int) -> list[int]:
    e111, e112, e113 = 0, 0x20, 0
    out = []
    for _ in range(n):
        out.append(stock_thresh(e111, e112, e113))
        e111, e112, e113 = bump(e111, e112, e113)
    return out


def apply_bonus(pts: int, pct: int) -> int:
    return pts + pts * pct // 100


def next_threshold(mode: str, stock: int, grants: int) -> int:
    x = EXTEND_X
    if mode == "EVERY_X":
        return stock
    if mode == "EVERY_2X":
        return stock * 2
    if mode == "EVERY_3X":
        return stock * 3
    if mode == "X_ONCE":
        return 0 if grants >= 1 else x
    if mode == "X_TWICE":
        return 0 if grants >= 2 else x * (grants + 1)
    if mode == "2X_ONCE":
        return 0 if grants >= 1 else x * 2
    if mode == "2X_TWICE":
        return 0 if grants >= 2 else (x * 2) * (grants + 1)
    if mode == "3X_ONCE":
        return 0 if grants >= 1 else x * 3
    if mode == "3X_TWICE":
        return 0 if grants >= 2 else (x * 3) * (grants + 1)
    return 0


def grants_at_score(mode: str, score: int, limit: int = 16) -> int:
    """How many extras fire by `score` (E103 units)."""
    e111, e112, e113 = 0, 0x20, 0
    grants = 0
    recurring = mode in ("EVERY_X", "EVERY_2X", "EVERY_3X")
    for _ in range(limit):
        stock = stock_thresh(e111, e112, e113)
        used = 0 if recurring else grants
        thresh = next_threshold(mode, stock, used)
        if not thresh or score < thresh:
            return grants
        if recurring:
            e111, e112, e113 = bump(e111, e112, e113)
        grants += 1
    return grants


def main() -> int:
    fails = 0
    opt_c = OPT_C.read_text(encoding="utf-8")
    opt_h = OPT_H.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")
    ply_h = PLY_H.read_text(encoding="utf-8")
    title = TITLE.read_text(encoding="utf-8")

    if "#define EXTEND_X_POINTS         2000UL" not in opt_h:
        fail("EXTEND_X_POINTS must be 2000 (E112=0x20)")
        fails += 1
    if "#define EXTEND_X_DISPLAY        20000UL" not in opt_h:
        fail("EXTEND_X_DISPLAY must be 20000 (HUD trailing 0)")
        fails += 1
    else:
        print("  X = 2000 internal / 20000 placar")

    seq = stock_sequence(5)
    if seq != [2000, 6000, 12000, 18000, 24000]:
        fail(f"stock E111-E113 sequence {seq} want [2000, 6000, 12000, 18000, 24000]")
        fails += 1
    else:
        print("  stock bump: 2000, 6000, 12000, 18000, 24000")

    # Recurring: 2× / 3× the stock sequence
    if [t * 2 for t in seq] != [4000, 12000, 24000, 36000, 48000]:
        fail("EVERY 2X must be 2× stock thresholds")
        fails += 1
    if grants_at_score("EVERY_X", 1999) != 0 or grants_at_score("EVERY_X", 2000) != 1:
        fail("EVERY X must grant at 2000 (stock)")
        fails += 1
    if grants_at_score("EVERY_X", 6000) != 2:
        fail("EVERY X must grant again at 6000 (stock bump 0x20→0x60)")
        fails += 1
    if grants_at_score("EVERY_2X", 3999) != 0 or grants_at_score("EVERY_2X", 4000) != 1:
        fail("EVERY 2X must grant first at 4000")
        fails += 1
    if grants_at_score("EVERY_2X", 11999) != 1 or grants_at_score("EVERY_2X", 12000) != 2:
        fail("EVERY 2X second grant is 2×6000 = 12000")
        fails += 1
    if grants_at_score("EVERY_3X", 6000) != 1 or grants_at_score("EVERY_3X", 17999) != 1:
        fail("EVERY 3X first grant at 6000, not again before 18000")
        fails += 1
    print("  recurring: EVERY X stock; 2X/3X scale the stock sequence")

    # Finite
    if grants_at_score("X_ONCE", 2000) != 1 or grants_at_score("X_ONCE", 999999) != 1:
        fail("X ONCE must grant only at 2000")
        fails += 1
    if grants_at_score("X_TWICE", 2000) != 1 or grants_at_score("X_TWICE", 4000) != 2:
        fail("X TWICE must grant at 2000 and 4000")
        fails += 1
    if grants_at_score("X_TWICE", 999999) != 2:
        fail("X TWICE must not keep granting after 2X")
        fails += 1
    if grants_at_score("2X_ONCE", 2000) != 0 or grants_at_score("2X_ONCE", 4000) != 1:
        fail("2X ONCE must grant only at 4000")
        fails += 1
    if grants_at_score("2X_TWICE", 4000) != 1 or grants_at_score("2X_TWICE", 8000) != 2:
        fail("2X TWICE must grant at 4000 and 8000")
        fails += 1
    if grants_at_score("3X_ONCE", 6000) != 1 or grants_at_score("3X_ONCE", 999999) != 1:
        fail("3X ONCE must grant only at 6000")
        fails += 1
    if grants_at_score("3X_TWICE", 6000) != 1 or grants_at_score("3X_TWICE", 12000) != 2:
        fail("3X TWICE must grant at 6000 and 12000")
        fails += 1
    if grants_at_score("NONE", 999999) != 0:
        fail("NO EXTENDS must never grant")
        fails += 1
    print("  finite: ONCE/TWICE at aX / 2·aX; NONE = 0")

    # Score bonuses (Filipe): ONCE > TWICE at each tier
    if apply_bonus(200, 0) != 200:
        fail("EVERY X must add +0%")
        fails += 1
    if apply_bonus(200, 20) != 240:
        fail("EVERY 2X +20% of 200 → 240")
        fails += 1
    if apply_bonus(200, 100) != 400:
        fail("NO EXTENDS +100% of 200 → 400")
        fails += 1
    if apply_bonus(17, 60) != 17 + 10:
        fail("X ONCE +60% of 17 → 27")
        fails += 1
    if BONUS["2X_ONCE"] != 80 or BONUS["2X_TWICE"] != 70:
        fail("2X ONCE +80%; 2X TWICE +70% (ONCE > TWICE)")
        fails += 1
    if BONUS["3X_ONCE"] != 100 or BONUS["3X_TWICE"] != 90:
        fail("3X ONCE +100%; 3X TWICE +90% (ONCE > TWICE)")
        fails += 1
    if BONUS["X_ONCE"] != 60 or BONUS["X_TWICE"] != 50:
        fail("X ONCE +60%; X TWICE +50% (ONCE > TWICE)")
        fails += 1
    print("  score %: ONCE > TWICE at each tier; NONE +100")

    # C locks
    if "s_extend = EXTEND_EVERY_X" not in opt_c:
        fail("default extend must be EVERY X")
        fails += 1
    m = re.search(r"k_extend_bonus\[10\]\s*=\s*\{([^}]+)\}", opt_c)
    if not m:
        fail("k_extend_bonus[10] missing")
        fails += 1
    else:
        nums = [int(x.strip().split(",")[0]) for x in re.findall(r"\d+", m.group(1))]
        want = [BONUS[k] for k in (
            "EVERY_X", "EVERY_2X", "EVERY_3X", "X_ONCE", "X_TWICE",
            "2X_ONCE", "2X_TWICE", "3X_ONCE", "3X_TWICE", "NONE",
        )]
        if nums[:10] != want:
            fail(f"k_extend_bonus {nums[:10]} want {want}")
            fails += 1
        else:
            print("  k_extend_bonus: Filipe table")

    thr = fn_span(opt_c, "u32 options_extend_threshold(u32 stock_thresh, u8 grants)") or ""
    if "stock_thresh * 2UL" not in thr or "stock_thresh * 3UL" not in thr:
        fail("EVERY 2X/3X must scale the stock E111-E113 threshold")
        fails += 1
    if "EXTEND_NONE" not in thr:
        fail("NO EXTENDS must return no further threshold")
        fails += 1
    else:
        print("  options_extend_threshold: stock scale + finite + none")

    extra = fn_span(ply, "static void extra_life_check(void)") or ""
    if "options_extend_threshold" not in extra:
        fail("extra_life_check must use the EXTEND schedule")
        fails += 1
    if "options_extend_uses_stock_bump" not in extra:
        fail("extra_life_check must bump E111-E113 only on EVERY nX")
        fails += 1
    if "s_extend_grants" not in extra:
        fail("finite modes must count grants (ONCE/TWICE)")
        fails += 1
    if "bump_extra_life_threshold" not in extra:
        fail("stock bump 0x20→0x60 / +0x60 DAA must stay")
        fails += 1
    else:
        print("  extra_life_check: schedule + stock bump / grant count")

    add = fn_span(ply, "static void add_points(u32 pts)") or ""
    if "options_apply_score_bonus" not in add:
        fail("every placar add must apply the extend score %")
        fails += 1
    if "extra_life_check" not in add:
        fail("extends must fire on the inflated placar")
        fails += 1
    else:
        print("  add_points: extend % then extra_life_check")

    init = fn_span(ply, "void player_init(void)") or ""
    if "s_e112 = 0x20" not in init:
        fail("player_init must still seed E112=0x20")
        fails += 1
    if "s_extend_grants = 0" not in init:
        fail("player_init must reset finite-mode grants")
        fails += 1
    if "EXTEND_NONE" not in init or "EXTEND_NONE_START" not in init:
        fail("NO EXTENDS must grant EXTEND_NONE_START at player_init")
        fails += 1
    if re.search(r"options_apply_score_bonus\s*\(", init):
        fail("the 500000 displayed start grant must stay flat (not +100% again)")
        fails += 1
    if "EXTEND_NONE_START_DISPLAY" in init:
        fail("player_init must add EXTEND_NONE_START (internal), not DISPLAY")
        fails += 1
    else:
        print("  player_init: E112=0x20, grants=0, NO EXTENDS flat 50000 internal")

    if "#define EXTEND_NONE_START         50000UL" not in opt_h:
        fail("EXTEND_NONE_START must be 50000 internal (500000 on HUD)")
        fails += 1
    if "#define EXTEND_NONE_START_DISPLAY 500000UL" not in opt_h:
        fail("EXTEND_NONE_START_DISPLAY must be 500000 (visible placar)")
        fails += 1
    else:
        print("  EXTEND_NONE_START = 50000 internal / 500000 placar")

    if "options_nudge_extend" not in title:
        fail("title OPTIONS must Left/Right PLAYER EXTEND")
        fails += 1
    if '"PLAYER EXTEND"' not in title or '"EVERY 20000"' not in title:
        fail("OPTIONS must show PLAYER EXTEND / EVERY 20000")
        fails += 1
    if '"NONE +500000"' not in title and '"NO EXTENDS"' not in title:
        fail("OPTIONS must show the NO EXTENDS / +500000 start grant")
        fails += 1
    else:
        print("  title: PLAYER EXTEND row, X shown as 20000")

    if "s_skill = SKILL_NORMAL" not in opt_c or "s_extend = EXTEND_EVERY_X" not in opt_c:
        fail("defaults must stay Normal + EVERY X")
        fails += 1
    else:
        print("  defaults: Normal + EVERY X → stock lives + 0% score")

    if "PLAYER_LIVES_INIT   3" not in ply_h:
        fail("KEEP: default ships 3")
        fails += 1

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
