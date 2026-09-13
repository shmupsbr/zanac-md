#!/usr/bin/env python3
"""Credits 0x47AA is skip-N, not a 0-based name list.

zanac.asm LAB_46F5: B = (HL) from 0x4775, HL = 0x47AA, DJNZ skip length-
prefixed records. First record at 0x47AA is length 0 (blank row).
IDs 0x12-0x16 are the 18-byte logo nametable rows at 0x4826; 0x17 is
18 spaces. load_logo_tiles 0x5C3C writes PGT at 0x580 (tile 0xB0).

MD used to start k_cred_str at GAME DESIGN (off-by-one) and drop IDs
>= 17, so page 1 printed PROGRAM / GAME DESIGN / JEMINI / MIYAMOTO /
COMPILE and the last page had no ZANAC logo.

Usage (from zanac-md):
    python tools/test_credits_47aa.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
ASM = Path("/tmp/zanac-re/source/zanac.asm")

# credits_control_table 0x4775 through the second 0xFF.
MSX_CTRL = bytes(
    (
        0x01, 0x00, 0x06, 0x0A, 0x07, 0xFF,
        0x02, 0x00, 0x0A, 0x07, 0xFF,
        0x10, 0x00, 0x0B, 0xFF,
        0x04, 0x00, 0x07, 0xFF,
        0x04, 0x02, 0x00, 0x07, 0xFF,
        0x03, 0x00, 0x06, 0x0C, 0xFF,
        0x0E, 0x00, 0x0F, 0x11, 0x09, 0xFF,
        0x17, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
        0x00, 0x05, 0x00, 0x0A, 0x00, 0x00, 0x0D, 0x08, 0x0D, 0xFF,
        0xFF,
    )
)

# Skip-N names from 0x47AA. [0] is the length-0 blank.
MSX_STR = (
    "",
    "GAME DESIGN",
    "PROGRAM",
    "GRAPHICS",
    "SOUND",
    "DIRECTOR",
    "JANUS",
    "JEMINI",
    "COMPILE",
    "WAO",
    "MOO",
    "MIYAMOTO",
    "YORIKI",
    "       ",
    "THANKS",
    "PAL",
    "MUSIC",
    "LUNARIAN",
)

# 0x4826: five 0x12-prefixed 18-byte logo rows (ids 18-22).
MSX_LOGO = (
    bytes((0x20, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7,
           0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xB2, 0xB2, 0xBD, 0x20)),
    bytes((0x20, 0x20, 0x20, 0xBE, 0xBF, 0xC0, 0xC1, 0xC2, 0xC3,
           0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0x20, 0x20, 0x20, 0x20)),
    bytes((0x20, 0x20, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF,
           0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0x20, 0x20, 0x20, 0x20)),
    bytes((0x20, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xDB, 0xDC,
           0xDD, 0xDE, 0xD9, 0xDF, 0xE0, 0xD9, 0xD9, 0xE1, 0x20)),
    bytes((0xE2, 0xE3, 0xE4, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5,
           0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE6)),
)

PAGE0 = ("GAME DESIGN", "", "JANUS", "MOO", "JEMINI")

HEX = re.compile(r"0x([0-9A-Fa-f]+)")
DB_RE = re.compile(r"\bDB\s+(.+?);\s*0x([0-9A-Fa-f]+)")


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def parse_u8_block(src: str, name: str) -> list[int]:
    m = re.search(
        rf"static const u8 {name}\[\S*\] = \{{(.*?)\}};",
        src,
        re.S,
    )
    if not m:
        raise SystemExit(f"{name} not found")
    return [int(h, 16) for h in HEX.findall(m.group(1))]


def parse_cred_str(src: str) -> list[str]:
    m = re.search(
        r"static const char \*const k_cred_str\[\] = \{(.*?)\};",
        src,
        re.S,
    )
    if not m:
        raise SystemExit("k_cred_str not found")
    return re.findall(r'"([^"]*)"', m.group(1))


def parse_logo_rows(src: str) -> list[bytes]:
    m = re.search(
        r"static const u8 k_cred_logo\[5\]\[CRED_LOGO_W\] = \{(.*?)\};",
        src,
        re.S,
    )
    if not m:
        raise SystemExit("k_cred_logo not found")
    vals = [int(h, 16) for h in HEX.findall(m.group(1))]
    if len(vals) != 5 * 18:
        raise SystemExit(f"k_cred_logo has {len(vals)} bytes, want 90")
    return [bytes(vals[i * 18 : (i + 1) * 18]) for i in range(5)]


def pages_from_ctrl(ctrl: bytes, strs: list[str]) -> list[list[str]]:
    pages: list[list[str]] = []
    cur: list[str] = []
    for b in ctrl:
        if b == 0xFF:
            pages.append(cur)
            cur = []
            continue
        if b < len(strs):
            cur.append(strs[b])
        else:
            cur.append(f"<{b}>")
    if pages and pages[-1] == []:
        pages.pop()
    return pages


def load_asm_region(path: Path, lo: int, hi: int) -> bytes | None:
    if not path.is_file():
        return None
    rom = bytearray(hi - lo + 1)
    filled = bytearray(hi - lo + 1)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = DB_RE.search(line)
            if not m:
                continue
            addr = int(m.group(2), 16)
            vals = [int(h, 16) for h in HEX.findall(m.group(1))]
            for i, v in enumerate(vals):
                a = addr + i
                if lo <= a <= hi:
                    rom[a - lo] = v & 0xFF
                    filled[a - lo] = 1
    if not all(filled):
        missing = [lo + i for i, ok in enumerate(filled) if not ok]
        raise SystemExit(f"zanac.asm gaps in 0x{lo:04X}-0x{hi:04X}: {missing[:8]}")
    return bytes(rom)


def parse_lenpref(blob: bytes) -> list[bytes]:
    out: list[bytes] = []
    i = 0
    while i < len(blob):
        n = blob[i]
        i += 1
        if i + n > len(blob):
            break
        out.append(blob[i : i + n])
        i += n
    return out


def main() -> int:
    src = MAPC.read_text(encoding="utf-8")
    ctrl = bytes(parse_u8_block(src, "k_cred_ctrl"))
    strs = parse_cred_str(src)
    logo = parse_logo_rows(src)

    if ctrl != MSX_CTRL:
        return fail(f"k_cred_ctrl != 0x4775 ({ctrl.hex(' ')})")
    if strs != list(MSX_STR):
        return fail(f"k_cred_str skip-N mismatch: {strs}")
    if "#define CRED_NSTR   18" not in src:
        return fail("CRED_NSTR must be 18 (empty + 17 names)")
    if logo != list(MSX_LOGO):
        return fail("k_cred_logo != 0x4826 rows")

    pages = pages_from_ctrl(ctrl, strs)
    if tuple(pages[0]) != PAGE0:
        return fail(f"page 0 must be {PAGE0}, got {tuple(pages[0])}")
    if pages[0][0] != "GAME DESIGN" or pages[0][1] != "":
        return fail("page 0 must start GAME DESIGN / blank (skip 1 then 0)")

    # Last page uses logo ids; they must not be treated as names.
    if "CRED_LOGO0" not in src or "id >= CRED_LOGO0 && id <= CRED_LOGO4" not in src:
        return fail("draw path must punch ids 18-22 as logo rows")
    if "hud_put_tile(BG_A, (u16)(3 + t), row, tiles[t])" not in src:
        return fail("logo content starts at column 3 (MSX x=2 + leading 0x20)")
    if "credits_ensure_logo_tiles" not in src:
        return fail("credits must load 0x5C3C logo tiles")
    if "logo_tiles" not in src or "LOGO_TILE_MSX_FIRST" not in src:
        return fail("credits logo load must use logo_tiles at tile 0xB0")
    if "s_bg_base + LOGO_TILE_MSX_FIRST" not in src:
        return fail("logo PGT overlay is s_bg_base + 0xB0")

    # Do not hook 412A playfield load (KEEP / title-start R8).
    warp = re.search(r"static void warp_play_dest_bgm\(void\)\s*\{(.*?)^\}", src, re.S | re.M)
    if not warp:
        return fail("warp_play_dest_bgm not found")
    if "logo_tiles" in warp.group(1) or "credits_ensure" in warp.group(1):
        return fail("do not load logo tiles on the 412A warp arm")

    asm = load_asm_region(ASM, 0x4775, 0x4897)
    if asm is not None:
        if asm[: len(MSX_CTRL)] != MSX_CTRL:
            return fail("zanac.asm 0x4775 != expected control table")
        recs = parse_lenpref(asm[0x47AA - 0x4775 :])
        if recs[0] != b"":
            return fail("0x47AA first record must be length 0")
        names = [r.decode("ascii") for r in recs[:18]]
        if names != list(MSX_STR):
            return fail(f"zanac.asm 0x47AA names {names}")
        for i, row in enumerate(MSX_LOGO):
            rec = recs[18 + i]
            if rec != row:
                return fail(f"zanac.asm logo row {18 + i} mismatch")
        if recs[23] != b" " * 18:
            return fail("id 23 must be 18 spaces")
        print("zanac.asm 0x4775/0x47AA/0x4826: match")
    else:
        print("zanac.asm not present; locked to listed 0x4775/0x47AA bytes")

    print("credits 47AA skip-N + 0x4826 logo rows: ok")
    print("  page 0:", " / ".join(repr(s) if s == "" else s for s in pages[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
