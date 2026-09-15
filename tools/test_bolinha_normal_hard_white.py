#!/usr/bin/env python3
"""NORMAL vis = Japan white bolinhas. #140/#142 still colour-cycled.

Playtest of #142 (Easy + BULLET VISIBILITY NORMAL):
  * caixinhas×3 (type 4 → 3× type 38 FRAME_LEAD) still colour-cycled
  * boss shots: first boss (type 73 → type 21 LIGHT_BAR) white OK;
    second boss (type 75 → type 42 FRAME_LEAD) already wrong on entry
  * ground/floor guns (k_gun type 38 FRAME_LEAD) still colour-cycled

Root: spr_place share-tagged (FRAME_LEAD, 15) and skipped paint_all, so
SGDK-packed nibble 4 sat on PAL2[4]/XOR PAL2[2] while type 21 had its
own bank and looked white. xor_cram_cycle could still walk leftover
cram_nib. This file FAILS unless every KIND_EBULLET colour choke
hard-refuses a walk under NORMAL and FRAME_LEAD always paint_all-15.

Japan v1 (zanac-re, SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):
  0x84eb type 37 / type 42 CALL 84e3: LD (IX+04), 0x8F  — no 8659
  0x8513 type 38 / type 43 CALL 8507 / type 45 CALL 850b: 0x8F
  0x8539 type 41: 0x8F
  0x8672 type 20: 0x8F
  0x8659 type 21 active only: LD A,R / AND 0x0F / OR 0x80  — always
      (not BULLET VISIBILITY; `<===>` bar is not a bolinha)

Usage (from zanac-md):
    python tools/test_bolinha_normal_hard_white.py
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

    lock = fn_span(ent, "static int ebullet_normal_lock(const Slot *s)")
    if not lock or "ebullet_bolinha" not in lock or "options_bullet_high" not in lock:
        return fail("ebullet_normal_lock missing (bolinha && !HIGH)")
    print("  ebullet_normal_lock: single NORMAL white predicate")

    # Choke points that still walked colour under #142.
    for sig, tag in (
        ("static void spr_set_sat_col(Slot *s, u8 col)", "spr_set_sat_col"),
        ("static int xor_cram_wanted(const Slot *s)", "xor_cram_wanted"),
        ("static int xor_cram_bind(Slot *s, u8 col)", "xor_cram_bind"),
        ("static void xor_cram_cycle(Slot *s, u8 col)", "xor_cram_cycle"),
        ("static int shot_vram_prepare(Slot *s, u8 want, u8 ntiles)", "shot_vram_prepare"),
        ("static u8 sat_col_tile_nibble(const Slot *s, u8 want)", "sat_col_tile_nibble"),
    ):
        body = fn_span(ent, sig)
        if not body or "ebullet_normal_lock" not in body:
            return fail("%s must hard-refuse via ebullet_normal_lock" % tag)
    print("  choke: set_sat_col / xor_cram / prepare / nibble all lock")

    setc = fn_span(ent, "static void spr_set_sat_col(Slot *s, u8 col)") or ""
    gate = setc.split("xor_cram_cycle")[0]
    if "return;" not in gate:
        return fail("NORMAL lock must return before xor_cram_cycle / bind")
    if "0x8F" not in gate or "xor_cram_release" not in gate:
        return fail("NORMAL lock must release CRAM and force 0x8F")
    if "vram_fr = 0xFF" not in gate:
        return fail("NORMAL lock must bust leftover (frame,15) tags")
    print("  spr_set_sat_col: 0x8F + release + invalidate; no CRAM")

    prep = fn_span(ent, "static int shot_vram_prepare(Slot *s, u8 want, u8 ntiles)") or ""
    # return 0 must sit in the lock arm, not only at the function tail.
    arm = prep.split("ebullet_normal_lock")[1][:500] if "ebullet_normal_lock" in prep else ""
    if "shot_bank_lookup" not in arm or "return 0" not in arm:
        return fail("shot_vram_prepare NORMAL arm must lookup then return 0 on miss")
    print("  shot_vram_prepare: share remembered 15; miss still paint_all")

    place = fn_span(ent, "static void spr_place(Slot *s, u16 frame)") or ""
    if re.search(
        r"if \(share\)\s*\{\s*/\*.*?\*/\s*shot_vram_point.*?s->vram_nib = want",
        place,
        re.S,
    ):
        return fail("spr_place share path must not tag vram_nib (that skipped paint_all)")
    if place.count("spr_upload_color(s)") < 2:
        return fail("spr_place must upload on both new-sprite and reuse arms")
    if place.count("SPR_FLAG_AUTO_TILE_UPLOAD") < 2:
        return fail("spr_place must drop AUTO_TILE_UPLOAD on new-sprite AND reuse arms")
    reuse = ""
    if "if (!s->spr)" in place:
        reuse = place.split("if (!s->spr)", 1)[1]
        if "\n    else\n    {" in reuse:
            reuse = reuse.split("\n    else\n    {", 1)[1]
    if "SPR_FLAG_AUTO_TILE_UPLOAD" not in reuse:
        return fail("spr_place reuse arm must drop AUTO_TILE_UPLOAD (box×3 crate leftover)")
    if reuse.find("shot_vram_own") < 0 or reuse.find("SPR_setAnimAndFrame") < 0:
        return fail("spr_place reuse arm must own tiles after setAnimAndFrame")
    if reuse.find("shot_vram_own") < reuse.find("SPR_setAnimAndFrame"):
        return fail("spr_place reuse own-after must follow setAnimAndFrame (#143 new-sprite lock)")
    if reuse.count("shot_vram_own") < 2:
        return fail("spr_place reuse arm must own after setAnimAndFrame and after upload")
    print("  spr_place: paint_all on spawn; AUTO_TILE_UPLOAD off on new AND reuse")

    up = fn_span(ent, "static void spr_upload_color(Slot *s)") or ""
    skip = re.search(
        r"if\s*\(\s*s->vram_fr\s*==\s*s->frame\s*&&\s*s->vram_nib\s*==\s*want"
        r"[\s\S]{0,80}?\)\s*return;",
        up,
    )
    if not skip:
        return fail("spr_upload_color matching-vram skip missing")
    if "ebullet_normal_lock" in skip.group(0):
        return fail("NORMAL must not DMA paint_all every tick (3+ volley slowdown)")
    print("  spr_upload_color: matching skip; own-after-place holds white")

    sync = fn_span(ent, "static void spr_sync_proj(Slot *s)") or ""
    if "ebullet_normal_lock" not in sync or "shot_vram_own" not in sync:
        return fail("spr_sync_proj must own tiles every visible NORMAL tick")
    print("  spr_sync_proj: NORMAL own before SPR_update")

    initf = fn_span(
        ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)"
    ) or ""
    if "xor_cram_release" not in initf:
        return fail("init_frag must xor_cram_release leftover CRAM")
    kind_at = initf.find("e->kind = KIND_EBULLET")
    rel_at = initf.find("xor_cram_release")
    own_at = initf.find("shot_vram_own")
    if kind_at < 0 or rel_at < 0 or rel_at > kind_at:
        return fail("init_frag must xor_cram_release leftover before KIND_EBULLET")
    if own_at < 0 or own_at > kind_at:
        return fail("init_frag must shot_vram_own leftover crate/flyer SAT before KIND_EBULLET")
    if "vram_fr = 0xFF" not in initf:
        return fail("init_frag must bust leftover vram tags (slot reuse)")
    print("  init_frag: release CRAM + own leftover SAT + invalidate vram")

    drop = fn_span(ent, "static void box_death_drop(s16 sx, s16 sy)") or ""
    if drop.count("spawn_frag") < 3 or ", 38)" not in drop:
        return fail("red box death must fire 3× type 38 (caixinhas)")
    if "spr_set_sat_col" in drop:
        return fail("box_death_drop must not private-walk colour")
    print("  boxes: 3× type 38 through init_frag")

    fire = fn_span(ent, "static void base_fire(Slot *e)") or ""
    if "spawn_frag(x, y, a, 21)" not in fire:
        return fail("boss 1 / type 73 must still spawn type 21")
    if "spawn_frag(x, y, 0, 42)" not in fire:
        return fail("boss 2 / type 75 must still spawn type 42 (8d6c)")
    if "spr_set_sat_col" in fire:
        return fail("base_fire must not colour-walk children")
    for n in (73, 74, 75, 76, 77, 78, 79):
        if ("e->variant == %d" % n) not in fire:
            return fail("base_fire must handle boss type %d" % n)
    if "spawn_frag(x, y, c, 43)" not in fire:
        return fail("boss 74/76/77 must still spawn type 43")
    if ", 45)" not in fire:
        return fail("boss 79 must still spawn type 45")
    if "spawn_frag(x, y, dir, 38)" not in fire:
        return fail("base_fire fallback must still type 38")
    if "base_muzzle" not in fire:
        return fail("do not break eye muzzle")
    print("  bosses 73-79: 21/38/42/43/45 via init_frag; muzzle kept")

    gun = fn_span(ent, "static void spawn_child_dir(s16 x, s16 y, u8 stype, u8 dir)") or ""
    if "spawn_frag(x, y, dir, 21)" not in gun or "spawn_frag(x, y, dir, 38)" not in gun:
        return fail("k_gun ground shots 21/38 must go through spawn_frag")
    print("  ground guns: type 21/38 via spawn_frag")

    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)") or ""
    if "0x80|(rnd()&0x0F)" not in apply.replace(" ", ""):
        return fail("HIGH must still 8659-walk inside apply_vis")
    if "spr_set_sat_col(e, 0x8F)" not in apply:
        return fail("NORMAL apply_vis must request 0x8F (choke enforces it)")
    print("  apply_vis: HIGH 8659 / NORMAL 0x8F")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles/releaseTiles")

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
    print("ok: NORMAL hard-white FRAME_LEAD (boxes/ground/boss2); type 21 cycles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
