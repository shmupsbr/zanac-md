#!/usr/bin/env python3
"""#145 shared (FRAME_LEAD,15) and colour-cycle returned.

Filipe after #145: box / boss / ground bolinhas colour-cycle again
under BULLET VISIBILITY = NORMAL. #143/#144 white was right; #145
restored the matching-vram skip and shared any remembered 15.

Why #145 reintroduced the cycle:
  * shot_vram_remember() after paint_all still retargeted onto an
    older (frame,15) index if one was already tagged. Verbatim
    want==baked DMA of FRAME_LEAD leaves SGDK packed nibble 4.
  * prepare / matching skip then treated that bank as white.
  * Type 21 (`<===>`) always 8659-walks PAL2[4] (#145, keep). Packed
    nibble 4 discs ride that CRAM walk — boxes and bosses cycle.

Required:
  * Share / skip only a bank remember()'d after paint_all rewrote
    every nonzero nibble to 15. Never share packed 4.
  * After paint_all, keep the sprite on the index we just DMA'd.
  * Matching skip stays (no paint_all-every-tick 3+ slowdown).
  * Type 21 still always cycles; HIGH discs still cycle; skill unused.
  * 8659 / xor_cram must not DMA nibble 4 into a proven white index.

Usage (from zanac-md):
    python tools/test_bolinha_white_share.py
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

    bank = re.search(
        r"typedef struct \{([^}]+)\} ShotBank",
        ent,
        re.S,
    )
    if not bank or "painted" not in bank.group(1):
        return fail("ShotBank must record paint_all provenance (not just frame,nib)")
    print("  ShotBank: painted flag (proven nibble 15)")

    rem = fn_span(ent, "static void shot_vram_remember(Slot *s, u8 want, u8 ntiles, u8 painted)")
    if not rem:
        return fail("shot_vram_remember must take a painted argument")
    if "index = cur" not in rem.replace(" ", "") and "index=cur" not in rem.replace(
        " ", ""
    ):
        if "s_shot_bank[i].index = cur" not in rem:
            return fail("paint_all remember must keep the just-DMA'd index (no retarget to packed 4)")
    if re.search(
        r"if \(shot_bank_lookup[^)]*\)\s*\{\s*shot_vram_point",
        rem,
        re.S,
    ):
        return fail("#145 remember() retarget-on-lookup is the poisoned-nibble share")
    print("  shot_vram_remember: paint_all keeps cur; no point-at-old-15")

    prep = fn_span(ent, "static int shot_vram_prepare(Slot *s, u8 want, u8 ntiles)") or ""
    if "lead7_pin_ensure" not in prep:
        return fail("NORMAL 3+ discs must share the Japan pat 7 pin")
    if "ebullet_normal_lock" not in prep or "return 0" not in prep:
        return fail("type 45 NORMAL / pin miss must still encode")
    print("  shot_vram_prepare: Japan pat 7 pin; type 45 isolated")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)") or ""
    skip = re.search(
        r"if\s*\(\s*s->vram_fr\s*==\s*s->frame\s*&&\s*s->vram_nib\s*==\s*want"
        r"[\s\S]{0,80}?\)\s*return;",
        up,
    )
    if not skip:
        return fail("matching-vram skip missing (3+ would DMA every tick)")
    if "ebullet_normal_lock" in skip.group(0):
        return fail("do not put ebullet_normal_lock in the skip (that is #144 slowdown)")
    if "shot_vram_white_proven" not in up:
        return fail("bust a lying (frame,15) tag before the matching skip")
    if "shot_vram_remember(s, want, (u8)ts->numTile, 0)" not in up.replace(" ", "").replace(
        "\n", ""
    ) and "shot_vram_remember(s, want, (u8)ts->numTile, 0)" not in up:
        # verbatim path must not claim painted
        if re.search(r"shot_vram_remember\s*\(\s*s,\s*want,\s*\(u8\)ts->numTile,\s*0\s*\)", up) is None:
            return fail("verbatim want==baked remember must pass painted=0")
    if re.search(r"shot_vram_remember\s*\(\s*s,\s*want,\s*\(u8\)ts->numTile,\s*painted\s*\)", up) is None:
        return fail("paint_all path must remember painted")
    if "shot_vram_leave_white" not in up:
        return fail("nibble-4 DMA must leave a proven white bank")
    print("  spr_upload_color: skip proven white; verbatim not painted; leave white")

    proven = fn_span(ent, "static int shot_vram_white_proven(const Slot *s, u8 want)") or ""
    if "painted" not in proven or "index" not in proven or "15" not in proven:
        return fail("white_proven must match painted + index + nibble 15")
    print("  shot_vram_white_proven: sprite sits on paint_all-15 tiles")

    leave = fn_span(ent, "static int shot_vram_leave_white(Sprite *sp, u8 nib)") or ""
    if not leave or "shot_vram_fresh_auto" not in leave:
        return fail("leave_white must fresh_auto off a proven 15 index before type21 DMA")
    if "u8 frame" in leave:
        return fail("#146 hole: leave_white must not key only the same frame")
    if "shot_bank_index_is_white" not in leave:
        return fail("leave_white must match any-frame painted-15 at this index")
    if "shot_bank_index_is_lead" not in leave:
        return fail("leave_white must leave any FRAME_LEAD bank")
    print("  shot_vram_leave_white: any white/lead index; type 21 cannot tint")

    xpaint = fn_span(ent, "static void xor_cram_paint(Slot *s, u8 nib)") or ""
    if "shot_vram_leave_white" not in xpaint:
        return fail("xor_cram_paint must not DMA 4 into a white (frame,15) index")
    if re.search(r"shot_vram_remember\s*\([^;]*,\s*1\s*\)", xpaint) is None:
        return fail("xor_cram_paint remember is paint_all (painted=1) for its nibble")
    print("  xor_cram_paint: leave white; remember painted nibble")

    cyc = fn_span(ent, "static void xor_cram_cycle(Slot *s, u8 col)") or ""
    bind = fn_span(ent, "static int xor_cram_bind(Slot *s, u8 col)") or ""
    if "ebullet_normal_lock" not in cyc or "ebullet_normal_lock" not in bind:
        return fail("NORMAL FRAME_LEAD must never 8659 / xor_cram")
    print("  xor_cram: NORMAL lock still refuses cycle/bind")

    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)") or ""
    light_at = apply.find("ebullet_light_bar")
    high_at = apply.find("options_bullet_high")
    if light_at < 0 or high_at < 0 or light_at > high_at:
        return fail("type 21 8659 must stay always-on, before vis-gated discs")
    if apply[light_at:high_at].count("ebullet_8659") < 1:
        return fail("type 21 arm must still 8659")
    print("  apply_vis: type 21 always cycles; HIGH discs cycle")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")
    if "paint_all-15 every tick" not in opth and "do not DMA" not in opth:
        if "Share a" not in opth and "share" not in opth.lower():
            return fail("options.h must document proven-paint share / no per-tick DMA")
    print("  KEEP: no VDP_*Tiles; type 21 ungated; no per-tick paint_all")

    print("ok: NORMAL share is paint_all-15 only; packed 4 cannot cycle with type 21")
    return 0


if __name__ == "__main__":
    sys.exit(main())
