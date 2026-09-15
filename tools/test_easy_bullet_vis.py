#!/usr/bin/env python3
"""Easy + NORMAL vis cannot colour-walk enemy tiros.

#138 gated FRAME_LEAD 20/37/38/41/42/43 on BULLET VISIBILITY, but type 21
(FRAME_LIGHT_BAR) kept Japan 8659 always-on. Easy ALC caps at 0x50; the
BE27 slice at pos 0x1C includes spawn_type_list[0x12] = type 48, whose
k_gun child is type 21. Type-73 base_fire also spawn_frag(..., 21).
Those bars are the Easy "bolinhas" Filipe still saw cycling.

Prove:
  * options_bullet_high / ebullet_lead_high / ebullet_cram_shot / type 21
    8659 never read skill or ALC.
  * k_gun pairs 1/3/4 fire type 21 through spawn_child_dir -> init_frag.
  * Easy-max slice includes those guns.
  * Type 73 base_fire type 21 uses the same init_frag (no private walk).
  * HIGH still has a type 21 8659 write.

Usage (from zanac-md):
    python tools/test_easy_bullet_vis.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
OPT = ROOT / "src" / "options.c"
SPAWN = ROOT / "src" / "data" / "spawn_table.c"
OPTH = ROOT / "inc" / "options.h"


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


SKILL_NAMES = (
    "SKILL_EASY",
    "SKILL_NORMAL",
    "SKILL_HARD",
    "options_skill",
    "options_alc",
    "ALC_HALF",
)


def mentions_skill(body: str) -> bool:
    return any(n in body for n in SKILL_NAMES)


def parse_c_array(src: str, name: str) -> list[int] | None:
    m = re.search(rf"{re.escape(name)}\[[^\]]*\]\s*=\s*\{{([^;]+)\}}", src, re.S)
    if not m:
        return None
    return [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", m.group(1))]


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    opt = OPT.read_text(encoding="utf-8")
    spawn = SPAWN.read_text(encoding="utf-8")
    opth = OPTH.read_text(encoding="utf-8")

    if "ALC_HALF_RANK           0x50" not in opth and "ALC_HALF_RANK  0x50" not in opth:
        return fail("Easy cap must stay ALC_HALF_RANK 0x50")
    if "BULLET_VIS_NORMAL       0" not in opth:
        return fail("NORMAL vis is 0 (white)")
    print("  Easy ALC cap 0x50; BULLET_VIS_NORMAL=0")

    high_fn = fn_span(opt, "u8 options_bullet_high(void)") or ""
    if mentions_skill(high_fn):
        return fail("options_bullet_high must ignore skill (Easy path)")
    if "options_bullet_vis" not in high_fn:
        return fail("options_bullet_high must read s_bullet_vis only")
    print("  options_bullet_high: vis only")

    for sig in (
        "static int ebullet_lead_disc(const Slot *s)",
        "static int ebullet_lead_high(const Slot *s)",
        "static int ebullet_type21(const Slot *s)",
        "static int ebullet_cram_shot(const Slot *s)",
    ):
        body = fn_span(ent, sig)
        if not body:
            return fail("%s missing" % sig.split("(")[0].split()[-1])
        if mentions_skill(body):
            return fail("%s must not consult skill/ALC" % sig)
    print("  colour helpers: no skill/ALC")

    if not re.search(
        r"if \(e->variant == 21 && options_bullet_high\(\)\)\s*\n"
        r"\s*spr_set_sat_col\(\s*e,\s*\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        return fail("type 21 8659 must require options_bullet_high() (Easy cannot bypass)")
    if re.search(
        r"if \(e->variant == 21\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        return fail("ungated type 21 8659 still present (Easy NORMAL would cycle)")
    print("  type 21 8659: HIGH only")

    gun = re.search(r"k_gun\[5\]\[4\]\s*=\s*\{(.*?)\};", ent, re.S)
    if not gun:
        return fail("k_gun table missing")
    rows = re.findall(r"\{\s*([^}]+)\}", gun.group(1))
    if len(rows) < 5:
        return fail("k_gun must have 5 pairs")
    child = [int(r.split(",")[-1].strip(), 0) for r in rows]
    if 21 not in child:
        return fail("k_gun must still fire type 21")
    if child[1] != 21 or child[3] != 21 or child[4] != 21:
        return fail("k_gun pairs 1/3/4 (types 48-49 / 52-55) fire type 21")
    if child[0] != 38 or child[2] != 38:
        return fail("k_gun pairs 0/2 still fire type 38 (lead disc)")
    spawn_child = fn_span(ent, "static void spawn_child_dir(s16 x, s16 y, u8 stype, u8 dir)")
    if not spawn_child or "spawn_frag(x, y, dir, 21)" not in spawn_child:
        return fail("gun type 21 must go through spawn_frag / init_frag")
    print("  k_gun 48/49/52-55 -> type 21 via spawn_frag")

    # BE27: pos = E12E+E132, Easy clamps 0x50. de = (pos>>1)&0x7E.
    # pos 0x1C -> half 0x0E -> pair index 7 -> offset 0x12 count 6.
    pairs = parse_c_array(spawn, "spawn_pair_table")
    types = parse_c_array(spawn, "spawn_type_list")
    if not pairs or not types:
        return fail("spawn_pair_table / spawn_type_list missing")
    pos = 0x1C
    de = ((pos >> 1) & 0x7E)
    off = pairs[de]
    count = pairs[de + 1]
    slice_types = types[off : off + count]
    if 0x30 not in slice_types and 0x31 not in slice_types:
        return fail(
            "Easy-reachable pos 0x1C slice %s must include type 48/49 (0x30/0x31)"
            % [hex(t) for t in slice_types]
        )
    if pos > 0x50:
        return fail("fixture pos 0x1C must be <= Easy cap 0x50")
    print("  Easy pos 0x1C slice includes type 48/49 guns (type 21 child)")

    fire = fn_span(ent, "static void base_fire(Slot *e)")
    if not fire or "spawn_frag(x, y, a, 21)" not in fire:
        return fail("type 73 base_fire must still spawn type 21 via spawn_frag")
    if "spr_set_sat_col" in fire:
        return fail("base_fire must not colour-walk children itself")
    print("  type 73 base_fire type 21: shared init_frag, no private walk")

    if "options_skill" in (fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)") or ""):
        return fail("init_frag must not read skill")
    print("ok: Easy+NORMAL cannot bypass vis; HIGH still 8659s type 21")
    return 0


if __name__ == "__main__":
    sys.exit(main())
