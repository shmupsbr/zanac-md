#!/usr/bin/env python3
"""BULLET VISIBILITY is the only switch for every tiro bolinha.

Filipe after #138/#139 (Easy): horizontals white vs cycling mixed;
red-box 3-volleys coloured; edge-of-screen horizontals coloured;
boss 1 white / boss 2 coloured. Visibility must own ALL of them.

NORMAL = solid white+EC (0x8F / nibble 15), no 8659, no PAL2[4] walk.
HIGH   = 8659 colour-walk on the same types.

Scope (prefer over-including): FRAME_LEAD 20/37/38/41/42/43,
FRAME_LIGHT_BAR 21, type 45 bar/med. Boxes, k_gun, spawners, wide
84-86, base_fire 73-79. Skill / ALC never enter.

This file must FAIL if any bolinha colour-walk can run without HIGH,
and FAIL if any forced-white bolinha path runs without NORMAL.

Usage (from zanac-md):
    python tools/test_bolinha_vis_universal.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
OPT = ROOT / "src" / "options.c"
OPTH = ROOT / "inc" / "options.h"

SKILL = (
    "SKILL_EASY",
    "SKILL_NORMAL",
    "SKILL_HARD",
    "options_skill",
    "options_alc",
    "ALC_HALF",
)
WALK_RE = re.compile(
    r"spr_set_sat_col\s*\(\s*e,\s*\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)"
)
WHITE_RE = re.compile(
    r"(?:(?:e|c|s)->sat_col\s*=\s*0x8F|spr_set_sat_col\s*\(\s*[ecs]\s*,\s*0x8F\s*\))"
)
BOLINHA = ("20", "21", "37", "38", "41", "42", "43", "45")


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


def mentions_skill(body: str) -> bool:
    return any(n in body for n in SKILL)


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    opt = OPT.read_text(encoding="utf-8")
    opth = OPTH.read_text(encoding="utf-8")

    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)")
    if not apply:
        return fail("ebullet_apply_vis must be the single bolinha colour helper")
    if "options_bullet_high" not in apply:
        return fail("ebullet_apply_vis must read BULLET VISIBILITY")
    if mentions_skill(apply):
        return fail("ebullet_apply_vis must not consult skill/ALC")
    if "0x80|(rnd()&0x0F)" not in apply.replace(" ", ""):
        return fail("HIGH must 8659-walk inside ebullet_apply_vis")
    if "spr_set_sat_col(e, 0x8F)" not in apply:
        return fail("NORMAL white must go through spr_set_sat_col (EC + upload)")
    if "ebullet_bolinha" not in apply:
        return fail("apply_vis must classify via ebullet_bolinha (no orphan types)")
    print("  ebullet_apply_vis: HIGH walk / NORMAL 0x8F; vis only")

    boli = fn_span(ent, "static int ebullet_bolinha(const Slot *s)")
    if not boli:
        return fail("ebullet_bolinha must list every tiro bolinha")
    for v in BOLINHA:
        if v not in boli and not (
            v in ("20", "37", "38", "41", "42", "43")
            and "ebullet_lead_disc" in boli
        ):
            return fail("ebullet_bolinha must include type %s" % v)
    if "21" not in boli or "45" not in boli:
        return fail("ebullet_bolinha must include type 21 and type 45")
    if mentions_skill(boli):
        return fail("ebullet_bolinha must not consult skill/ALC")
    print("  ebullet_bolinha: 20/21/37/38/41/42/43/45")

    high = fn_span(ent, "static int ebullet_bolinha_high(const Slot *s)")
    if not high:
        return fail("ebullet_bolinha_high must be the single HIGH gate")
    if "options_bullet_high" not in high:
        return fail("ebullet_bolinha_high must read options_bullet_high")
    if mentions_skill(high):
        return fail("ebullet_bolinha_high must not consult skill/ALC")
    cram = fn_span(ent, "static int ebullet_cram_shot(const Slot *s)")
    if not cram or "ebullet_bolinha_high" not in cram:
        return fail("ebullet_cram_shot must be bolinha_high (PAL2[4] on HIGH only)")
    if mentions_skill(cram or ""):
        return fail("ebullet_cram_shot must not consult skill/ALC")
    print("  HIGH gate: bolinha_high → cram_shot; no skill")

    # Orphan 8659 walks: every R-nibble|0x80 write must live in apply_vis.
    walks = list(WALK_RE.finditer(ent))
    if not walks:
        return fail("no 8659 colour-walk found")
    apply_start = ent.find("static void ebullet_apply_vis")
    apply_body = apply or ""
    for m in walks:
        pos = m.start()
        in_apply = apply_start >= 0 and pos > apply_start and pos < apply_start + 800
        if not in_apply:
            snippet = ent[max(0, pos - 80) : pos + 40].replace("\n", " ")
            return fail("orphan 8659 walk (must only live in ebullet_apply_vis): %s" % snippet)
    if apply_body.count("0x80") < 1:
        return fail("apply_vis must contain the 8659 write")
    print("  no orphan 8659: one walk inside ebullet_apply_vis")

    # Forced-white sat_col=0x8F on ebullet bolinha sites must go through
    # apply_vis, except comments. Scan KIND_EBULLET arming helpers.
    for sig in (
        "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)",
        "static void spawn_ebullet_dir(s16 x, s16 y, u8 dir)",
        "static void spawn_lead20(s16 x, s16 y)",
    ):
        body = fn_span(ent, sig)
        if not body:
            return fail("%s missing" % sig)
        if "ebullet_apply_vis" not in body:
            return fail("%s must arm colour via ebullet_apply_vis" % sig.split("(")[0])
        # Direct 0x8F on the slot is an orphan white path (NORMAL-only
        # belongs inside apply_vis).
        if WHITE_RE.search(body):
            return fail("%s still writes sat_col=0x8F (must use apply_vis)" % sig)
    print("  arming: init_frag / spawn_lead20 / spawn_ebullet_dir → apply_vis")

    # Stream type 20 is a fourth arming path (not init_frag).
    if "ebullet_apply_vis(e)" not in ent.split("else if (t == 20)")[1][:800]:
        return fail("stream type 20 must apply_vis (not a private 0x8F)")
    print("  stream type 20: apply_vis")

    # Per-frame colour arms.
    for sig, tag in (
        ('else if (e->kind == KIND_EBULLET && e->variant == 20)', "type 20"),
        ('else if (e->kind == KIND_EBULLET && e->variant == 41)', "type 41"),
    ):
        idx = ent.find(sig)
        if idx < 0:
            return fail("%s update arm missing" % tag)
        chunk = ent[idx : idx + 1200]
        if "ebullet_apply_vis(e)" not in chunk:
            return fail("%s arm must call ebullet_apply_vis" % tag)
        if WALK_RE.search(chunk):
            return fail("%s arm has an orphan 8659 (must call apply_vis)" % tag)
    group = re.search(
        r"e->variant == 21 \|\| e->variant == 37.*?"
        r"e->variant == 45\).*?"
        r"ebullet_apply_vis\(e\).*?if \(step_88_4898\(e\)\)",
        ent,
        re.S,
    )
    if not group:
        return fail("21/37/38/42/43/45 step must call apply_vis before 4898")
    if "e->variant == 45" not in group.group(0):
        return fail("type 45 must share the 21-group vis step")
    print("  per-frame: type 20 / 41 / 21-group (incl. 45) call apply_vis")

    if "ebullet_apply_vis(e)" not in (
        fn_span(ent, "static void update_enemies(void)") or ""
    ):
        return fail("update_enemies must call apply_vis")
    # init_ret skip must still colour so HIGH has no white flash.
    ret = re.search(
        r"s_ebullet_init_ret\[i\] = 0;\s*\n\s*ebullet_apply_vis\(e\);",
        ent,
    )
    if not ret:
        return fail("init-RET visit must apply_vis (no white orphan frame)")
    print("  init-RET: apply_vis")

    # Spawners of bolinhas: boxes 3x38, guns 21/38, base 21/42/43/45.
    drop = fn_span(ent, "static void box_death_drop(s16 sx, s16 sy)")
    if not drop or drop.count("spawn_frag") < 3 or ", 38)" not in drop:
        return fail("red-box death must still fire three type-38 bolinhas")
    if "spr_set_sat_col" in (drop or ""):
        return fail("box_death_drop must not colour-walk (init_frag owns vis)")
    print("  boxes: 3x type 38 via spawn_frag / init_frag")

    fire = fn_span(ent, "static void base_fire(Slot *e)")
    if not fire:
        return fail("base_fire missing")
    for v in (21, 42, 43, 45, 38):
        if (", %d)" % v) not in fire and (", %d," % v) not in fire:
            # spawn_frag(x, y, dir, 21) etc.
            if (" %d)" % v) not in fire:
                return fail("base_fire must still spawn type %d" % v)
    if "spr_set_sat_col" in fire:
        return fail("base_fire must not colour-walk children (init_frag owns vis)")
    if "base_muzzle" not in fire:
        return fail("base_fire must spawn from the eye muzzle")
    print("  bosses 73-79: types 21/38/42/43/45 via init_frag; no private walk")

    gun = fn_span(ent, "static void spawn_child_dir(s16 x, s16 y, u8 stype, u8 dir)")
    if not gun or "spawn_frag(x, y, dir, 21)" not in gun or "spawn_frag(x, y, dir, 38)" not in gun:
        return fail("k_gun / wide children 21 and 38 must go through spawn_frag")
    print("  guns/wide/edge: type 21 and 38 via spawn_frag")

    # Tile path: HIGH nibble 4, NORMAL nibble 15, including type 45.
    want = fn_span(ent, "static u8 proj_tile_want(const Slot *s)")
    if not want or "ebullet_cram_shot" not in want or "ebullet_bolinha" not in want:
        return fail("proj_tile_want must bank HIGH on 4 / NORMAL bolinha on 15")
    if "return 15" not in want:
        return fail("NORMAL bolinha (incl. 21/45) must bank nibble 15")
    up = fn_span(ent, "static void spr_upload_color(Slot *s)")
    if not up or "ebullet_bolinha" not in up:
        return fail("spr_upload_color must paint_all every bolinha")
    print("  tiles: HIGH PAL2[4]; NORMAL nibble 15 for every bolinha")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")

    if "BULLET_VIS_NORMAL       0" not in opth:
        return fail("NORMAL vis is 0")
    high_fn = fn_span(opt, "u8 options_bullet_high(void)") or ""
    if mentions_skill(high_fn):
        return fail("options_bullet_high must ignore skill")
    print("  KEEP: OPTIONS vis; no VDP_*Tiles; skill never gates colour")
    print("ok: NORMAL all bolinhas white; HIGH all bolinhas cycle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
