#!/usr/bin/env python3
"""Convert TASM-style MFORTH sources into asm485 syntax."""

import argparse
import re
import sys
from pathlib import Path

INDENT = "            "  # 12 spaces to match asm85 formatting in this repo

OPCODES = {
    # 8080/8085 core
    "ACI", "ADC", "ADD", "ADI", "ANA", "ANI", "CALL", "CC", "CM", "CMA", "CMC",
    "CMP", "CNC", "CNZ", "CP", "CPE", "CPI", "CPO", "CZ", "DAA", "DAD",
    "DCR", "DCX", "DI", "EI", "HLT", "IN", "INR", "INX", "JC", "JM", "JMP",
    "JNC", "JNZ", "JP", "JPE", "JPO", "JZ", "LDA", "LDAX", "LHLD", "LXI",
    "MOV", "MVI", "NOP", "ORA", "ORI", "OUT", "PCHL", "POP", "PUSH", "RAL",
    "RAR", "RC", "RET", "RLC", "RM", "RNC", "RNZ", "RP", "RPE", "RPO",
    "RRC", "RST", "RZ", "SBB", "SBI", "SHLD", "SPHL", "STA", "STAX",
    "STC", "SUB", "SUI", "XCHG", "XRA", "XRI", "XTHL",
    # 8085
    "RIM", "SIM",
    # undocumented 8085 (handled separately but also treated as opcodes)
    "DSUB", "LDEH", "LDES", "LHLX", "SHLX", "RDEL",
}

DIRECTIVES = {
    "ORG", "EQU", "SET", "DB", "DW", "DS", "END", "INCLUDE",
    "IF", "ELSE", "ENDIF", "ELSEIF", "IFDEF", "IFNDEF", "DEFINE", "UNDEF",
}

HEX_SUFFIX_RE = re.compile(r"\b([0-9A-Fa-f]+)[hH]\b")
HEX_0X_RE = re.compile(r"\b0x([0-9A-Fa-f]+)\b")
HEX_DOLLAR_RE = re.compile(r"\$([0-9A-Fa-f]+)\b")

LABEL_ORG_RE = re.compile(r"^(\s*)([A-Za-z_.$][\w.$]*):\s*(?:\.?(ORG))\b(.*)$", re.IGNORECASE)
LABEL_EQU_RE = re.compile(r"^(\s*)([A-Za-z_.$][\w.$]*):\s*(EQU|SET)\b(.*)$", re.IGNORECASE)

UNDOC_OP_RE = re.compile(
    r"^(\s*)([A-Za-z_.$][\w.$]*:)?(\s*)(DSUB|LDEH|LDES|LHLX|SHLX|RDEL)\b(.*)$",
    re.IGNORECASE,
)

PREPROC_RE = re.compile(
    r"^(\s*)#?(IFDEF|IFNDEF|IF|ELSEIF|ELSE|ENDIF|DEFINE|UNDEF|INCLUDE|ECHO)\b",
    re.IGNORECASE,
)
LABEL_RE = re.compile(r"^\s*#?(IFDEF|IFNDEF|IF|ELSEIF|ELSE|ENDIF)\s*:", re.IGNORECASE)
PREPROC_START = {"IFDEF", "IFNDEF"}
DIRECTIVES = {"DEFINE", "UNDEF", "INCLUDE", "ECHO"}
DOT_DIRECTIVE_RE = re.compile(r"\.(ORG|EQU|SET|BYTE|WORD|DB|DW|DS|END|INCLUDE|IFDEF|IFNDEF|IF|ELSEIF|ELSE|ENDIF|DEFINE|UNDEF)\b", re.IGNORECASE)

ADDINSTR_RE = re.compile(r"^(\s*)\.?ADDINSTR\b", re.IGNORECASE)
LINKTO_EMPTY_RE = re.compile(r"\bLINKTO\((.*),\s*\"\"\s*\)", re.IGNORECASE)
LABEL_LINE_RE = re.compile(r"^(\s*)([A-Za-z_.$][\w.$]*)(\s+)(.*)$")
LINKTO_DEFINE_RE = re.compile(
    r"^\s*#?DEFINE\s+LINKTO\(\s*prev\s*,\s*isimm\s*,\s*len\s*,\s*lastchar\s*,\s*revchars\s*\)",
    re.IGNORECASE,
)


