#!/usr/bin/env python3
"""
Extract a symbol table from an opForge .lst file into MFORTH's .SYM format:
  SYMBOLNAME <hexaddress>
(one per line, address is hex without 0x, case-insensitive ok)

opForge's README: listing includes a symbol table. citeturn1view0
We parse common patterns seen in assembler listings.
"""
from __future__ import annotations
import argparse, re, pathlib, sys

# Match patterns like:
#   SYMBOL 1234
#   SYMBOL = 1234
#   SYMBOL: 1234
#   1234 SYMBOL
PATTERNS = [
    re.compile(r'^\s*([A-Za-z_.$][\w.$]*)\s*[:=]?\s+([0-9A-Fa-f]{4})\b'),
    re.compile(r'^\s*([0-9A-Fa-f]{4})\s+([A-Za-z_.$][\w.$]*)\b'),
]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("lst", help="Input listing (.lst)")
    ap.add_argument("sym", help="Output symbols (.sym)")
    args=ap.parse_args()

    syms={}
    for line in pathlib.Path(args.lst).read_text(errors="ignore").splitlines():
        line=line.rstrip()
        for rx in PATTERNS:
            m=rx.match(line)
            if not m: 
                continue
            if rx is PATTERNS[0]:
                name, addr = m.group(1), m.group(2)
            else:
                addr, name = m.group(1), m.group(2)
            # filter obvious noise
            if name.lower().startswith(("noname.","link_","last_")):
                continue
            # keep last occurrence
            syms[int(addr,16)] = name
            break

    if not syms:
        raise SystemExit("ERROR: Could not find any symbols in listing; update parse patterns in tools_mac/opForge_lst_to_sym.py")

    out_lines=[]
    for addr in sorted(syms.keys()):
        out_lines.append(f"{syms[addr]} {addr:04X}")
    pathlib.Path(args.sym).write_text("\n".join(out_lines)+"\n", encoding="ascii")

if __name__=="__main__":
    main()
