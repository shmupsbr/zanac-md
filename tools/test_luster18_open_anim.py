#!/usr/bin/env python3
"""Type 18 yo-yo open animation vs Japan v1 handler 0x7CD8.

The open-and-fire enemy is type 18 (handler_type18 0x7CB3), not type 8
umber or loga 46-55. 7ccd C=0x8B; shared 7c14 SAT 0x74 / marker 0x7C.

Japan v1 (zanac-re SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  7ce1  DEC (IX+0x1d)
  7ce4  JR NZ, 7cfc
  7ce6  LD (IX+0x1d),0x30
  7cea  LD (IX+0x03),0x74          ; pat 29 closed
  7cee  LD (IY+0x03),0x7C          ; pat 31
  7cf7  LD A,0x25 / CALL 8ddb      ; type 37 on the CLOSE frame
  7cfc  LD A,(IX+0x1d) / CP 0x08
  7d04  LD (IX+0x03),0x78          ; pat 30 open
  7d08  LD (IY+0x03),0x80          ; pat 32

Playtest: after #115 aligned the 71f6 pair, the open pose still looked
wrong. FRAME_LUSTER (SAT 0x78) is baked TMS 14; type 18 +04 is nibble 11.
spr_place used to remap only when SGDK frameInd was unchanged, so 0x74
-> 0x78 could keep gray baked tiles or closed-colour + open-black.

Usage (from zanac-md):
    python tools/test_luster18_open_anim.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
REB = ROOT / "tools" / "rebuild_sprites.py"
PNG = ROOT / "res" / "sprites" / "objs.png"
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


def running_body(n: int = 96):
    """7cd8: DEC then close+fire on 0, open on CP 8. Init +1d=0x30."""
    clock = 0x30
    prim, compl = 0x74, 0x7C
    seq = []
    fires = []
    for i in range(n):
        clock = (clock - 1) & 0xFF
        fired = False
        if clock == 0:
            clock = 0x30
            prim, compl = 0x74, 0x7C
            fired = True
            fires.append(i)
        if clock == 8:
            prim, compl = 0x78, 0x80
        seq.append((clock, prim, compl, fired))
    return seq, fires


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    reb = REB.read_text(encoding="utf-8")

    spawn = fn_span(ent, "static void spawn_luster(Slot *e, u8 type)")
    if not spawn:
        return fail("spawn_luster not found")
    if "e->clock = 0x30" not in spawn:
        return fail("type 18 7cc9 +1d must start 0x30")
    if "FRAME_LUSTER_A" not in spawn or "FRAME_LUSTER_A_C" not in spawn:
        return fail("7c14 start SAT 0x74 / 0x7C (FRAME_LUSTER_A / _C)")
    if re.search(r"type == 18.*?FRAME_LUSTER[^_]", spawn, re.S):
        return fail("type 18 must not start on FRAME_LUSTER (open / SAT 0x78)")
    print("  spawn type 18: +1d=0x30 SAT 0x74/0x7C closed")

    step = fn_span(ent, "static void luster_step(Slot *e)")
    if not step:
        return fail("luster_step not found")
    # Fire on zero, then CP 8. Do not fire at the open write.
    zero = step.find("if (!e->clock)")
    open8 = step.find("e->clock == 8")
    if zero < 0 or open8 < 0 or open8 < zero:
        return fail("7ce1 must DEC, close+fire on 0, then 7cfc CP 8")
    fire_blk = step[zero:open8]
    if "FRAME_LUSTER_A" not in fire_blk or "spawn_frag" not in fire_blk:
        return fail("7cea/7cf7: close SAT 0x74 + type37 on +1d==0")
    if "FRAME_LUSTER)" not in step[open8:]:
        return fail("7d04 open must spr_place FRAME_LUSTER (SAT 0x78)")
    if "FRAME_LUSTER_C" not in step[open8:]:
        return fail("7d08 open complement SAT 0x80 FRAME_LUSTER_C")
    print("  7cd8: close+type37 at 0; open 0x78/0x80 at +1d==8")

    jp, jf = running_body()
    if jf != [47, 95]:
        return fail("type37 must fire every 48 ticks (first at tick 47)")
    open_ticks = [t for t, (c, p, m, f) in enumerate(jp) if p == 0x78]
    if len(open_ticks) != 16:
        return fail("open SAT 0x78 must last 8 ticks per 48 (got %d in 96)"
                    % len(open_ticks))
    # First cycle: ticks 40..47 are clock 8..1 open; tick 47 is last open
    # BEFORE the DEC-to-0 close+fire. Wait: tick i DECs first.
    # Start 0x30. i=0: clock=0x2F closed. After 40 DECs clock=8 (i=39).
    # i=39: clock=8 open. i=46: clock=1 open. i=47: clock=0 -> 0x30 close+fire.
    if jp[39][1] != 0x78 or jp[46][1] != 0x78:
        return fail("open window must be clock 8..1 (ticks 39..46)")
    if jp[47][1] != 0x74 or not jp[47][3]:
        return fail("tick 47 must close SAT 0x74 and fire type37")
    if jp[47][0] != 0x30:
        return fail("after fire +1d reloads 0x30 (not 8)")
    print("  sequence: 40 closed + 8 open; fire on close, not on open")

    place = fn_span(ent, "static void spr_place(Slot *s, u16 frame)")
    if not place:
        return fail("spr_place not found")
    # Frame-change path must remap (type 18 open is baked 14, +04 nibble 11).
    if "else if (s->cram_nib)" in place and "spr_upload_color(s);" not in place.split(
        "else if (s->cram_nib)"
    )[-1]:
        # old pattern: only same-frame upload
        pass
    if "else" not in place or "spr_upload_color(s)" not in place:
        return fail("spr_place must spr_upload_color on non-CRAM frame change")
    if re.search(
        r"if \(prev == \(s16\)frame\)\s*\n\s*spr_upload_color\(s\);\s*\n"
        r"\s*else if \(s->cram_nib\)",
        place,
    ):
        return fail("do not remap only when frameInd is unchanged (18 open stays gray)")
    if "xor_cram_paint" not in place:
        return fail("KEEP: CRAM-bound SAT-name change still xor_cram_paint")
    if "mdx = dx" not in fn_span(ent, "static void spr_sync(Slot *s)") or "":
        return fail("KEEP: type 18 complement draw X = primary")
    print("  spr_place: remap on 0x74->0x78; KEEP xor_cram_paint + dual-SAT X")

    colors = re.search(
        r"static const u8 k_frame_color\[FRAME_N\] = \{([^}]+)\}",
        re.sub(r"/\*.*?\*/", "", ent, flags=re.S),
    )
    if not colors:
        return fail("k_frame_color not found")
    cols = [int(x) for x in re.findall(r"\d+", colors.group(1))]
    if cols[3] != 14:
        return fail("FRAME_LUSTER baked must stay TMS 14 (types 16/17 0x8E)")
    if cols[53] != 11:
        return fail("FRAME_LUSTER_A baked must stay TMS 11 (type 18 0x8B)")
    if cols[3] == 11:
        return fail("do not re-bake FRAME_LUSTER as 11 (breaks type 16/17)")
    print("  bake: FRAME_LUSTER=14 FRAME_LUSTER_A=11 (18 remaps 14->11)")

    if "(30, 14, False)" not in reb or "(29, 11, False)" not in reb:
        return fail("rebuild_sprites must keep pat 30/29 as LUSTER / LUSTER_A")
    if "(32, 1, True)" not in reb or "(31, 1, True)" not in reb:
        return fail("rebuild_sprites must keep pat 32/31 complements")

    try:
        from PIL import Image
    except ImportError:
        return fail("Pillow required to prove objs.png vs Japan pats")

    sys.path.insert(0, str(ROOT / "tools"))
    from extract_map_scripts import parse_asm, decompress

    asm_path = next((p for p in ASM_CANDIDATES if p.is_file()), None)
    if not asm_path:
        return fail("zanac.asm required for pat 29-32 evidence")
    asm = asm_path.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"LD\s+\(IX\+0x03\),\s*0x74\s*;\s*0x7cea", asm, re.I):
        return fail("zanac.asm 7cea is not SAT 0x74")
    if not re.search(r"LD\s+\(IY\+0x03\),\s*0x7c\s*;\s*0x7cee", asm, re.I):
        return fail("zanac.asm 7cee is not marker 0x7C")
    if not re.search(r"LD\s+A,\s*0x25\s*;\s*0x7cf7", asm, re.I):
        return fail("zanac.asm 7cf7 is not type 37")
    if not re.search(r"LD\s+\(IX\+0x03\),\s*0x78\s*;\s*0x7d04", asm, re.I):
        return fail("zanac.asm 7d04 is not SAT 0x78")
    if not re.search(r"LD\s+\(IY\+0x03\),\s*0x80\s*;\s*0x7d08", asm, re.I):
        return fail("zanac.asm 7d08 is not marker 0x80")
    print("  zanac.asm: 7cea 0x74 / 7d04 0x78 / 7cf7 type37")

    rom = parse_asm(asm_path)
    raw = decompress(rom, 0x6976, 0x70B8, max_out=4096)
    pats = [raw[i * 32 : (i + 1) * 32] for i in range(64)]

    def pat_bits(pat: bytes) -> set[tuple[int, int]]:
        bits: set[tuple[int, int]] = set()
        for y in range(16):
            left, right = pat[y], pat[16 + y]
            for x in range(8):
                if left & (0x80 >> x):
                    bits.add((x, y))
                if right & (0x80 >> x):
                    bits.add((8 + x, y))
        return bits

    im = Image.open(PNG)

    def png_bits(idx: int, body: bool) -> set[tuple[int, int]]:
        fr = im.crop((idx * 16, 0, (idx + 1) * 16, 16))
        pix = list(fr.getdata())
        out: set[tuple[int, int]] = set()
        for y in range(16):
            for x in range(16):
                v = pix[y * 16 + x]
                if body and v > 1:
                    out.add((x, y))
                if not body and v == 1:
                    out.add((x, y))
        return out

    pairs = (
        (53, 29, True, "FRAME_LUSTER_A closed"),
        (3, 30, True, "FRAME_LUSTER open"),
        (54, 31, False, "FRAME_LUSTER_A_C"),
        (29, 32, False, "FRAME_LUSTER_C"),
    )
    for fi, pat, body, name in pairs:
        if png_bits(fi, body) != pat_bits(pats[pat]):
            return fail("%s objs.png != Japan pat %d" % (name, pat))
    print("  objs.png: pats 29/31 closed, 30/32 open match Japan 0x6976")

    # KEEP dual-SAT X from #115
    sync = fn_span(ent, "static void spr_sync(Slot *s)")
    if not sync or "mdx = dx" not in sync:
        return fail("KEEP: spr_sync complement X = primary")
    if "mode_draw_x(s->x, 0x81)" in sync:
        return fail("KEEP: do not recompute complement X from 0x81")
    print("  KEEP: #115 complement draw X = primary")

    print("ok: type 18 open anim is Japan 7cd8 SAT 0x74->0x78, fire on close")
    return 0


if __name__ == "__main__":
    sys.exit(main())
