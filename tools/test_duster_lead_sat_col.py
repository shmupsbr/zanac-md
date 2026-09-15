#!/usr/bin/env python3
"""Type 10/20/37/38/41 write SAT +04 so Early Clock applies.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type10_duster 0x7a48: LD (IX+0x04), 0x89
  handler_type20_lead_homing 0x8672: LD (IX+0x04), 0x8F
  handler_type37_lead_bullet 0x84eb: LD (IX+0x04), 0x8F
  handler_type38_burst_fragment 0x8513: LD (IX+0x04), 0x8F
  handler_type41_pair_fragment 0x8539: LD (IX+0x04), 0x8F
  Type 42 CALL 84e3; type 43 CALL 8507 — same +04.

  TMS SAT colour bit7 = Early Clock (draw at SAT_X-32). Port mode_draw_x
  uses sat_col bit7. Old spawn left sat_col=0, so dusters/leads drew
  32px right of the MSX SAT. k_frame_color already bakes nibble 9 / 15.

  Type 21 init 0x863b does not write +04 (active 0x8659 is R-nibble|0x80).
  Type 9 umber morph stays off. Types 7/8 Yvel SAT morph stays.

Usage (from zanac-md):
    python tools/test_duster_lead_sat_col.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
MAPC = ROOT / "src" / "map_script.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def fn_body(src: str, sig: str) -> str | None:
    m = re.search(rf"{re.escape(sig)}\n\{{(.*?)\n\}}", src, re.S)
    return m.group(1) if m else None


def main() -> int:
    fails = 0
    src = ENTITY.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")

    duster = fn_body(src, "static void spawn_duster(Slot *e)")
    if not duster:
        fail("spawn_duster not found")
        return 1
    if "e->sat_col = 0x89" not in duster:
        fail("spawn_duster must write sat_col 0x89 (7a48)")
        fails += 1
    else:
        print("  spawn_duster: sat_col 0x89 (7a48)")
    if duster.find("e->sat_col = 0x89") > duster.find("spr_place"):
        fail("spawn_duster sat_col must be set before spr_place (EC on first frame)")
        fails += 1

    lead20 = fn_body(src, "static void spawn_lead20(s16 x, s16 y)")
    if not lead20 or ("c->sat_col = 0x8F" not in lead20 and "ebullet_apply_vis(c)" not in lead20):
        fail("spawn_lead20 must write sat_col 0x8F (8672) via apply_vis")
        fails += 1
    else:
        print("  spawn_lead20: sat_col via apply_vis (8672)")

    e37 = fn_body(src, "static void spawn_ebullet_dir(s16 x, s16 y, u8 dir)")
    if not e37 or ("e->sat_col = 0x8F" not in e37 and "ebullet_apply_vis(e)" not in e37):
        fail("spawn_ebullet_dir must write sat_col 0x8F (84eb) via apply_vis")
        fails += 1
    else:
        print("  spawn_ebullet_dir: sat_col via apply_vis (84eb)")

    frag = fn_body(src, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not frag:
        fail("init_frag not found")
        return 1
    if "ebullet_apply_vis" not in frag:
        fail("init_frag must write sat_col 0x8F for bolinhas via apply_vis")
        fails += 1
    else:
        print("  init_frag: apply_vis (NORMAL 0x8F / HIGH 8659)")
    if re.search(r"if\s*\(\s*variant\s*==\s*21\s*\)\s*\n\s*e->sat_col", frag):
        fail("init_frag must not invent type 21 +04 (863b writes none)")
        fails += 1

    stream = re.search(
        r"else if \(t == 20\)\n    \{(.*?)else if \(t == 56\)",
        src,
        re.S,
    )
    if not stream or (
        "e->sat_col = 0x8F" not in stream.group(1)
        and "ebullet_apply_vis(e)" not in stream.group(1)
    ):
        fail("stream type 20 must write sat_col 0x8F (8672) via apply_vis")
        fails += 1
    else:
        print("  spawn_from_type 20: sat_col 0x8F (8672)")

    asm = load_asm()
    if asm:
        for addr, needle in (
            ("0x7a48", "0x89"),
            ("0x8672", "0x8f"),
            ("0x84eb", "0x8f"),
            ("0x8513", "0x8f"),
            ("0x8539", "0x8f"),
        ):
            if not re.search(rf"{needle}\s*;\s*{addr}", asm, re.I):
                fail(f"zanac.asm {addr} is not {needle}")
                fails += 1
        else:
            print("  zanac.asm +04: 7a48=0x89; 8672/84eb/8513/8539=0x8F")

    # Leave-alones from PR #50 / #49 / #48 / #46 / #47.
    step = re.search(r"static void umber_step\(Slot \*e\)\n\{(.*?)\n\}", src, re.S)
    if not step:
        fail("umber_step not found")
        fails += 1
    else:
        body = step.group(1)
        if "FRAME_UMBER_B" not in body:
            fail("umber 7/8 SAT morph was reverted")
            fails += 1
        elif "e->variant == 9" in body.split("if (e->variant == 7 || e->variant == 8)")[0]:
            fail("umber_step morph must not run on type 9")
            fails += 1
        else:
            print("  umber_step: 7/8 morph stays; type 9 no morph")

    pd = re.search(r"static void pairdesc_step\(Slot \*e\)\n\{(.*?)\n\}", src, re.S)
    if not pd or "dir - 1" not in pd.group(1) or "dir + 1" not in pd.group(1):
        fail("pairdesc 57/58 convert dirs were reverted")
        fails += 1
    else:
        print("  pairdesc_step: aim-1 / aim+1 / aim stays")

    md = re.search(r"static const u8 k_stealth_dir\[4\] = \{([^}]+)\}", src)
    if not md:
        fail("k_stealth_dir not found")
        fails += 1
    else:
        ds = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\b\d+\b", md.group(1))]
        if ds != [2, 6, 4, 4]:
            fail(f"k_stealth_dir {ds} want [2, 6, 4, 4]")
            fails += 1
        else:
            print("  k_stealth_dir: [2, 6, 4, 4] stays")

    for name, pat in (
        ("spawn_spawner", r"static void spawn_spawner\(Slot \*e\)\n\{(.*?)\n\}"),
        (
            "spawn_spawner_cmd1",
            r"static void spawn_spawner_cmd1\(Slot \*e, u8 emit, u8 count, u8 interval\)\n\{(.*?)\n\}",
        ),
    ):
        m = re.search(pat, src, re.S)
        if not m:
            fail(f"{name} not found")
            fails += 1
            continue
        if re.search(r"spr_place\s*\(\s*e\s*,\s*FRAME_FIRE\s*\)", m.group(1)):
            fail(f"{name} spr_place(FRAME_FIRE) was restored")
            fails += 1
        elif "e->sat_col = 0;" not in m.group(1):
            fail(f"{name} sat_col=0 was removed")
            fails += 1
        else:
            print(f"  {name}: sat_col 0, no FRAME_FIRE")

    fn = re.search(
        r"static void cmd_spawn_ctrl\(u8 cmd, const u8 \*ops\)\n\{(.*?)\n\}",
        mapc,
        re.S,
    )
    if not fn or "cmd_place_tiles" not in fn.group(1):
        fail("cmd_spawn_ctrl bit2 -> cmd_place_tiles was reverted")
        fails += 1
    else:
        print("  cmd_spawn_ctrl: bit2 still falls into cmd_place_tiles")

    if "mode_letter_attr" in src and re.search(
        r"for\s*\(.*\)\s*\{[^}]*mode_letter_attr", src, re.S
    ):
        fail("playfield-wide mode_letter_attr fill must stay gone")
        fails += 1

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
