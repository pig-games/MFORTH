#!/usr/bin/env python3
"""
Convert an Intel HEX file to a fixed-size binary image, filling gaps with a chosen value.
MFORTH expects a 32 KiB ROM (0x8000 bytes). ToolLib.ROM reads exactly 32768 bytes. (repo source)
"""
from __future__ import annotations
import argparse, pathlib, sys, re

def parse_hex_line(line: str):
    line=line.strip()
    if not line or not line.startswith(':'):
        return None
    b=bytes.fromhex(line[1:])
    ln=b[0]
    addr=(b[1]<<8)|b[2]
    rectype=b[3]
    data=b[4:4+ln]
    # checksum ignored (last byte)
    return ln, addr, rectype, data

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("hex", help="Input .hex (Intel HEX)")
    ap.add_argument("bin", help="Output .bin")
    ap.add_argument("--size", default="0x8000", help="Output size, default 0x8000")
    ap.add_argument("--fill", default="0x00", help="Fill byte for gaps, default 0x00")
    args=ap.parse_args()
    size=int(args.size,0)
    fill=int(args.fill,0) & 0xFF

    mem=bytearray([fill]*size)
    upper=0
    with open(args.hex,'r',encoding='utf-8',errors='ignore') as f:
        for line in f:
            rec=parse_hex_line(line)
            if not rec: 
                continue
            ln, addr, rectype, data = rec
            if rectype==0x00: # data
                a=upper+addr
                if a+ln>size:
                    raise SystemExit(f"HEX record writes beyond size: addr=0x{a:X} len={ln} size={size}")
                mem[a:a+ln]=data
            elif rectype==0x01: # EOF
                break
            elif rectype==0x04: # extended linear address
                upper=((data[0]<<8)|data[1])<<16
            else:
                # ignore other types
                pass
    pathlib.Path(args.bin).write_bytes(mem)

if __name__=="__main__":
    main()
