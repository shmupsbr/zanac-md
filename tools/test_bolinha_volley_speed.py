#!/usr/bin/env python3
"""Bolinha travel speed + 68000 multiplex.

#155 set LEAD_MD_SPEED 5 (2.5 px/f cardinal). Filipe: 4
(2.0 px/f). Appearance stays locked: FRAME_LEAD look,
NORMAL white / HIGH cycle, type 21 always 8659. Multiplex stays.

LEAD_MD_SPEED 4 = 128*4 = 2.0 px/frame cardinal.
Type 21 stays Japan 4.

Usage (from zanac-md):
    python tools/test_bolinha_volley_speed.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
OPT = ROOT / "inc" / "options.h"


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
    opth = OPT.read_text(encoding="utf-8")

    m = re.search(r"#define\s+LEAD_MD_SPEED\s+(\d+)", ent)
    if not m:
        return fail("LEAD_MD_SPEED must name the lead travel speed")
    spd = int(m.group(1))
    if spd != 4:
        return fail("LEAD_MD_SPEED must be 4")
    if "lead_md_speed_is_5" in ent:
        return fail("C89 assert must expect 4, not 5")
    if "lead_md_speed_is_4" not in ent:
        return fail("C89 assert: LEAD_MD_SPEED == 4")
    print("  LEAD_MD_SPEED %d (unit 128 → 2.0 px/frame cardinal)" % spd)

    init = fn_span(
        ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)"
    ) or ""
    arm38 = init.split("variant == 38")[1][:500] if "variant == 38" in init else ""
    if "apply_dir_88(e, dir, LEAD_MD_SPEED)" not in arm38:
        return fail("type 38 must use LEAD_MD_SPEED")
    arm37 = init.split("variant == 37")[1][:500] if "variant == 37" in init else ""
    if "LEAD_MD_SPEED" not in arm37:
        return fail("type 37 aimed disc must use LEAD_MD_SPEED")
    xor = fn_span(ent, "static void apply_dir_88_xor(Slot *e, u8 dir)") or ""
    if "LEAD_MD_SPEED" not in xor:
        return fail("type 42/43 XOR must start from LEAD_MD_SPEED")
    arm21 = init.split("variant == 21")[1][:400] if "variant == 21" in init else ""
    if "apply_dir_88(e, dir, 4)" not in arm21:
        return fail("type 21 must stay Japan speed 4")
    print("  type 37/38/42/43: LEAD_MD_SPEED 4; type 21 stays 4")

    units = re.search(
        r"static const s16 k_unit_y\[16\] = \{\s*([^}]+)\}", ent, re.S
    )
    if not units or "128" not in units.group(1).split(",")[0]:
        return fail("k_unit_y[0] must stay mag 128 (4cf7 unit)")
    print("  4cf7 unit mag 128 * 4 = 2.0 px/frame cardinal")

    drop = fn_span(ent, "static void box_death_drop(s16 sx, s16 sy)") or ""
    if drop.count("spawn_frag(") != 3 or ", 38)" not in drop:
        return fail("red box still fires 3× type 38")
    print("  box×3: three type 38 at LEAD_MD_SPEED")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)") or ""
    skip = re.search(
        r"if\s*\(\s*s->vram_fr\s*==\s*s->frame\s*&&\s*s->vram_nib\s*==\s*want"
        r"[\s\S]{0,80}?\)\s*return;",
        up,
    )
    if not skip:
        return fail("matching-vram skip missing (3+ discs would DMA every tick)")
    if "ebullet_normal_lock" in skip.group(0):
        return fail("#144 per-tick paint_all under NORMAL is the 3+ slowdown")
    if "shot_vram_white_proven" not in up:
        return fail("do not skip DMA on a lying (frame,15) tag")
    print("  spr_upload_color: skip DMA when (frame,15) already paint_all'd")

    prep = fn_span(ent, "static int shot_vram_prepare(Slot *s, u8 want, u8 ntiles)") or ""
    if "lead7_pin_ensure" not in prep:
        return fail("NORMAL 3+ discs must share the FRAME_LEAD pin (no per-disc DMA)")
    if "ebullet_lead_disc" not in prep:
        return fail("prepare must key lead discs separately from type 21")
    print("  shot_vram_prepare: FRAME_LEAD pin share (3+ volley speed)")

    place = fn_span(ent, "static void spr_place(Slot *s, u16 frame)") or ""
    compact = place.replace(" ", "").replace("\n", "")
    if "share?0:SPR_FLAG_AUTO_VRAM_ALLOC" not in compact:
        return fail("lead share must addSprite without AUTO_VRAM (multiplex, no alloc/free)")
    if "if (share)" not in place or "shot_vram_point" not in place:
        return fail("lead share must point at the pin index")
    print("  spr_place: multiplex pin tiles; no per-disc AUTO_VRAM")

    point = fn_span(ent, "static void shot_vram_point(Sprite *sp, u16 idx)") or ""
    if "TILE_INDEX_MASK" not in point or "SPR_FLAG_AUTO_VRAM_ALLOC" not in point:
        return fail("shot_vram_point must no-op when already on the shared index")
    if "SPR_setVRAMTileIndex" not in point or "SPR_setAutoTileUpload" not in point:
        return fail("shot_vram_point must still drop AUTO_TILE_UPLOAD before setVRAM")
    print("  shot_vram_point: no-op when already multiplexed")

    onpin = fn_span(ent, "static int ebullet_lead_on_pin(const Slot *s, u8 want)") or ""
    if not onpin or "FRAME_LEAD" not in onpin or "lead7_pin_has_idx" not in onpin:
        return fail("ebullet_lead_on_pin must detect a disc already on the pin")
    print("  ebullet_lead_on_pin: multiplex occupancy")

    setc = fn_span(ent, "static void spr_set_sat_col(Slot *s, u8 col)") or ""
    if "ebullet_lead_on_pin" not in setc:
        return fail("NORMAL apply_vis/set_sat_col must skip paint when already on pin")
    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)") or ""
    if "ebullet_lead_on_pin" not in apply:
        return fail("apply_vis must no-op a white disc already on the pin")
    print("  apply_vis: no per-tick paint on a pinned white disc")

    up7 = fn_span(ent, "static int ebullet_upload_lead7(Slot *s, u8 want)") or ""
    if "DMA_queueDma" in up7:
        return fail("ebullet_upload_lead7 must not DMA; pin owns the one upload")
    if "ebullet_lead_on_pin" not in up7:
        return fail("upload_lead7 must skip work when already on the pin")
    pin = fn_span(ent, "static int lead7_pin_ensure(u8 want, u16 *out)") or ""
    if "DMA_queueDma" not in pin or "FRAME_LEAD" not in pin:
        return fail("only lead7_pin_ensure DMA's FRAME_LEAD tiles (once)")
    if re.search(r"SPR_setAnimAndFrame\s*\([^)]*FRAME_CIRCLE", pin):
        return fail("do not restore the #150 16x16 vehicle")
    print("  upload: one pin DMA; later discs only point")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")

    sync = fn_span(ent, "static void spr_sync_proj(Slot *s)") or ""
    if "shot_vram_own" not in sync or "ebullet_normal_lock" not in sync:
        return fail("spr_sync_proj must still own unpinned NORMAL discs")
    if "LEAD_WHITE_NIB" not in sync:
        return fail("spr_sync_proj must skip own once the disc is on the pin")
    print("  spr_sync_proj: own only until pin; no per-tick SGDK on shared discs")

    step = re.search(
        r"e->variant == 21 \|\| e->variant == 37.*?e->variant == 45\).*?"
        r"ebullet_apply_vis\(e\).*?if \(step_88_4898\(e\)\)",
        ent,
        re.S,
    )
    if not step:
        return fail("21-group must still reach apply_vis (type 21 / HIGH / unpinned)")
    if "LEAD_WHITE_NIB" not in step.group(0):
        return fail("NORMAL pinned lead must skip apply_vis in the 21-group tick")
    print("  tick: type 21 still apply_vis; NORMAL pin skips the choke")

    if "LEAD_MD_SPEED" not in opth:
        return fail("options.h must document LEAD_MD_SPEED")
    if "LEAD_MD_SPEED (4)" not in opth:
        return fail("options.h must document LEAD_MD_SPEED (4)")
    if "FRAME_LEAD" not in opth:
        return fail("options.h must keep FRAME_LEAD appearance lock")

    print("ok: LEAD_MD_SPEED 4 + multiplex; type 21 / look unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