def split_comment(line: str) -> tuple[str, str]:
    in_double = False
    in_single = False
    for i, ch in enumerate(line):
        if ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "'" and not in_double:
            in_single = not in_single
        if ch == ';' and not in_double and not in_single:
            return line[:i], line[i:]
    return line, ""


def normalize_hex(expr: str) -> str:
    def repl_suffix(m: re.Match) -> str:
        raw = m.group(1).upper()
        if raw[0] in "ABCDEF":
            raw = "0" + raw
        return f"{raw}H"

    def repl_0x(m: re.Match) -> str:
        raw = m.group(1).upper()
        if raw[0] in "ABCDEF":
            raw = "0" + raw
        return f"{raw}H"

    def repl_dollar(m: re.Match) -> str:
        raw = m.group(1).upper()
        if raw[0] in "ABCDEF":
            raw = "0" + raw
        return f"{raw}H"

    def apply(segment: str) -> str:
        segment = HEX_SUFFIX_RE.sub(repl_suffix, segment)
        segment = HEX_0X_RE.sub(repl_0x, segment)
        segment = HEX_DOLLAR_RE.sub(repl_dollar, segment)
        return segment

    out = []
    start = 0
    in_quote = False
    for i, ch in enumerate(expr):
        if ch == '"':
            if not in_quote:
                out.append(apply(expr[start:i]))
                in_quote = True
                start = i
            else:
                out.append(expr[start:i + 1])
                in_quote = False
                start = i + 1
    if in_quote:
        out.append(expr[start:])
    else:
        out.append(apply(expr[start:]))
    return "".join(out)


