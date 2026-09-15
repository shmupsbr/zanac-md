#!/usr/bin/env python3
"""Type 21 FRAME_LIGHT_BAR (`<===>`) always colour-cycles.

Filipe after #144: white bolinhas OK, but the horizontal bar shot
(not the disc) TEM color cycle and must not enter BULLET VISIBILITY.
#143/#144 NORMAL lock wrongly forced it white.

Japan v1 (zanac-re SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type21_light_bar 0x8635:
    8639  JR NZ,0x8659
    863b  init: +17=4, SAT 0x18, no +04, 4cf7 speed 4, SET 7, ev0x16
    8659  LD A,R / AND 0x0F / OR 0x80 / LD (IX+04),A   ; always

  handler_type45_light_bar_var: CALL 850b +04=0x8F (vis-gated white).
  Type 45 pulses SAT 0x18/0x20 (bar/med) but colour stays 0x8F.

Usage (from zanac-md):
    python tools/test_type21_always_cycle.py
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
    Path.home() / "zanac-re" / "source/zanac.asm",
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

    bar = fn_span(ent, "static int ebullet_light_bar(const Slot *s)")
    if not bar or "21" not in bar:
        return fail("ebullet_light_bar must be type 21")
    if "options_bullet" in bar:
        return fail("ebullet_light_bar must not read BULLET VISIBILITY")
    print("  ebullet_light_bar: type 21, no vis")

    boli = fn_span(ent, "static int ebullet_bolinha(const Slot *s)") or ""
    if re.search(r"v\s*==\s*21", boli):
        return fail("type 21 must not sit in ebullet_bolinha (vis list)")
    if "45" not in boli:
        return fail("type 45 stays vis-gated (Japan 0x8F)")
    print("  ebullet_bolinha: discs+45; not type 21")

    lock = fn_span(ent, "static int ebullet_normal_lock(const Slot *s)") or ""
    if "ebullet_bolinha" not in lock:
        return fail("normal_lock is bolinha && !HIGH")
    if "21" in lock and "light_bar" not in lock:
        return fail("normal_lock must not name type 21")
    print("  ebullet_normal_lock: does not catch the `<===>` bar")

    cram = fn_span(ent, "static int ebullet_cram_shot(const Slot *s)") or ""
    if "ebullet_light_bar" not in cram:
        return fail("ebullet_cram_shot must always CRAM type 21")
    print("  ebullet_cram_shot: type 21 always PAL2[4]")

    apply = fn_span(ent, "static void ebullet_apply_vis(Slot *e)") or ""
    if "ebullet_light_bar" not in apply:
        return fail("apply_vis must 8659 type 21 first")
    # The always-walk must sit before the vis-gated pair.
    light_at = apply.find("ebullet_light_bar")
    high_at = apply.find("options_bullet_high")
    if light_at < 0 or high_at < 0 or light_at > high_at:
        return fail("type 21 8659 must run before the vis-gated 0x8F/HIGH pair")
    if apply[light_at:high_at].count("ebullet_8659") < 1:
        return fail("type 21 arm must 8659")
    print("  apply_vis: type 21 8659 always, then vis-gated discs/45")

    if "FRAME_LIGHT_BAR 21" in opth and "does not enter" not in opth:
        return fail("options.h must exclude type 21 from vis scope")
    print("  options.h: type 21 not in BULLET VISIBILITY")

    asm = load_asm()
    if asm:
        if not re.search(r"JR\s+NZ,\s*0x8659\s*;\s*0x8639", asm, re.I):
            return fail("zanac.asm 8639 is not JR NZ 8659")
        if not re.search(r"LD\s+A,\s*R\s*;\s*0x8659", asm, re.I):
            return fail("zanac.asm 8659 is not LD A,R")
        if not re.search(r"LD\s+\(IX\+0x04\),\s*0x8f\s*;\s*0x8513", asm, re.I):
            return fail("zanac.asm 8513 (type 45 via 850b) must stay 0x8F")
        print("  zanac.asm: type 21 always 8659; type 45 0x8F")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    print("ok: `<===>` type 21 always colour-cycles; vis does not gate it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
