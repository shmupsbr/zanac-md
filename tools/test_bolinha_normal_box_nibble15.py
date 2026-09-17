#!/usr/bin/env python3
"""#147 still colour-cycled box×3. NORMAL discs must be nibble 15 only.

Filipe after #147 merge+rebuild (tip bd98d3d): a caixinha (type 4)
bolinha still walked red → yellow → green. Two others existed; shot 7
erased. BULLET VISIBILITY = NORMAL. Type 21 CRAM was already PAL2[3].

Why #147 was still visible:
  * SHOT_BANK_N=12 can miss a painted FRAME_LEAD index (full, or first
    apply_vis uploading leftover crate/type21 as (oldframe,15)).
  * leave_white only saw indices recorded in that bank.
  * Type 21 spr_upload ignored prepare and DMA'd nibble 3 into the
    untagged disc. fire7_paint_cram_tiles never left white (PAL2[13]).
  * One of three discs sat on a walked nibble; the others stayed white.

Nuclear lock this file FAILS unless:
  * Dedicated never-evicted white VRAM lock (not the 12-slot bank).
  * lead_white_buf + NORMAL upload keep_body so only nibble 15 remains.
  * pal2_write refuses to walk PAL2[15] (restore-to-white only).
  * fire7 / xor / type 21 leave locked white before DMA.
  * init_frag detaches leftover SAT under NORMAL (box crate reuse).
  * spr_set_sat_col does not upload a leftover non-bolinha frame.
  * Type 21 still 8659s; HIGH discs still 8659; speed 3; no VDP_*Tiles.

Usage (from zanac-md):
    python tools/test_bolinha_normal_box_nibble15.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
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


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    opth = OPTH.read_text(encoding="utf-8")

    if not re.search(r"#define\s+LEAD_WHITE_NIB\s+15", ent):
        return fail("LEAD_WHITE_NIB must stay 15")
    if not re.search(r"#define\s+TYPE21_CRAM_NIB\s+3", ent):
        return fail("TYPE21_CRAM_NIB must stay 3 (not 15, not packed 4)")
    if "type21_cram_not_white" not in ent or "fire7_cram_not_white" not in ent:
        return fail("C89 asserts: type 21 / fire 7 must not be nibble 15")
    print("  nibbles: white 15; type 21 = 3; fire 7 != 15")

    if "WHITE_LOCK_N" not in ent or "s_white_lock" not in ent:
        return fail("never-evicted white VRAM lock missing")
    add = fn_span(ent, "static void white_lock_add(u8 frame, u16 idx)") or ""
    has = fn_span(ent, "static int white_lock_has_idx(u16 idx)") or ""
    look = fn_span(ent, "static int white_lock_lookup(u8 frame, u16 *out)") or ""
    if not add or not has or not look:
        return fail("white_lock add/has/lookup missing")
    print("  white_lock: never-evicted (frame, index)")

    leave = fn_span(ent, "static int shot_vram_leave_white(Sprite *sp, u8 nib)") or ""
    if "white_lock_has_idx" not in leave:
        return fail("leave_white must leave a locked white index (bank can miss)")
    prep = fn_span(ent, "static int shot_vram_prepare(Slot *s, u8 want, u8 ntiles)") or ""
    arm = prep.split("ebullet_normal_lock")[1][:900] if "ebullet_normal_lock" in prep else ""
    if "white_lock_lookup" not in arm:
        return fail("NORMAL prepare must share the locked white index first")
    if "white_lock_has_idx" not in prep:
        return fail("type 21 / HIGH prepare must refuse a locked white index")
    rem = fn_span(ent, "static void shot_vram_remember(Slot *s, u8 want, u8 ntiles, u8 painted)") or ""
    if "white_lock_has_idx" not in rem or "LEAD_WHITE_NIB" not in rem:
        return fail("remember must not alias a cycling nibble onto locked white")
    print("  share: lock first; type 21 / fire cannot sit on it")

    buf = fn_span(ent, "static const u8 *lead_white_buf(const u8 *src, u16 nbytes)") or ""
    if "orb_paint_body_nibbles" not in buf or "orb_keep_body_nibbles" not in buf:
        return fail("lead_white_buf must paint_all-15 AND drop non-15 leftover")
    up = fn_span(ent, "static void spr_upload_color(Slot *s)") or ""
    if "s_white_only" not in up or "orb_keep_body_nibbles" not in up:
        return fail("NORMAL upload must keep_body nibble 15 only")
    if "white_lock_add" not in up:
        return fail("NORMAL paint_all-15 must lock the VRAM index")
    print("  pixels: only nibble 15 (keep_body); index locked")

    pal = fn_span(ent, "static void pal2_write(u8 nib, u16 color)") or ""
    if not pal:
        return fail("pal2_write missing")
    if "LEAD_WHITE_NIB" not in pal or "k_tms_vdp[LEAD_WHITE_NIB]" not in pal:
        return fail("pal2_write must force PAL2[15] to TMS white")
    # Walkers must not PAL_setColor PAL2+n themselves (15 is locked).
    outside_pal2 = ent
    pal_fn = fn_span(ent, "static void pal2_write(u8 nib, u16 color)") or ""
    if pal_fn:
        outside_pal2 = ent.replace(pal_fn, "")
    if re.search(
        r"PAL_setColor\s*\(\s*\(u16\)\s*\(\s*\(PAL2\s*\*\s*16\)\s*\+\s*"
        r"(LEAD_WHITE_NIB|15)\b",
        outside_pal2,
    ):
        return fail("direct PAL_setColor PAL2[15] outside pal2_write")
    if re.search(
        r"PAL_setColor\s*\(\s*\(u16\)\s*\(\s*\(PAL2\s*\*\s*16\)\s*\+\s*"
        r"(s->cram_nib|nib|FIRE7_CRAM_NIB|LIGHTBAR_CRAM_NIB)",
        outside_pal2,
    ):
        return fail("xor/fire/type21 must pal2_write, not raw PAL_setColor PAL2+n")
    for sig in (
        "static void fire7_bind_cram(Slot *f)",
        "static void fire7_cycle_cram(Slot *f)",
        "static int xor_cram_bind(Slot *s, u8 col)",
        "static void xor_cram_cycle(Slot *s, u8 col)",
    ):
        body = fn_span(ent, sig) or ""
        if "pal2_write" not in body:
            return fail("%s must pal2_write (cannot walk 15)" % sig.split()[-1])
    print("  PAL2[15]: pal2_write lock; walkers cannot tint discs")

    fire7 = fn_span(ent, "static void fire7_paint_cram_tiles(Slot *f)") or ""
    if "shot_vram_leave_white" not in fire7:
        return fail("fire 7 must leave locked white before comet DMA")
    print("  fire 7: leave_white before PAL2[13] paint")

    initf = fn_span(
        ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)"
    ) or ""
    kind_at = initf.find("e->kind = KIND_EBULLET")
    det_at = initf.find("spr_detach")
    lock_at = initf.find("ebullet_normal_lock")
    if det_at < 0 or lock_at < 0 or det_at < kind_at:
        return fail("init_frag must spr_detach leftover SAT after KIND_EBULLET under NORMAL")
    if "ebullet_normal_lock(e) && e->spr" not in initf.replace(" ", "").replace("\n", ""):
        if "ebullet_normal_lock(e) && e->spr" not in initf:
            return fail("NORMAL box/gun/boss discs must drop leftover SAT")
    print("  init_frag: NORMAL detaches crate/type21 leftover SAT")

    setc = fn_span(ent, "static void spr_set_sat_col(Slot *s, u8 col)") or ""
    if "ebullet_white_frame" not in setc:
        return fail("spr_set_sat_col must not upload leftover crate/type21 as (oldframe,15)")
    print("  spr_set_sat_col: upload only bolinha frames")

    drop = fn_span(ent, "static void box_death_drop(s16 sx, s16 sy)") or ""
    if drop.count(", 38)") < 3:
        return fail("boxes still 3× type 38")
    if "spr_set_sat_col" in drop:
        return fail("box_death_drop must not private-walk colour")
    print("  box 4: 3× type 38 via init_frag")

    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)") or ""
    if "rnd(" in apply:
        return fail("apply_vis must not rnd-walk (NORMAL cannot cycle)")
    walk = fn_span(ent, "static void ebullet_8659(Slot *e)") or ""
    if "ebullet_normal_lock" not in walk or "0x8F" not in walk:
        return fail("ebullet_8659 must refuse NORMAL lock")
    if apply.count("ebullet_8659") < 2:
        return fail("type 21 and HIGH must still 8659")
    print("  assert: NORMAL cannot rnd-walk; type 21 / HIGH can")

    arm38 = initf.split("variant == 38")[1][:400] if "variant == 38" in initf else ""
    if "apply_dir_88(e, dir, 3)" not in arm38:
        return fail("type 38 must keep Japan speed 3")
    skip = re.search(
        r"if\s*\(\s*s->vram_fr\s*==\s*s->frame\s*&&\s*s->vram_nib\s*==\s*want"
        r"[\s\S]{0,80}?\)\s*return;",
        up,
    )
    if not skip or "ebullet_normal_lock" in skip.group(0):
        return fail("matching skip must stay (3+ volley speed)")
    print("  speed: type 38 = 3; matching skip kept")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")
    if "never-evicted" not in opth and "PAL2[15]" not in opth:
        return fail("options.h must document locked white / PAL2[15]")
    print("  KEEP: no VDP_*Tiles; type 21 ungated; no per-tick paint_all")

    print("ok: NORMAL box bolinhas cannot show non-white pixels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
