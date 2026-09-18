#!/usr/bin/env python3
"""White bolinha ×3+ feel slow: programmed speed vs DMA slowdown.

Filipe after #151 (look locked): groups of 3+ white discs (caixinha×3)
feel like molasses. Appearance is correct — do not change art / colour.
He asks: reuse the same sprite and only multiplex?

Japan v1 type 38 (box×3 / stealth volley / umber burst):
  8507  LD (IX+0x17),0x03     ; speed byte 3
  851d  CALL 4cf7             ; unit mag 128 * 3 = 1.5 px/frame cardinal
Port apply_dir_88(e, dir, 3) matches. NOT half of MSX — do not double.

#144 DMA every tick was one hitch. #151 still serialised per-shot
AUTO_VRAM alloc/free + paint + apply_vis upload on every disc. A
3-frag volley hitch drops the game off 60fps so speed-3 looks slow.

Safe fix: one shared FRAME_LEAD pin DMA; every live disc points at
that tile index (no AUTO_VRAM, no per-shot paint after the first);
apply_vis is a no-op when already on the pin. Leave speed 3.

Usage (from zanac-md):
    python tools/test_bolinha_volley_speed.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
ASM_CANDIDATES = (
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
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


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")

    init = fn_span(
        ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)"
    ) or ""
    # variant 38 arm: apply_dir_88(e, dir, 3) — not 6.
    arm38 = init.split("variant == 38")[1][:400] if "variant == 38" in init else ""
    if "apply_dir_88(e, dir, 3)" not in arm38:
        return fail("type 38 must keep Japan 8507 speed 3")
    if "apply_dir_88(e, dir, 6)" in arm38:
        return fail("do not double type 38 speed (this was DMA slowdown)")
    print("  type 38: apply_dir_88 speed 3 (Japan +17=3)")

    units = re.search(
        r"static const s16 k_unit_y\[16\] = \{\s*([^}]+)\}", ent, re.S
    )
    if not units or "128" not in units.group(1).split(",")[0]:
        return fail("k_unit_y[0] must stay mag 128 (4cf7 unit)")
    print("  4cf7 unit mag 128 * speed 3 = 1.5 px/frame cardinal")

    drop = fn_span(ent, "static void box_death_drop(s16 sx, s16 sy)") or ""
    if drop.count("spawn_frag(") != 3 or ", 38)" not in drop:
        return fail("red box still fires 3× type 38")
    print("  box×3: three type 38, speed 3 each")

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
    if "share ? 0 : SPR_FLAG_AUTO_VRAM_ALLOC" not in place.replace(" ", "").replace(
        "\n", ""
    ) and "share ? 0 : SPR_FLAG_AUTO_VRAM_ALLOC" not in place:
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
        return fail("keep spr_sync_proj own-every-tick (poison was AUTO upload)")
    print("  spr_sync_proj: own tiles so SPR_update cannot re-poison 15")

    asm = load_asm()
    if asm:
        if not re.search(r"LD\s+\(IX\+0x17\),\s*0x03\s*;\s*0x8507", asm, re.I):
            return fail("zanac.asm 8507 is not speed 3")
        print("  zanac.asm 8507: +17=3")
    else:
        print("  (zanac.asm not on this machine; C speed 3 locked)")

    print("ok: programmed speed matches MSX; 3+ slowness was #144 DMA, not half-vel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
