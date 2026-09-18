#!/usr/bin/env python3
"""White bolinha ×3+ feel slow: programmed speed vs DMA slowdown.

Filipe after #144: groups of 3+ white discs feel very slow. Diagnose:

Japan v1 type 38 (box×3 / stealth volley / umber burst):
  8507  LD (IX+0x17),0x03     ; speed byte 3
  851d  CALL 4cf7             ; unit mag 128 * 3 = 1.5 px/frame cardinal
Port apply_dir_88(e, dir, 3) matches. NOT half of MSX — do not double.

#144 slowdown: spr_upload_color refused the matching-(frame,15) skip
under ebullet_normal_lock, so every NORMAL disc DMA'd paint_all-15
(128 B) every tick. Three live discs = 384 B/frame of redundant VRAM
plus 68000 remap — same class as the orb "slowdown da porra".
shot_vram_prepare also returned 0 unconditionally, so the three
shots could not share a (FRAME_LEAD,15) bank.

Safe fix (this PR): restore matching skip (own-after-place already
stops SPR_update loadTiles poison); share a remembered 15 bank;
leave speed 3.

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
        return fail("NORMAL 3+ discs must share the Japan pat 7 pin (no per-disc DMA)")
    if "ebullet_lead_disc" not in prep:
        return fail("prepare must key lead discs separately from type 21")
    print("  shot_vram_prepare: Japan pat 7 pin share (3+ volley speed)")

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