def space_shifts(expr: str) -> str:
    out = []
    i = 0
    in_quote = False
    while i < len(expr):
        ch = expr[i]
        if ch == '"':
            in_quote = not in_quote
            out.append(ch)
            i += 1
            continue
        if not in_quote and expr[i:i+2] in ("<<", ">>"):
            op = expr[i:i+2]
            out.append(f" {op} ")
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def convert_line(line: str) -> list[str]:
    if not line.strip():
        return [line]

    code, comment = split_comment(line)
    if not code.strip():
        return [line]

    # Drop .ADDINSTR lines (asm85 doesn't support custom mnemonics)
    if ADDINSTR_RE.match(code.strip()):
        return ["; " + line.lstrip()]

    # Remove dot directives (map .BYTE/.WORD to DB/DW)
    def map_dot(m: re.Match) -> str:
        directive = m.group(1).upper()
        if directive == "BYTE":
            return "DB"
        if directive == "WORD":
            return "DW"
        return directive
    code = DOT_DIRECTIVE_RE.sub(map_dot, code)

    # Normalize ECHO and prep IF/ELSEIF expressions (prefix handled later)
    if re.match(r"^\s*#?ECHO\b", code, re.IGNORECASE):
        code = re.sub(r"^\s*#?ECHO", "; ECHO", code, count=1, flags=re.IGNORECASE)
        return [code + ("\n" if not code.endswith("\n") else "")]

    if (
        re.match(r"^\s*#?IF\b", code, re.IGNORECASE)
        and not re.match(r"^\s*#?IF(N?DEF)\b", code, re.IGNORECASE)
        and not re.match(r"^\s*#?IF:", code, re.IGNORECASE)
    ):
        code = code.replace("!=", " NE ")
        code = code.replace(">", " GT ")

    # Replace undocumented opcodes inside DEFINE bodies
    if re.match(r"^\s*#?DEFINE\b", code):
        def repl_define(m: re.Match) -> str:
            op = m.group(0).upper()
            return {
                "LHLX": "DB 0EDH",
                "SHLX": "DB 0D9H",
                "DSUB": "DB 08H",
                "RDEL": "DB 18H",
            }.get(op, op)

        code = re.sub(r"\b(LHLX|SHLX|DSUB|RDEL)\b", repl_define, code, flags=re.IGNORECASE)

    # LINKTO(...,"") -> LINKTO0(...)
    code = LINKTO_EMPTY_RE.sub(r"LINKTO0(\1)", code)

    # Add missing label colons (e.g., "PLUSLOOP    JMP" -> "PLUSLOOP: JMP")
    if ":" not in code:
        m = LABEL_LINE_RE.match(code)
        if m:
            indent, label, ws, rest = m.groups()
            if indent:
                m = None
            if m:
                first = label.upper()
                second = re.split(r"\s+", rest.strip(), maxsplit=1)[0].upper()
                if (
                    first not in DIRECTIVES
                    and first not in OPCODES
                    and second in OPCODES
                ):
                    code = f"{indent}{label}: {rest.lstrip()}"

    # Convert label: ORG to ORG then label on next line
    m = LABEL_ORG_RE.match(code)
    if m:
        indent, label, _, rest = m.groups()
        rest = rest.rstrip()
        org_indent = indent if indent else " "
        org_line = f"{org_indent}ORG{rest}"
        org_line = normalize_hex(space_shifts(org_line))
        if comment:
            pad = re.search(r"(\s*)$", code).group(1)
            org_line += f"{pad}{comment}"
        return [org_line + "\n", f"{label}:\n"]

    # Remove colon from label on EQU/SET
    m = LABEL_EQU_RE.match(code)
    if m:
        indent, label, directive, rest = m.groups()
        code = f"{indent}{label} {directive.upper()}{rest}"

    # Preserve original spacing before comments
    comment_pad = ""
    if comment:
        m = re.search(r"(\s*)$", code)
        comment_pad = m.group(1)
        code = code.rstrip()

    # Translate undocumented opcodes to DB
    m = UNDOC_OP_RE.match(code)
    if m:
        indent, label, ws, op, rest = m.groups()
        label = label or ""
        ws = ws or ""
        if label and not ws and not label.endswith(":"):
            ws = " "
        op = op.upper()
        rest_raw = rest.rstrip()
        rest_stripped = rest.strip()
        if op == "DSUB":
            rep = "DB 08H"
        elif op == "RDEL":
            rep = "DB 18H"
        elif op == "LDEH":
            rep = f"DB 028H,{rest_raw}" if rest_stripped else "DB 028H"
        elif op == "LDES":
            rep = f"DB 038H,{rest_raw}" if rest_stripped else "DB 038H"
        elif op == "LHLX":
            rep = "DB 0EDH"
        elif op == "SHLX":
            rep = "DB 0D9H"
        else:
            rep = op
        code = f"{indent}{label}{ws}{rep}"

    # Normalize hex literals and spacing around shifts
    code = normalize_hex(code)
    code = space_shifts(code)

    # Remove trailing comma for DB/DW without reformatting spacing
    data_match = re.match(r"^(\s*(?:[A-Za-z_.$][\w.$]*:)?\s*)(DB|DW)\b(.*)$", code, re.IGNORECASE)
    if data_match:
        prefix, directive, rest = data_match.groups()

        def strip_trailing(segment: str) -> str:
            return re.sub(r",\s*$", "", segment)

        out = []
        start = 0
        in_quote = False
        for i, ch in enumerate(rest):
            if ch == '"':
                if not in_quote:
                    out.append(strip_trailing(rest[start:i]))
                    in_quote = True
                    start = i
                else:
                    out.append(rest[start:i + 1])
                    in_quote = False
                    start = i + 1
        if in_quote:
            out.append(rest[start:])
        else:
            out.append(strip_trailing(rest[start:]))
        code = f"{prefix}{directive.upper()}{''.join(out)}"

    # Auto-generate LINKTO0 define for kernel macro block
    extra_line = None
    if LINKTO_DEFINE_RE.match(code) and "LINKTO0" not in code:
        extra_line = code
        extra_line = re.sub(r"\bLINKTO\(", "LINKTO0(", extra_line, count=1, flags=re.IGNORECASE)
        extra_line = re.sub(
            r"prev\s*,\s*isimm\s*,\s*len\s*,\s*lastchar\s*,\s*revchars",
            "prev,isimm,len,lastchar",
            extra_line,
            flags=re.IGNORECASE,
        )
        extra_line = re.sub(
            r"10000000b\|lastchar\s*,\s*revchars",
            "10000000b|lastchar",
            extra_line,
            flags=re.IGNORECASE,
        )
        extra_line = extra_line.rstrip("\n")

    # Indent opcode-only lines starting at column 1
    stripped = code.lstrip()
    leading = code[: len(code) - len(stripped)]
    if not leading:
        token = re.split(r"\s+", stripped, maxsplit=1)[0]
        token_up = token.upper()
        if token_up in OPCODES:
            code = INDENT + stripped

    # Reattach comment
    if comment:
        code = f"{code}{comment_pad}{comment}"

    if "\\" in code and not re.match(r"^\s*#?DEFINE\b", code):
        segments = []
        current = []
        in_double = False
        in_single = False
        for ch in code:
            if ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "'" and not in_double:
                in_single = not in_single
            if ch == "\\" and not in_double and not in_single:
                segments.append("".join(current))
                current = []
                continue
            current.append(ch)
        segments.append("".join(current))

        indent = re.match(r"\s*", code).group(0)
        lines = []
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            lines.append(f"{indent}{seg}\n")
        if extra_line:
            lines.append(extra_line + "\n")
        return lines

    lines = [code + ("\n" if not code.endswith("\n") else "")]
    if extra_line:
        lines.append(extra_line + "\n")
    return lines


