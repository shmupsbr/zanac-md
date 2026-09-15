#!/usr/bin/env python3
"""Ground/floor 'tiro bolinha' stays white (Japan +04 0x8F).

Filipe after #136: the common small bolinha colour-cycled. He wants the
OLD white behaviour back: Pat 7 FRAME_LEAD types 20/37/38/41/42/43 stay
solid TMS white (sat_col 0x8F / baked nibble 15). No CRAM walk, no 8659
R-nibble animation on the disc.

Pat 6 FRAME_LIGHT_BAR (type 21) still 8659-walks on PAL2[4] — that is a
different art. Type 45 stays 0x8F size-pulse.

KEEP: init 20/37/38/41/42/43 +04=0x8F (EC); type 21 init no +04;
8659 still on type 21; gun k_gun colours; 44A6/44BA; no VDP_*Tiles.

Usage (from zanac-md):
    python tools/test_ebullet_ball_colour.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PNG = ROOT / "res" / "sprites" / "objs.png"
ASM_CANDIDATES = (
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
)

FRAME_LEAD = 6
FRAME_LIGHT_BAR = 49


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


def frame_hist(im, idx: int) -> dict[int, int]:
    crop = im.crop((idx * 16, 0, idx * 16 + 16, 16))
    h: dict[int, int] = {}
    for y in range(16):
        for x in range(16):
            p = crop.getpixel((x, y))
            h[p] = h.get(p, 0) + 1
    return h


def cram_ungated(body: str) -> bool:
    """Lead discs on a CRAM/8659 path with no HIGH-visibility gate."""
    if "ebullet_lead_disc" not in body:
        return False
    if "options_bullet_high" in body or "BULLET_VIS_HIGH" in body:
        return False
    if "return 0" in body and "ebullet_lead_disc" in body:
        # Classifier that explicitly refuses leads is a white lock.
        if re.search(
            r"if\s*\(\s*ebullet_lead_disc\s*\([^)]*\)\s*\)\s*\n\s*return 0",
            body,
        ):
            return False
    return True


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")

    if "FRAME_LEAD      6" not in ent and "FRAME_LEAD 6" not in ent:
        return fail("FRAME_LEAD must stay objs frame 6 (pat 7 disc)")
    if "FRAME_LIGHT_BAR 49" not in ent and "FRAME_LIGHT_BAR  49" not in ent:
        return fail("FRAME_LIGHT_BAR must stay objs frame 49 (pat 6)")
    print("  frames: LEAD=6 disc; LIGHT_BAR=49 colour-walk")

    lead = fn_span(ent, "static int ebullet_lead_disc(const Slot *s)")
    if not lead:
        return fail("ebullet_lead_disc must classify pat-7 types")
    for v in ("20", "37", "38", "41", "42", "43"):
        if v not in lead:
            return fail("ebullet_lead_disc must include type %s" % v)
    if "21" in lead.split("return")[0] and "== 21" in lead:
        return fail("type 21 is the bar, not the lead disc")
    print("  ebullet_lead_disc: 20/37/38/41/42/43")

    cram = fn_span(ent, "static int ebullet_cram_shot(const Slot *s)")
    if not cram:
        return fail("ebullet_cram_shot not found")
    if "variant == 21" not in cram:
        return fail("type 21 must stay a CRAM shot")
    if cram_ungated(cram):
        return fail("default: lead discs must not be CRAM shots (white lock)")
    if "options_bullet_high" not in cram:
        return fail("HIGH must gate lead CRAM; NORMAL stays white")
    print("  ebullet_cram_shot: type 21 yes; leads NORMAL white / HIGH gated")

    frag = fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not frag:
        return fail("init_frag not found")
    if "variant != 21" not in frag or "e->sat_col = 0x8F" not in frag:
        return fail("init still writes Japan +04=0x8F on 20/37/38/41/42/43")
    if re.search(r"if\s*\(\s*variant\s*==\s*21\s*\)\s*\n\s*e->sat_col", frag):
        return fail("init_frag must not invent type 21 +04 (863b)")
    if "FRAME_LIGHT_BAR : FRAME_LEAD" not in frag.replace(" ", "") and (
        "(variant == 21 || variant == 45) ? FRAME_LIGHT_BAR : FRAME_LEAD" not in frag
    ):
        return fail("type 21/45 spr_place FRAME_LIGHT_BAR; leads FRAME_LEAD")
    if "cram_nib = 0" not in frag:
        return fail("init_frag must clear leftover cram_nib before spr_place")
    print("  init_frag: leads 0x8F FRAME_LEAD; type 21 no +04; cram_nib cleared")

    if not re.search(
        r"if \(e->variant == 21\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        return fail("type 21 must still 8659 R-nibble|0x80")
    if len(re.findall(
        r"if \(e->variant == 21\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    )) != 1:
        return fail("type 21 8659 must stay a single write")
    if re.search(
        r"ebullet_lead_disc\(\s*e\s*\)\s*\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ) and "options_bullet_high" not in ent:
        return fail("lead discs must not 8659-walk in default (white lock)")
    if not re.search(
        r"ebullet_lead_disc\(\s*e\s*\)\s*&&\s*options_bullet_high\(\s*\)",
        ent,
    ):
        return fail("HIGH must restore 8659 colour-walk on lead discs only")
    if re.search(
        r"if \(e->variant == 45\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        return fail("type 45 must not 8659 (size pulse, colour 0x8F)")
    print("  KEEP: type 21 8659; leads NORMAL white / HIGH walk; type 45 no walk")

    want = fn_span(ent, "static u8 proj_tile_want(const Slot *s)")
    if not want:
        return fail("proj_tile_want not found")
    if "variant == 21" not in want and "ebullet_cram_shot" not in want:
        return fail("type 21 must bank on nibble 4, not leftover sat_col 15")
    if "LIGHTBAR_CRAM_NIB" not in want:
        return fail("type 21 must bank on LIGHTBAR_CRAM_NIB")
    if re.search(
        r"ebullet_lead_disc\s*\([^)]*\)\s*\)\s*\n\s*return LIGHTBAR_CRAM_NIB",
        want,
    ):
        return fail("lead discs must not bank on PAL2[4] (default white)")
    if "ebullet_lead_disc" in want and "return 15" not in want:
        return fail("lead discs must key the bank on baked nibble 15 (white)")
    print("  proj_tile_want: type 21 -> nibble 4; leads -> 15 white")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)")
    if not up:
        return fail("spr_upload_color not found")
    if "paint_bar" not in up:
        return fail("spr_upload_color must paint_all CRAM shots")
    if "ebullet_cram_shot" not in up:
        return fail("spr_upload_color must paint_all type 21 onto PAL2[4]")
    if re.search(
        r"ebullet_lead_disc\s*\([^)]*\)\s*\n\s*want = LIGHTBAR_CRAM_NIB",
        up,
    ):
        return fail("spr_upload_color must not paint leads onto PAL2[4]")
    if "ebullet_lead_disc" in up and "want = 15" not in up:
        return fail("spr_upload_color must force lead discs to nibble 15")
    print("  spr_upload_color: type 21 paint_all; leads verbatim 15")

    paint = fn_span(ent, "static void xor_cram_paint(Slot *s, u8 nib)")
    if not paint:
        return fail("xor_cram_paint not found")
    if not re.search(r"remap_cache_get\([^;]*1\s*\)", paint):
        return fail("xor_cram_paint must paint_all like fire 7")
    print("  xor_cram_paint: paint_all")

    wanted = fn_span(ent, "static int xor_cram_wanted(const Slot *s)")
    if not wanted:
        return fail("xor_cram_wanted not found")
    if cram_ungated(wanted):
        return fail("lead discs must not CRAM-bind in default (xor_cram_wanted)")
    if "variant == 45" in wanted:
        return fail("type 45 must not CRAM-bind")
    if "ebullet_cram_shot" not in wanted and "variant == 21" not in wanted:
        return fail("type 21 must still CRAM-bind")
    print("  xor_cram_wanted: type 21 yes; lead discs no; type 45 no")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")
    print("  KEEP: no VDP_allocateTiles/releaseTiles")

    if "ebullet_hits_player" not in ent or "ebullet_sat_name" not in ent:
        return fail("KEEP: Japan 44A6/44BA ebullet ship+SAT name")
    print("  KEEP: ebullet_hits_player / ebullet_sat_name")

    if "k_gun[5][4]" not in ent and "k_gun[5][4] =" not in ent:
        return fail("k_gun table missing")
    if not re.search(r"k_gun\[5\]\[4\]\s*=\s*\{[^;]*\b38\b[^;]*\b21\b", ent, re.S):
        return fail("k_gun must still fire type 38 (bolinha) and type 21 (cycler)")
    print("  KEEP: k_gun child types 38 / 21")

    opt_c = (ROOT / "src" / "options.c").read_text(encoding="utf-8")
    opt_h = (ROOT / "inc" / "options.h").read_text(encoding="utf-8")
    title = (ROOT / "src" / "title.c").read_text(encoding="utf-8")
    if "s_bullet_vis = BULLET_VIS_NORMAL" not in opt_c:
        return fail("default BULLET VISIBILITY must be NORMAL (white)")
    if "BULLET_VIS_NORMAL       0" not in opt_h or "BULLET_VIS_HIGH         1" not in opt_h:
        return fail("BULLET_VIS_NORMAL=0 / HIGH=1")
    if "options_bullet_high" not in opt_c or "options_nudge_bullet_vis" not in opt_c:
        return fail("options must persist BULLET VISIBILITY like other rows")
    if '"BULLET VISIBILITY"' not in title:
        return fail("OPTIONS must list BULLET VISIBILITY")
    opt_ui = fn_span(title, "static void draw_options_menu(void)") or ""
    if '"NORMAL"' not in opt_ui or '"HIGH"' not in opt_ui:
        return fail("BULLET VISIBILITY must list NORMAL / HIGH")
    if "options_nudge_bullet_vis" not in title:
        return fail("OPTIONS Left/Right must nudge BULLET VISIBILITY")
    print("  OPTIONS: BULLET VISIBILITY NORMAL (default) / HIGH")

    asm = load_asm()
    if asm:
        for addr, col in (
            ("0x84eb", "0x8f"),
            ("0x8513", "0x8f"),
            ("0x8539", "0x8f"),
            ("0x8672", "0x8f"),
        ):
            if not re.search(rf"{col}\s*;\s*{addr}", asm, re.I):
                return fail("zanac.asm %s is not %s" % (addr, col))
        if not re.search(r"LD\s+A,\s*R\s*;\s*0x8659", asm, re.I):
            return fail("zanac.asm 8659 is not LD A,R")
        print("  zanac.asm: lead init 0x8F; 8659 LD A,R")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    try:
        from PIL import Image
    except ImportError:
        print("  (Pillow missing; skip objs.png hist)")
        print("ok: lead discs white (nibble 15 / 0x8F); type 21 KEEP")
        return 0

    if not PNG.is_file():
        return fail("res/sprites/objs.png missing")
    im = Image.open(PNG)
    if im.mode != "P":
        return fail("objs.png must stay indexed")
    leadh = frame_hist(im, FRAME_LEAD)
    bar = frame_hist(im, FRAME_LIGHT_BAR)
    lead_body = {k: v for k, v in leadh.items() if k}
    bar_body = {k: v for k, v in bar.items() if k}
    if set(lead_body) != {15}:
        return fail("FRAME_LEAD bolinha must bake TMS 15, got %s" % lead_body)
    if set(bar_body) != {4}:
        return fail("FRAME_LIGHT_BAR must bake TMS 4, got %s" % bar_body)
    if lead_body[15] < 8 or lead_body[15] > 24:
        return fail("FRAME_LEAD should be a small disc (~14 px), got %d" % lead_body[15])
    print("  objs.png: LEAD nibble 15 disc; LIGHT_BAR nibble 4 bar")
    print("ok: lead discs white (nibble 15 / 0x8F); type 21 KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
