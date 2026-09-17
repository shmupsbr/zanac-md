#!/usr/bin/env python3
"""Red flying box (type 4) 3-shot volley is white under NORMAL vis.

Filipe after #143: bosses looked fixed; red caixinhas×3 still colour-
cycled. Blue=powerup (type 6), yellow=empty (type 5), red=3 shots
(type 4 → 3× type 38 FRAME_LEAD).

Japan v1 (zanac-re):
  7860 last-HP: type4 0x89 / type5 0x8A / else 0x87
  7878 CP 4 / JR Z,788f → in-place type 38 + two 8ddb
  8513 type 38 CALL 8507: +04=0x8F (no 8659)

#143 owned NEW sprites after spr_place. Box death runs during collide
(after update_enemies) via free_enemy, which reuses leftover crate /
flyer SAT. setAnimAndFrame then ORs NEED_TILES_UPLOAD if
AUTO_TILE_UPLOAD is still on; SPR_update loadTiles packed nibble 4
onto PAL2[4] and later ticks skipped paint_all because vram_nib==15.

This file FAILS unless:
  * type 4 death still fires 3× type 38 through init_frag
  * init_frag owns leftover SAT before KIND_EBULLET
  * spr_place reuse arm drops AUTO_TILE_UPLOAD / owns after place
  * spr_upload_color does not skip paint_all under NORMAL lock
  * spr_sync_proj owns every visible NORMAL tick
  * every boss 73-79 still fires via spawn_frag (no private walk)
  * skill never enters the colour path
  * HIGH still 8659-walks inside apply_vis
  * base_muzzle / eye centre untouched
  * no VDP_allocateTiles

Usage (from zanac-md):
    python tools/test_box_red_volley_white.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
OPTH = ROOT / "inc" / "options.h"
OPT = ROOT / "src" / "options.c"

SKILL = (
    "SKILL_EASY",
    "SKILL_NORMAL",
    "SKILL_HARD",
    "options_skill",
    "options_alc",
    "ALC_HALF",
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


def mentions_skill(body: str) -> bool:
    return any(n in body for n in SKILL)


def reuse_arm(place: str) -> str:
    if "if (!s->spr)" not in place:
        return ""
    rest = place.split("if (!s->spr)", 1)[1]
    if "\n    else\n    {" not in rest:
        return ""
    return rest.split("\n    else\n    {", 1)[1]


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    opth = OPTH.read_text(encoding="utf-8")
    opt = OPT.read_text(encoding="utf-8")

    if "BULLET_VIS_NORMAL       0" not in opth:
        return fail("NORMAL vis is 0")
    high_fn = fn_span(opt, "u8 options_bullet_high(void)") or ""
    if mentions_skill(high_fn):
        return fail("options_bullet_high must ignore skill")
    print("  OPTIONS: NORMAL=0; HIGH ignores skill")

    # Type 4 = red 3-shot. last-HP 7860 0x89. Death 788f 3x38.
    last = re.search(
        r"if \(e->kind == KIND_BOX && e->hp == 1\)\s*\{(.*?)return;",
        ent,
        re.S,
    )
    if not last:
        return fail("last-HP 7860 box colour missing")
    body = last.group(1)
    if "e->variant == 4" not in body or "0x89" not in body:
        return fail("type 4 last-HP must stay 0x89 (red crate, not the volley)")
    if "e->variant == 5" not in body or "0x8A" not in body:
        return fail("type 5 last-HP must stay 0x8A (yellow empty)")
    if "0x87" not in body:
        return fail("type 6 last-HP must stay 0x87 (blue chip)")
    print("  7860: type4 red 0x89 / type5 yellow 0x8A / type6 blue 0x87")

    kill = fn_span(ent, "static void box_kill_7878(Slot *e)") or ""
    if "drop == 4" not in kill or "box_death_drop" not in kill:
        return fail("type 4 red-box death must box_death_drop")
    if "drop == 5" not in kill or "become_expl" not in kill:
        return fail("type 5 yellow must still become_expl")
    if "become_chip" not in kill:
        return fail("type 6 blue must still become_chip")
    if "spr_detach" not in kill:
        return fail("type 4 must drop crate SAT before the 3x38 volley")
    if "e->sat_col = 0" not in kill:
        return fail("type 4 must wipe leftover 7860 red before 3x38")
    print("  7878: type4→3x38 / type5 expl / type6 chip; crate SAT dropped")

    drop = fn_span(ent, "static void box_death_drop(s16 sx, s16 sy)") or ""
    if drop.count("spawn_frag(") != 3 or drop.count(", 38)") != 3:
        return fail("red box volley must be three spawn_frag(..., 38)")
    if "spr_set_sat_col" in drop or "0x80" in drop:
        return fail("box_death_drop must not private-walk colour")
    if mentions_skill(drop):
        return fail("box_death_drop must not consult skill")
    print("  788f: 3× type 38 via spawn_frag (dirs 3/5/4)")

    initf = fn_span(
        ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)"
    ) or ""
    kind_at = initf.find("e->kind = KIND_EBULLET")
    own_at = initf.find("shot_vram_own")
    rel_at = initf.find("xor_cram_release")
    if kind_at < 0 or rel_at < 0 or rel_at > kind_at:
        return fail("init_frag must xor_cram_release leftover before KIND_EBULLET")
    if own_at < 0 or own_at > kind_at:
        return fail("init_frag must shot_vram_own leftover crate SAT before KIND_EBULLET")
    if "ebullet_apply_vis" not in initf:
        return fail("type 38 volley colour must go through ebullet_apply_vis")
    if mentions_skill(initf):
        return fail("init_frag must not consult skill")
    print("  init_frag: leftover SAT owned; apply_vis; no skill")

    place = fn_span(ent, "static void spr_place(Slot *s, u16 frame)") or ""
    reuse = reuse_arm(place)
    if not reuse:
        return fail("spr_place reuse arm missing")
    if "SPR_FLAG_AUTO_TILE_UPLOAD" not in reuse:
        return fail("reuse arm must drop AUTO_TILE_UPLOAD (packed nibble 4)")
    anim = reuse.find("SPR_setAnimAndFrame")
    own1 = reuse.find("shot_vram_own")
    if anim < 0 or own1 < 0 or own1 < anim:
        return fail("reuse arm must shot_vram_own AFTER setAnimAndFrame")
    if reuse.count("shot_vram_own") < 2:
        return fail("reuse arm must own after setAnimAndFrame and after upload")
    if mentions_skill(place):
        return fail("spr_place must not consult skill")
    print("  spr_place reuse: #143 own-after (box×3 crate leftover)")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)") or ""
    skip = re.search(
        r"if\s*\(\s*s->vram_fr\s*==\s*s->frame\s*&&\s*s->vram_nib\s*==\s*want"
        r"[\s\S]{0,80}?\)\s*return;",
        up,
    )
    if not skip:
        return fail("matching (frame,nibble) skip missing")
    if "ebullet_normal_lock" in skip.group(0):
        return fail("do not paint_all every tick under NORMAL (3+ volley slowdown)")
    if "shot_vram_white_proven" not in up:
        return fail("box×3 skip must sit on paint_all-15, not packed nibble 4")
    print("  spr_upload_color: matching skip; proven white bank holds")

    sync = fn_span(ent, "static void spr_sync_proj(Slot *s)") or ""
    if "ebullet_normal_lock" not in sync or "shot_vram_own" not in sync:
        return fail("spr_sync_proj must own tiles every visible NORMAL tick")
    if mentions_skill(sync):
        return fail("spr_sync_proj must not consult skill")
    print("  spr_sync_proj: last chance own before SPR_update")

    # Per-frame type 38 (the volley) still apply_vis.
    group = re.search(
        r"e->variant == 21 \|\| e->variant == 37.*?e->variant == 45\).*?"
        r"ebullet_apply_vis\(e\)",
        ent,
        re.S,
    )
    if not group or "e->variant == 38" not in group.group(0):
        return fail("type 38 armed step must call apply_vis (volley colour every frame)")
    print("  type 38 step: apply_vis every frame")

    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)") or ""
    if "options_bullet_high" not in apply:
        return fail("apply_vis must read BULLET VISIBILITY")
    if "ebullet_8659" not in apply:
        return fail("HIGH must still 8659-walk")
    walk = fn_span(ent, "static void ebullet_8659(Slot *e)") or ""
    if "0x80|(rnd()&0x0F)" not in walk.replace(" ", ""):
        return fail("HIGH must still 8659-walk")
    if "spr_set_sat_col(e, 0x8F)" not in apply:
        return fail("NORMAL must request 0x8F")
    if mentions_skill(apply):
        return fail("apply_vis must not consult skill")
    print("  apply_vis: HIGH cycle / NORMAL 0x8F; vis only")

    fire = fn_span(ent, "static void base_fire(Slot *e)") or ""
    if not fire:
        return fail("base_fire missing")
    for n in (73, 74, 75, 76, 77, 78, 79):
        if ("e->variant == %d" % n) not in fire:
            return fail("base_fire must handle boss type %d" % n)
    for v in (21, 38, 42, 43, 45):
        if (" %d)" % v) not in fire:
            return fail("bosses must still spawn type %d via spawn_frag" % v)
    if "spr_set_sat_col" in fire:
        return fail("base_fire must not colour-walk children")
    if "base_muzzle" not in fire:
        return fail("do not break eye muzzle")
    if mentions_skill(fire):
        return fail("base_fire must not consult skill")
    print("  bosses 73-79: 21/38/42/43/45 via init_frag; muzzle kept")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")

    print("ok: NORMAL red-box×3 white; bosses white discs; type 21 cycles; HIGH discs cycle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