def convert_text(text: str) -> str:
    out_lines = []
    for line in text.splitlines(keepends=True):
        converted = convert_line(line)
        out_lines.extend(converted)
    return normalize_preproc_text("".join(out_lines))


def normalize_preproc_text(text: str) -> str:
    out = []
    stack: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith(";"):
            out.append(line)
            continue

        code, comment = split_comment(line)
        if not code.strip():
            out.append(line)
            continue

        line_ending = "\n" if line.endswith("\n") else ""
        if code.endswith("\n"):
            code = code[:-1]
        if comment.endswith("\n"):
            comment = comment[:-1]

        if LABEL_RE.match(code):
            if code.lstrip().startswith("#"):
                code = code.replace("#", "", 1)
            out.append(code + comment + line_ending)
            continue

        m = PREPROC_RE.match(code)
        if not m:
            out.append(line)
            continue

        indent = m.group(1)
        keyword = m.group(2).upper()
        rest = code[m.end():]
        has_hash = code.lstrip().startswith("#")
        cond_indent = indent if indent else "    "

        if keyword in DIRECTIVES:
            new_code = f"#{keyword}{rest}"
        elif keyword in PREPROC_START:
            stack.append("preproc")
            new_code = f"#{keyword}{rest}"
        elif keyword == "IF":
            stack.append("cond")
            new_code = f"{cond_indent}{keyword}{rest}"
        elif keyword in {"ELSE", "ELSEIF", "ENDIF"}:
            if stack:
                mode = stack[-1]
            else:
                mode = "preproc" if has_hash else "cond"
            if mode == "preproc":
                new_code = f"#{keyword}{rest}"
            else:
                new_code = f"{cond_indent}{keyword}{rest}"
            if keyword == "ENDIF" and stack:
                stack.pop()
        else:
            new_code = code

        out.append(new_code + comment + line_ending)
    return "".join(out)


def convert_file(src: Path, dst: Path | None) -> None:
    data = src.read_text(errors="ignore")
    converted = convert_text(data)
    if dst is None:
        sys.stdout.write(converted)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(converted)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert TASM-style MFORTH .asm files to asm85 syntax.")
    parser.add_argument("src", type=Path, help="Source file or directory")
    parser.add_argument("dst", nargs="?", type=Path, help="Destination file or directory")
    parser.add_argument("--in-place", action="store_true", help="Convert files in place (directory only)")
    args = parser.parse_args()

    if args.src.is_dir():
        if args.in_place:
            if args.dst is not None:
                parser.error("--in-place cannot be used with a destination path")
            for path in args.src.rglob("*.asm"):
                convert_file(path, path)
            return 0
        if args.dst is None:
            parser.error("destination directory required when converting a directory")
        for path in args.src.rglob("*.asm"):
            rel = path.relative_to(args.src)
            convert_file(path, args.dst / rel)
        return 0

    if args.dst is None:
        convert_file(args.src, None)
        return 0

    convert_file(args.src, args.dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
