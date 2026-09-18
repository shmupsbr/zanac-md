#!/usr/bin/env python3
"""#150 Japan pat-7 16x16 is a ship-sized blob. Restore FRAME_LEAD.

Filipe after #150 merge+rebuild (tip 65a62bb): bolinhas are completely
wrong — a huge sprite the size of the player ship. The old FRAME_LEAD
(~14 px / SGDK 8x8) was the accepted bolinha. Only colour was wrong
before: NORMAL must stay solid white, no 8659.

This file FAILS unless:
  * Lead discs use FRAME_LEAD (not FRAME_CIRCLE / Japan pat 7 16x16)
  * SAT name stays 0x1C (ebullet_sat_name / ebullet_place_lead)
  * Exclusive FRAME_LEAD pin: paint_all-15 + keep_body 15
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

    tiles = fn_span(ent, "static const u8 *lead_frame_tiles(const u8 *src, u16 nbytes, u8 want)") or ""
    if not tiles:
        return fail("lead_frame_tiles must paint FRAME_LEAD PNG (not Japan pat 7)")
    if "orb_encode_japan_tiles" in tiles or "k_japan_pat7" in tiles:
        return fail("lead tiles must not encode Japan pat 7 into a 16x16 vehicle")
    if "orb_paint_body_nibbles" not in tiles or "orb_keep_body_nibbles" not in tiles:
        return fail("lead_frame_tiles must paint_all + keep_body onto want")
    pin = fn_span(ent, "static int lead7_pin_ensure(u8 want, u16 *out)") or ""
    if not pin or "FRAME_LEAD" not in pin or "HIDDEN" not in pin:
        return fail("lead pin must be a hidden FRAME_LEAD bolinha")
    if re.search(r"SPR_setAnimAndFrame\s*\([^)]*FRAME_CIRCLE", pin):
        return fail("lead pin must not set FRAME_CIRCLE (ship-sized #150 blob)")
    if "SPR_addSpriteEx" not in pin or "shot_vram_keep_banked" not in pin:
        return fail("lead pin must hold exclusive VRAM (no VDP_*Tiles)")
    if "lead_frame_tiles" not in pin:
        return fail("lead pin must DMA FRAME_LEAD PNG tiles")
    up7 = fn_span(ent, "static int ebullet_upload_lead7(Slot *s, u8 want)") or ""
    if not up7 or "lead7_pin_ensure" not in up7 or "0x1C" not in up7:
        return fail("ebullet_upload_lead7 must point at FRAME_LEAD and restore SAT 0x1C")
    if "ebullet_lead_disc" not in up7:
        return fail("upload_lead7 is only for SAT 0x1C discs (20/37/38/41/42/43)")
    print("  look: small FRAME_LEAD pin; SAT 0x1C")

    place = fn_span(ent, "static void ebullet_place_lead(Slot *e)") or ""
    if not place or "FRAME_LEAD" not in place or "0x1C" not in place:
        return fail("ebullet_place_lead must use FRAME_LEAD + SAT 0x1C")
    if re.search(r"spr_place\s*\([^)]*FRAME_CIRCLE", place):
        return fail("ebullet_place_lead must not spr_place FRAME_CIRCLE")
    if "ebullet_upload_lead7" not in place:
        return fail("ebullet_place_lead must upload the FRAME_LEAD pin")
    print("  place: every lead disc goes through ebullet_place_lead")

    for sig, tag in (
        ("static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)", "init_frag"),
        ("static void spawn_ebullet_dir(s16 x, s16 y, u8 dir)", "spawn_ebullet_dir"),
        ("static void spawn_lead20(s16 x, s16 y)", "spawn_lead20"),
    ):
        body = fn_span(ent, sig) or ""
        if "ebullet_place_lead" not in body:
            return fail("%s must ebullet_place_lead (FRAME_LEAD bolinha)" % tag)
        if re.search(r"spr_place\s*\([^)]*FRAME_CIRCLE", body):
            return fail("%s must not spr_place FRAME_CIRCLE for lead discs" % tag)
    stream = fn_span(ent, "static int spawn_from_type(u8 t)") or ""
    if "ebullet_place_lead" not in stream:
        return fail("stream type 20 must ebullet_place_lead")
    print("  spawn: init_frag / type37 / type20 all FRAME_LEAD")

    satn = fn_span(ent, "static u8 ebullet_sat_name(const Slot *e)") or ""
    if "0x1C" not in satn:
        return fail("ebullet_sat_name must keep SAT 0x1C for lead discs")
    print("  collision: SAT 0x1C (Japan 4560)")

    prep = fn_span(ent, "static int shot_vram_prepare(Slot *s, u8 want, u8 ntiles)") or ""
    if "ebullet_lead_disc" not in prep or "lead7_pin_ensure" not in prep:
        return fail("prepare must share only the FRAME_LEAD pin for lead discs")
    if "lead7_pin_overlaps" not in prep or "lead7_pin_has_idx" not in prep:
        return fail("type 21 / HIGH prepare must refuse the FRAME_LEAD span")
    lock = prep.split("ebullet_normal_lock")[1][:200] if "ebullet_normal_lock" in prep else ""
    if "return 0" not in lock:
        return fail("type 45 NORMAL must not share type 21's light_bar bank")
    leave = fn_span(ent, "static int shot_vram_leave_white(Sprite *sp, u8 nib)") or ""
    if "lead7_pin_overlaps" not in leave:
        return fail("leave_white must leave the FRAME_LEAD pin span")
    print("  VRAM: FRAME_LEAD exclusive of type 21; type 45 NORMAL paints own white")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)") or ""
    if "ebullet_upload_lead7" not in up:
        return fail("spr_upload_color must take the FRAME_LEAD pin path for lead discs")
    if "orb_encode_japan_tiles" in (fn_span(ent, "static int ebullet_upload_lead7(Slot *s, u8 want)") or ""):
        return fail("do not encode Japan pat 7 for bolinhas")
    print("  upload: lead discs use FRAME_LEAD pin, not Japan 16x16")

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
    if "apply_dir_88(e, dir, LEAD_MD_SPEED)" not in arm38:
        return fail("type 38 must use LEAD_MD_SPEED (MD feel, not Japan 3)")
    if "ebullet_normal_lock(e)" not in initf or "spr_detach(e)" not in initf:
        return fail("NORMAL must drop leftover crate SAT before place")
    print("  speed: type 38 = LEAD_MD_SPEED; leftover SAT detached")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")
    if "FRAME_LEAD" not in opth or "0x1C" not in opth:
        return fail("options.h must document FRAME_LEAD bolinha / SAT 0x1C")
    if "Do not encode" not in opth:
        return fail("options.h must reject the #150 16x16 FRAME_CIRCLE vehicle")
    boot = fn_span(ent, "void entity_init(void)") or ""
    if "lead7_pin_ensure" not in boot or "LEAD_WHITE_NIB" not in boot:
        return fail("entity_init must hold FRAME_LEAD white for the session")
    place_spr = fn_span(ent, "static void spr_place(Slot *s, u16 frame)") or ""
    if "lead7_pin_ensure" not in place_spr:
        return fail("spr_place must share the FRAME_LEAD pin for lead discs")
    print("  KEEP: FRAME_LEAD pin; no VDP_*Tiles; type 21 ungated")

    if "WHITE_LOCK_N" in ent or "white_pin_ensure" in ent:
        return fail("do not bring back the #149 white_lock / pin share maze")
    pin_fn = fn_span(ent, "static int lead7_pin_ensure(u8 want, u16 *out)") or ""
    if "orb_encode_japan_tiles" in pin_fn or "k_japan_pat7" in pin_fn:
        return fail("do not bring back the #150 Japan pat 7 16x16 encode")
    print("  discarded: #150 Japan 16x16; #149 white_lock maze")

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

    print("ok: NORMAL box/ground/boss bolinhas are small FRAME_LEAD white discs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
