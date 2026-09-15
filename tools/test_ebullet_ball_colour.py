#!/usr/bin/env python3
"""Ground/floor 'tiro bolinha' colour vs Japan SAT + MD shot bank.

Playtest after #135: 'Ainda tá errado: Inimigos (de chão e de solo), o
tiro bolinha (o pequeno, mais comum), é SEMPRE branco. Um inimigo de
chão está disparando tiros que mudam de cor, e os boss e inimigos
voadores estão disparando tiros coloridos.'

Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  Pat 7 FRAME_LEAD is the 4x5 disc — the common small bolinha.
  Types 20 / 37 / 38 / 41 / 42 / 43. Init +04 = 0x8F at 8672 / 84eb /
  8513 / 8539 (TMS 15 white, EC). No 8659 in the armed path.
  Ground guns 46/47 and 50/51 8ddb type 38; luster 16/17, umber 7,
  wide 84, box-4 drop also type 38.

  Pat 6 FRAME_LIGHT_BAR is the short 15x5 colour-cycling shot (type 21).
  Active 8659: LD A,R / AND 0x0F / OR 0x80 / +04. Filipe: ONE ground
  enemy (guns 48/49 Y-track) already looks right; do not break it.
  Type 45 850b is 0x8F; 8625 pulses SAT name, not colour.

#135 painted type 21 onto PAL2[4] and left leads on Japan 0x8F. After
#132/#133 the shot VRAM bank keys (FRAME_LEAD, baked 15) and later
sprites inherit those white tiles — the common ground disc stays white
even when a coloured sat_col would have remapped.

Fix: paint_all lead discs onto LIGHTBAR_CRAM_NIB (same as type 21),
key the bank on nibble 4, 8659-walk +04 (draw-only). Type 45 stays
0x8F. 44A6/44BA / ebullet_hits_player unchanged. No VDP_*Tiles.

KEEP: init 20/37/38/41/42/43 +04=0x8F (EC); type 21 init no +04;
8659 still on type 21; gun k_gun colours; flyer/boss type 21.

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
    if "ebullet_lead_disc" not in ent or not re.search(
        r"ebullet_lead_disc\(\s*e\s*\)\s*\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        return fail("lead discs must 8659-walk (draw-only) so bolinhas are not stuck white")
    if re.search(
        r"if \(e->variant == 45\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        return fail("type 45 must not 8659 (size pulse, colour 0x8F)")
    print("  KEEP: type 21 8659; lead discs walk; type 45 no walk")

    want = fn_span(ent, "static u8 proj_tile_want(const Slot *s)")
    if not want:
        return fail("proj_tile_want not found")
    if "variant == 21" not in want or "LIGHTBAR_CRAM_NIB" not in want:
        return fail("type 21 must bank on nibble 4, not leftover sat_col 15")
    if "ebullet_lead_disc" not in want:
        return fail("lead discs must bank on nibble 4, not baked 15")
    print("  proj_tile_want: type 21 + lead discs -> LIGHTBAR_CRAM_NIB")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)")
    if not up:
        return fail("spr_upload_color not found")
    if "paint_bar" not in up:
        return fail("spr_upload_color must paint_all CRAM shots")
    if "ebullet_lead_disc" not in up and "ebullet_cram_shot" not in up:
        return fail("lead discs must paint_all onto PAL2[4], not verbatim baked-15")
    print("  spr_upload_color: type 21 + leads paint_all, no verbatim baked-15")

    paint = fn_span(ent, "static void xor_cram_paint(Slot *s, u8 nib)")
    if not paint:
        return fail("xor_cram_paint not found")
    if not re.search(r"remap_cache_get\([^;]*1\s*\)", paint):
        return fail("xor_cram_paint must paint_all like fire 7")
    print("  xor_cram_paint: paint_all")

    wanted = fn_span(ent, "static int xor_cram_wanted(const Slot *s)")
    if not wanted or "ebullet_lead_disc" not in wanted:
        return fail("lead discs must CRAM-bind (xor_cram_wanted)")
    if "variant == 45" in wanted:
        return fail("type 45 must not CRAM-bind")
    print("  xor_cram_wanted: lead discs yes; type 45 no")

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
        print("ok: lead discs paint_all PAL2[4] + 8659 walk; type 21 KEEP")
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
    print("ok: lead discs paint_all PAL2[4] + 8659 walk; type 21 KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
