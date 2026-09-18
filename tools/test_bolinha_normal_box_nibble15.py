#!/usr/bin/env python3
"""#149 pin still colour-cycled caixinha×3. Japan pat 7, not FRAME_LEAD.

Filipe after #149 merge+rebuild (tip 4cd1f4d): caixinha bolinhas still
do not match Japan MSX under BULLET VISIBILITY = NORMAL. He is done
with incremental CRAM / pin / share hacks.

Japan v1 (zanac-re, SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):
  0x8513 type 38 CALL 8507: LD (IX+04), 0x8F  — no 8659
  0x84eb type 37 / 42: 0x8F
  0x8539 type 41: 0x8F
  0x8672 type 20: 0x8F
  SAT 0x1C = gfx pat 7 (centred ~4x5 disc in a 16x16)
  0x8659 type 21 only: LD A,R / AND 0x0F / OR 0x80

SGDK FRAME_LEAD is an 8x8 UL shard of pat 7. Shared VRAM + CRAM walks
made boxes cycle while early floor guns sometimes looked white.

This file FAILS unless:
  * Lead discs encode Japan pat 7 into a 16x16 vehicle (FRAME_CIRCLE)
  * SAT name stays 0x1C (ebullet_sat_name / ebullet_place_lead)
  * NORMAL = nibble 15 / 0x8F, no 8659, no type-21 tile share
  * HIGH / type 21 still 8659 on TYPE21_CRAM_NIB
  * box_death_drop is exactly 3× type 38 via init_frag
  * skill never enters; no VDP_allocateTiles

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
    opth = OPTH.read_text(encoding="utf-8")

    if not re.search(r"#define\s+LEAD_WHITE_NIB\s+15", ent):
        return fail("LEAD_WHITE_NIB must stay 15")
    if re.search(r"#define\s+TYPE21_CRAM_NIB\s+3\b", ent):
        return fail("TYPE21_CRAM_NIB must not be flyer green 3")
    if not re.search(r"#define\s+TYPE21_CRAM_NIB\s+5", ent):
        return fail("TYPE21_CRAM_NIB must be dedicated 5")
    if "type21_cram_not_white" not in ent or "fire7_cram_not_white" not in ent:
        return fail("C89 asserts: type 21 / fire 7 must not be nibble 15")
    print("  nibbles: white 15; type 21 = 5; fire 7 != 15")

    if "k_japan_pat7" not in ent:
        return fail("Japan gfx pat 7 bytes missing")
    tiles = fn_span(ent, "static const u8 *lead7_tiles(u8 want)") or ""
    if "orb_encode_japan_tiles" not in tiles or "k_japan_pat7" not in tiles:
        return fail("lead7_tiles must encode Japan pat 7 (not FRAME_LEAD PNG)")
    if "LEAD_WHITE_NIB" not in tiles:
        return fail("lead7_tiles must bake nibble 15 for NORMAL")
    pin = fn_span(ent, "static int lead7_pin_ensure(u8 want, u16 *out)") or ""
    if not pin or "FRAME_CIRCLE" not in pin or "HIDDEN" not in pin:
        return fail("lead7 pin must be a hidden 16x16 FRAME_CIRCLE vehicle")
    if "SPR_addSpriteEx" not in pin or "shot_vram_keep_banked" not in pin:
        return fail("lead7 pin must hold exclusive VRAM (no VDP_*Tiles)")
    up7 = fn_span(ent, "static int ebullet_upload_lead7(Slot *s, u8 want)") or ""
    if not up7 or "lead7_pin_ensure" not in up7 or "0x1C" not in up7:
        return fail("ebullet_upload_lead7 must point at pat 7 and restore SAT 0x1C")
    if "ebullet_lead_disc" not in up7:
        return fail("upload_lead7 is only for SAT 0x1C discs (20/37/38/41/42/43)")
    print("  look: Japan pat 7 on 16x16 vehicle; SAT 0x1C")

    place = fn_span(ent, "static void ebullet_place_lead(Slot *e)") or ""
    if not place or "FRAME_CIRCLE" not in place or "0x1C" not in place:
        return fail("ebullet_place_lead must use FRAME_CIRCLE vehicle + SAT 0x1C")
    if "ebullet_upload_lead7" not in place:
        return fail("ebullet_place_lead must upload Japan pat 7")
    print("  place: every lead disc goes through ebullet_place_lead")

    for sig, tag in (
        ("static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)", "init_frag"),
        ("static void spawn_ebullet_dir(s16 x, s16 y, u8 dir)", "spawn_ebullet_dir"),
        ("static void spawn_lead20(s16 x, s16 y)", "spawn_lead20"),
    ):
        body = fn_span(ent, sig) or ""
        if "ebullet_place_lead" not in body:
            return fail("%s must ebullet_place_lead (not FRAME_LEAD shard)" % tag)
        if re.search(r"spr_place\s*\([^)]*FRAME_LEAD", body):
            return fail("%s must not spr_place FRAME_LEAD" % tag)
    stream = fn_span(ent, "static int spawn_from_type(u8 t)") or ""
    if "ebullet_place_lead" not in stream:
        return fail("stream type 20 must ebullet_place_lead")
    print("  spawn: init_frag / type37 / type20 all Japan pat 7")

    satn = fn_span(ent, "static u8 ebullet_sat_name(const Slot *e)") or ""
    if "0x1C" not in satn:
        return fail("ebullet_sat_name must keep SAT 0x1C for lead discs")
    print("  collision: SAT 0x1C (Japan 4560)")

    prep = fn_span(ent, "static int shot_vram_prepare(Slot *s, u8 want, u8 ntiles)") or ""
    if "ebullet_lead_disc" not in prep or "lead7_pin_ensure" not in prep:
        return fail("prepare must share only the Japan pat 7 pin for lead discs")
    if "lead7_pin_overlaps" not in prep or "lead7_pin_has_idx" not in prep:
        return fail("type 21 / HIGH prepare must refuse the pat 7 span")
    lock = prep.split("ebullet_normal_lock")[1][:200] if "ebullet_normal_lock" in prep else ""
    if "return 0" not in lock:
        return fail("type 45 NORMAL must not share type 21's light_bar bank")
    leave = fn_span(ent, "static int shot_vram_leave_white(Sprite *sp, u8 nib)") or ""
    if "lead7_pin_overlaps" not in leave:
        return fail("leave_white must leave the Japan pat 7 span")
    print("  VRAM: pat 7 exclusive of type 21; type 45 NORMAL paints own white")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)") or ""
    if "ebullet_upload_lead7" not in up:
        return fail("spr_upload_color must take the Japan pat 7 path for lead discs")
    if "lead_white_buf" in up:
        return fail("do not remap FRAME_LEAD PNG for bolinhas")
    print("  upload: lead discs never touch FRAME_LEAD packed nibble 4")

    pal = fn_span(ent, "static void pal2_write(u8 nib, u16 color)") or ""
    if not pal or "LEAD_WHITE_NIB" not in pal or "k_tms_vdp[LEAD_WHITE_NIB]" not in pal:
        return fail("pal2_write must force PAL2[15] to TMS white")
    print("  PAL2[15]: locked TMS white")

    drop = fn_span(ent, "static void box_death_drop(s16 sx, s16 sy)") or ""
    if drop.count("spawn_frag(") != 3 or drop.count(", 38)") != 3:
        return fail("boxes still 3× type 38 (not 6)")
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
    print("  colour: NORMAL 0x8F; type 21 / HIGH 8659")

    initf = fn_span(
        ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)"
    ) or ""
    arm38 = initf.split("variant == 38")[1][:400] if "variant == 38" in initf else ""
    if "apply_dir_88(e, dir, 3)" not in arm38:
        return fail("type 38 must keep Japan speed 3")
    if "ebullet_normal_lock(e)" not in initf or "spr_detach(e)" not in initf:
        return fail("NORMAL must drop leftover crate SAT before place")
    print("  speed: type 38 = 3; leftover SAT detached")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")
    if "pat 7" not in opth and "SAT 0x1C" not in opth:
        return fail("options.h must document Japan pat 7 / SAT 0x1C")
    boot = fn_span(ent, "void entity_init(void)") or ""
    if "lead7_pin_ensure" not in boot or "LEAD_WHITE_NIB" not in boot:
        return fail("entity_init must hold Japan pat 7 white for the session")
    place_spr = fn_span(ent, "static void spr_place(Slot *s, u16 frame)") or ""
    if "lead7_pin_ensure" not in place_spr:
        return fail("spr_place must share the Japan pat 7 pin for lead discs")
    print("  KEEP: Japan pat 7 pin; no VDP_*Tiles; type 21 ungated")

    if "WHITE_LOCK_N" in ent or "white_pin_ensure" in ent:
        return fail("remove the #149 FRAME_LEAD pin / white_lock share maze")
    print("  discarded: FRAME_LEAD white_lock / pin heuristics")

    asm = load_asm()
    if not asm:
        print("  (zanac.asm not on this machine; C locks only)")
    else:
        for addr, who in (
            ("0x84eb", "type 37/42"),
            ("0x8513", "type 38/43/45"),
            ("0x8539", "type 41"),
            ("0x8672", "type 20"),
        ):
            if not re.search(rf"LD\s+\(IX\+0x04\),\s*0x8f\s*;\s*{addr}", asm, re.I):
                return fail("zanac.asm %s is not LD (IX+04), 0x8F (%s)" % (addr, who))
        if not re.search(r"LD\s+A,\s*R\s*;\s*0x8659", asm, re.I):
            return fail("zanac.asm 8659 is not LD A,R (type 21 always-cycle)")
        if not re.search(r"JR\s+NZ,\s*0x8659\s*;\s*0x8639", asm, re.I):
            return fail("zanac.asm 8639 is not JR NZ 8659")
        print("  zanac.asm: 84eb/8513/8539/8672 +04=0x8F; 8659 type 21 always")

    print("ok: NORMAL box/ground/boss bolinhas are Japan pat 7 white discs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
