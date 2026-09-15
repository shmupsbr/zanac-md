#!/usr/bin/env python3
"""#146 had zero playtest effect. Isolate FRAME_LEAD from type 21.

Filipe after #146 merge+rebuild (tip 35cadf8): "Não mudou nada."
Box / boss bolinhas still colour-cycled under BULLET VISIBILITY=NORMAL.

Why #146 was invisible:
  * options_bullet_high() is correctly false when the menu shows NORMAL
    (default 0, skill never writes vis). Box/boss shots ARE ebullet_bolinha
    38/42 and do hit ebullet_apply_vis every tick.
  * SGDK packs FRAME_LEAD as nibble 4. Type 21 8659 walked PAL2[4].
  * leave_white only matched painted-15 for the *same frame*, so a reused
    FRAME_LIGHT_BAR sprite painted 4 into the shared white disc index.
    Packed-4 discs then rode type 21's CRAM walk. Share-before-paint and
    xor_cram on leftover cram_nib were the same leak class.

Nuclear lock:
  * Type 21 CRAM is a dedicated nibble, not 4, not 15, not fire 13, not XOR 2.
  * NORMAL never shares FRAME_LEAD with any bank type 21 can touch.
  * White discs DMA from a RAM paint_all-15 cache (one blit, keep speed).
  * ebullet_8659 refuses ebullet_normal_lock; apply_vis NORMAL has no rnd.
  * Type 21 always 8659s; HIGH bolinhas still 8659.

Usage (from zanac-md):
    python tools/test_bolinha_type21_isolated.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
OPT = ROOT / "src" / "options.c"
OPTH = ROOT / "inc" / "options.h"
TITLE = ROOT / "src" / "title.c"
GAME = ROOT / "src" / "game.c"

WALK_RE = re.compile(
    r"spr_set_sat_col\s*\(\s*e,\s*\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)"
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
    opt = OPT.read_text(encoding="utf-8")
    opth = OPTH.read_text(encoding="utf-8")
    title = TITLE.read_text(encoding="utf-8")
    game = GAME.read_text(encoding="utf-8")

    # 1. Menu NORMAL <=> options_bullet_high false. Default, no overwrite.
    if "s_bullet_vis = BULLET_VIS_NORMAL" not in opt:
        return fail("s_bullet_vis must default NORMAL (0)")
    high = fn_span(opt, "u8 options_bullet_high(void)") or ""
    if "BULLET_VIS_HIGH" not in high:
        return fail("options_bullet_high is vis == HIGH")
    if "s_skill" in high or "options_skill" in high:
        return fail("options_bullet_high must ignore skill")
    nudge_sk = fn_span(opt, "void options_nudge_skill(s8 dir)") or ""
    if "s_bullet_vis" in nudge_sk:
        return fail("skill nudge must not write visibility")
    if "s_bullet_vis" in game or "options_nudge_bullet_vis" in game:
        return fail("game_start must not overwrite BULLET VISIBILITY")
    if not re.search(r'k_bvis\[2\]\s*=\s*\{\s*"NORMAL",\s*"HIGH"\s*\}', title):
        return fail("title k_bvis[0] must be NORMAL matching BULLET_VIS_NORMAL=0")
    if title.count("options_nudge_bullet_vis") != 1:
        return fail("only OPTIONS left/right on row 5 may nudge vis")
    print("  menu: NORMAL default; skill/game_start cannot force HIGH")

    # 2. Box/boss shots are bolinha 38/42 and hit apply_vis.
    boli = fn_span(ent, "static int ebullet_bolinha(const Slot *s)") or ""
    lead = fn_span(ent, "static int ebullet_lead_disc(const Slot *s)") or ""
    if "38" not in lead or "42" not in lead:
        return fail("box type 38 / boss type 42 must be ebullet_lead_disc")
    if "ebullet_lead_disc" not in boli:
        return fail("ebullet_bolinha must include lead discs")
    drop = fn_span(ent, "static void box_death_drop(s16 sx, s16 sy)") or ""
    if drop.count("spawn_frag") < 3 or ", 38)" not in drop:
        return fail("boxes still 3x type 38")
    fire = fn_span(ent, "static void base_fire(Slot *e)") or ""
    if "spawn_frag(x, y, 0, 42)" not in fire:
        return fail("boss 2 still type 42 FRAME_LEAD")
    if "spawn_frag(x, y, a, 21)" not in fire:
        return fail("boss 1 still type 21 <===>")
    group = re.search(
        r"e->variant == 21 \|\| e->variant == 37.*?e->variant == 45\).*?"
        r"ebullet_apply_vis\(e\)",
        ent,
        re.S,
    )
    if not group or "38" not in group.group(0) or "42" not in group.group(0):
        return fail("type 38/42 step must call apply_vis every tick")
    print("  box 38 / boss 42: bolinha + apply_vis every tick")

    # 3. Type 21 CRAM off packed nibble 4 and off white 15.
    if not re.search(r"#define\s+LEAD_PACKED_NIB\s+4", ent):
        return fail("LEAD_PACKED_NIB must be SGDK FRAME_LEAD 4")
    if not re.search(r"#define\s+LEAD_WHITE_NIB\s+15", ent):
        return fail("LEAD_WHITE_NIB must be Japan 0x8F / 15")
    if not re.search(r"#define\s+TYPE21_CRAM_NIB\s+3", ent):
        return fail("TYPE21_CRAM_NIB must be dedicated 3")
    if re.search(r"#define\s+LIGHTBAR_CRAM_NIB\s+4\b", ent):
        return fail("LIGHTBAR_CRAM_NIB must not be packed lead 4")
    if "type21_cram_not_packed" not in ent or "type21_cram_not_white" not in ent:
        return fail("C89 static asserts: type 21 nibble != 4 and != 15")
    print("  CRAM: type 21 nibble 3; packed lead 4; white 15 — isolated")

    # 4. leave_white is any-index, not same-frame. No FRAME_LEAD share with 21.
    leave = fn_span(ent, "static int shot_vram_leave_white(Sprite *sp, u8 nib)") or ""
    if not leave:
        return fail("leave_white must not take a frame (that was the #146 hole)")
    if "shot_bank_index_is_white" not in leave:
        return fail("leave_white must match any-frame painted-15")
    if "shot_bank_index_is_lead" not in leave:
        return fail("leave_white must leave any FRAME_LEAD bank")
    prep = fn_span(ent, "static int shot_vram_prepare(Slot *s, u8 want, u8 ntiles)") or ""
    if "shot_bank_index_is_lead" not in prep:
        return fail("type 21 / HIGH prepare must refuse a FRAME_LEAD index")
    print("  share: NORMAL FRAME_LEAD never sits in a type 21 bank")

    # 5. RAM paint_all-15 cache: blit, not per-pixel rebuild.
    buf = fn_span(ent, "static const u8 *lead_white_buf(const u8 *src, u16 nbytes)") or ""
    if not buf or "orb_paint_body_nibbles" not in buf:
        return fail("lead_white_buf must paint_all-15 once into RAM")
    if "s_lead_white_ok" not in buf:
        return fail("lead_white_buf must cache; later DMA is a blit")
    up = fn_span(ent, "static void spr_upload_color(Slot *s)") or ""
    if "lead_white_buf" not in up:
        return fail("NORMAL FRAME_LEAD DMA must blit the RAM white cache")
    print("  speed: white FRAME_LEAD DMA is one RAM blit")

    # 6. Assertion: NORMAL cannot rnd-walk bolinha; type 21 can.
    walk = fn_span(ent, "static void ebullet_8659(Slot *e)") or ""
    if not walk:
        return fail("ebullet_8659 missing")
    if "ebullet_normal_lock" not in walk or "0x8F" not in walk:
        return fail("ebullet_8659 must refuse NORMAL lock")
    if "0x80|(rnd()&0x0F)" not in walk.replace(" ", ""):
        return fail("ebullet_8659 must rnd-walk when not NORMAL bolinha")
    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)") or ""
    if "rnd(" in apply:
        return fail("apply_vis must not call rnd (NORMAL cannot colour-walk)")
    if apply.count("ebullet_8659") < 2:
        return fail("type 21 and HIGH must call ebullet_8659")
    walks = list(WALK_RE.finditer(ent))
    if not walks:
        return fail("no 8659 rnd walk")
    start = ent.find("static void ebullet_8659")
    for m in walks:
        if m.start() < start or m.start() > start + 500:
            return fail("orphan rnd colour-walk outside ebullet_8659")
    print("  assert: NORMAL cannot rnd-walk bolinha; type 21 can")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")
    if "base_muzzle" not in fire:
        return fail("do not touch boss eye muzzle")
    print("  KEEP: no VDP_*Tiles; eye muzzle; skill unused")

    print("ok: NORMAL FRAME_LEAD cannot cycle with type 21; white at speed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
