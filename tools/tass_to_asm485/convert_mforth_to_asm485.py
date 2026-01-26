#!/usr/bin/env python3
"""Convert TASM-style MFORTH sources into asm485 syntax."""

import argparse
import re
import sys
from pathlib import Path

INDENT = "            "  # 12 spaces to match asm485 formatting in this repo

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
    "MACRO", "ENDMACRO", "SEGMENT", "ENDSEGMENT",
    "BYTE", "WORD", "CONST", "VAR",
}

HEX_SUFFIX_RE = re.compile(r"\b([0-9A-Fa-f]+)[hH]\b")
HEX_0X_RE = re.compile(r"\b0x([0-9A-Fa-f]+)\b")
HEX_DOLLAR_RE = re.compile(r"\$([0-9A-Fa-f]+)\b")

LABEL_ORG_RE = re.compile(r"^(\s*)([A-Za-z_.$][\w.$]*):\s*(?:\.?(ORG))\b(.*)$", re.IGNORECASE)
LABEL_EQU_RE = re.compile(r"^(\s*)([A-Za-z_.$][\w.$]*):\s*\.?(EQU|SET)\b(.*)$", re.IGNORECASE)
LABEL_ASSIGN_RE = re.compile(r"^(\s*)([A-Za-z_.$][\w.$]*)(\s+)\.?(EQU|SET)\b(.*)$", re.IGNORECASE)

UNDOC_OP_RE = re.compile(
    r"^(\s*)(?:([A-Za-z_.$][\w.$]*)(\s+))?(DSUB|LDEH|LDES|LHLX|SHLX|RDEL)\b(.*)$",
    re.IGNORECASE,
)

PREPROC_RE = re.compile(
    r"^(\s*)([#.])(IFDEF|IFNDEF|IF|ELSEIF|ELSE|ENDIF|DEFINE|UNDEF|INCLUDE|ECHO)\b",
    re.IGNORECASE,
)
LABEL_RE = re.compile(r"^\s*#?(IFDEF|IFNDEF|IF|ELSEIF|ELSE|ENDIF)\s*:", re.IGNORECASE)
DIRECTIVE_RE = re.compile(
    r"^(\s*(?:[A-Za-z_.$][\w.$]*:)?\s*)(\.?)(ORG|BYTE|WORD|DB|DW|DS|END)\b(?!\s*:)",
    re.IGNORECASE,
)
DEFINE_RE = re.compile(
    r"^(\s*)#?DEFINE\s+([A-Za-z_.$][\w.$]*)(?:\s*\(([^)]*)\))?\s*(.*)$",
    re.IGNORECASE,
)

ADDINSTR_RE = re.compile(r"^(\s*)\.?ADDINSTR\b", re.IGNORECASE)
LINKTO_EMPTY_RE = re.compile(r"\bLINKTO\((.*),\s*\"\"\s*\)", re.IGNORECASE)
LABEL_LINE_RE = re.compile(r"^(\s*)([A-Za-z_.$][\w.$]*)(\s+)(.*)$")
LABEL_DEF_RE = re.compile(r"^(\s*)([A-Za-z_.$][\w.$]*):(\s*)(.*)$")

REGISTERS = {
    "A", "B", "C", "D", "E", "H", "L", "M",
    "SP", "PSW", "AF",
}

MACRO_TOKENS = [
    "RESTORE",
    "REGPAIR",
    "PUSH",
    "FETCH",
    "PICK",
    "SAVE",
    "LINK",
    "NEXT",
    "INX",
    "NFA",
    "LFA",
    "CFA",
    "PFA",
    "REG",
    "PAIR",
    "ZERO",
    "BYTE",
    "WORD",
    "POP",
    "ASM",
    "OP",
    "RS",
    "SP",
    "TO",
    "DE",
    "BC",
]


def is_escaped(text: str, idx: int) -> bool:
    backslashes = 0
    j = idx - 1
    while j >= 0 and text[j] == "\\":
        backslashes += 1
        j -= 1
    return (backslashes % 2) == 1


def apply_outside_quotes(text: str, func) -> str:
    out = []
    start = 0
    in_double = False
    in_single = False
    for i, ch in enumerate(text):
        if ch == '"' and not in_single and not is_escaped(text, i):
            if not in_double:
                out.append(func(text[start:i]))
                in_double = True
                start = i
            else:
                out.append(text[start:i + 1])
                in_double = False
                start = i + 1
        elif ch == "'" and not in_double and not is_escaped(text, i):
            if not in_single:
                out.append(func(text[start:i]))
                in_single = True
                start = i
            else:
                out.append(text[start:i + 1])
                in_single = False
                start = i + 1
    if in_double or in_single:
        out.append(text[start:])
    else:
        out.append(func(text[start:]))
    return "".join(out)


def split_comment(line: str) -> tuple[str, str]:
    in_double = False
    in_single = False
    for i, ch in enumerate(line):
        if ch == '"' and not in_single and not is_escaped(line, i):
            in_double = not in_double
        elif ch == "'" and not in_double and not is_escaped(line, i):
            in_single = not in_single
        if ch == ';' and not in_double and not in_single:
            return line[:i], line[i:]
    return line, ""


def split_backslash_segments(text: str) -> list[str]:
    segments = []
    current = []
    in_double = False
    in_single = False
    for i, ch in enumerate(text):
        if ch == '"' and not in_single and not is_escaped(text, i):
            in_double = not in_double
        elif ch == "'" and not in_double and not is_escaped(text, i):
            in_single = not in_single
        if ch == "\\" and not in_double and not in_single:
            segments.append("".join(current))
            current = []
            continue
        current.append(ch)
    segments.append("".join(current))
    return segments


def apply_param_escapes(text: str, params: list[str]) -> str:
    if not params:
        return text

    def replace_segment(segment: str) -> str:
        out = segment
        for param in params:
            if not param:
                continue
            pattern = rf"(?<!\\)\b{re.escape(param)}\b"
            out = re.sub(pattern, rf"\\{param}", out, flags=re.IGNORECASE)
        return out

    return apply_outside_quotes(text, replace_segment)


def split_macro_tokens(name: str) -> list[str]:
    name = name.strip("_")
    if not name:
        return []
    tokens = []
    parts = [p for p in name.split("_") if p]
    macro_tokens = sorted(MACRO_TOKENS, key=len, reverse=True)
    for part in parts:
        i = 0
        while i < len(part):
            if part[i].isdigit():
                j = i + 1
                while j < len(part) and part[j].isdigit():
                    j += 1
                tokens.append(part[i:j])
                i = j
                continue
            matched = False
            for tok in macro_tokens:
                if part.startswith(tok, i):
                    tokens.append(tok)
                    i += len(tok)
                    matched = True
                    break
            if matched:
                continue
            tokens.append(part[i])
            i += 1
    return tokens


def style_macro_name(name: str) -> str:
    name_up = name.upper()
    tokens = split_macro_tokens(name_up)
    if not tokens:
        return name.lower()
    out = tokens[0].lower()
    for tok in tokens[1:]:
        if tok.isdigit():
            out += tok
        else:
            out += tok.lower().capitalize()
    return out


def lowercase_identifiers(code: str, macro_names: set[str]) -> str:
    ident_re = re.compile(r"\b\.?[A-Za-z_.$][\w.$]*\b")

    def repl(segment: str) -> str:
        def replace_token(m: re.Match) -> str:
            token = m.group(0)
            if token.startswith("."):
                rest = token[1:]
                rest_up = rest.upper()
                if rest_up in macro_names:
                    return "." + style_macro_name(rest_up)
                return token.lower()
            token_up = token.upper()
            if token_up in OPCODES or token_up in REGISTERS:
                return token
            if token_up in macro_names:
                return style_macro_name(token_up)
            return token.lower()

        return ident_re.sub(replace_token, segment)

    return apply_outside_quotes(code, repl)


def parse_paren_args(text: str) -> tuple[str, str] | None:
    idx = 0
    while idx < len(text) and text[idx].isspace():
        idx += 1
    if idx >= len(text) or text[idx] != "(":
        return None
    depth = 0
    in_double = False
    in_single = False
    end = None
    for i in range(idx, len(text)):
        ch = text[i]
        if ch == '"' and not in_single and not is_escaped(text, i):
            in_double = not in_double
        elif ch == "'" and not in_double and not is_escaped(text, i):
            in_single = not in_single
        if in_double or in_single:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        return None
    args = text[idx + 1:end].strip()
    suffix = text[end + 1:]
    return args, suffix


def normalize_directives(code: str) -> str:
    def repl(m: re.Match) -> str:
        prefix = m.group(1)
        has_dot = bool(m.group(2))
        directive = m.group(3).upper()
        rest = code[m.end():]
        if not has_dot:
            next_tok = re.split(r"\s+", rest.strip(), maxsplit=1)[0].upper() if rest.strip() else ""
            if next_tok in OPCODES:
                return m.group(0)
        mapped = {
            "DB": ".byte",
            "BYTE": ".byte",
            "DW": ".word",
            "WORD": ".word",
            "DS": ".ds",
            "ORG": ".org",
            "END": ".end",
        }.get(directive, f".{directive.lower()}")
        return f"{prefix}{mapped}"

    return DIRECTIVE_RE.sub(repl, code)


def normalize_preproc(code: str) -> str:
    m = PREPROC_RE.match(code)
    if not m:
        return code
    indent = m.group(1)
    keyword = m.group(3).lower()
    rest = code[m.end():]
    return f"{indent}.{keyword}{rest}"


def convert_undoc_opcodes(code: str) -> str:
    m = UNDOC_OP_RE.match(code)
    if not m:
        return code
    indent, label, ws, op, rest = m.groups()
    label = label or ""
    ws = ws or ""
    if label and not ws and not label.endswith(":"):
        ws = " "
    op = op.upper()
    rest_raw = rest.rstrip()
    rest_stripped = rest.strip()
    if op == "DSUB":
        rep = ".byte 08H"
    elif op == "RDEL":
        rep = ".byte 18H"
    elif op == "LDEH":
        rep = f".byte 028H,{rest_raw}" if rest_stripped else ".byte 028H"
    elif op == "LDES":
        rep = f".byte 038H,{rest_raw}" if rest_stripped else ".byte 038H"
    elif op == "LHLX":
        rep = ".byte 0EDH"
    elif op == "SHLX":
        rep = ".byte 0D9H"
    else:
        rep = op
    return f"{indent}{label}{ws}{rep}"


def convert_macro_invocation(code: str, macro_names: set[str]) -> str:
    if not macro_names:
        return code
    indent = ""
    label = ""
    ws = ""
    rest = code

    m = re.match(r"^(\s*)([A-Za-z_.$][\w.$]*:)(\s*)(.*)$", code)
    if m:
        indent, label, ws, rest = m.groups()
        label = label[:-1]
    else:
        m = LABEL_LINE_RE.match(code)
        if m:
            indent, possible_label, ws, rest = m.groups()
            rest_stripped = rest.lstrip()
            if rest_stripped:
                t = re.match(r"^[.#]?([A-Za-z_.$][\w.$]*)", rest_stripped)
                if t:
                    token_up = t.group(1).upper()
                    first_up = possible_label.upper().lstrip(".")
                    if token_up in macro_names and first_up not in OPCODES and first_up not in DIRECTIVES and first_up not in macro_names:
                        label = possible_label
                    else:
                        label = ""
        if not label:
            rest = code.lstrip()
            indent = code[: len(code) - len(rest)]
            ws = ""

    rest = rest or ""
    if not rest:
        return code
    prefix = ""
    rest_body = rest
    if rest and rest[0] in "#.":
        prefix = rest[0]
        rest_body = rest[1:]
    tm = re.match(r"^([A-Za-z_.$][\w.$]*)(.*)$", rest_body)
    if not tm:
        return code
    name = tm.group(1)
    name_up = name.upper()
    if name_up not in macro_names:
        return code
    styled = style_macro_name(name_up)
    after = tm.group(2)
    parsed = parse_paren_args(after)
    if parsed:
        args, suffix = parsed
        if args:
            new_rest = f".{styled} {args}"
        else:
            new_rest = f".{styled}"
        new_rest += suffix
    else:
        new_rest = f".{styled}{after}"
    if label:
        ws_out = ws if ws else " "
        return f"{indent}{label.lower()}{ws_out}{new_rest}"
    return f"{indent}{new_rest}"


def convert_define_macro(code: str, comment: str, line_ending: str, macro_names: set[str]) -> list[str] | None:
    m = DEFINE_RE.match(code)
    if not m:
        return None
    indent, name, args_raw, body = m.groups()
    name_upper = name.upper()
    styled_name = style_macro_name(name_upper)
    args = []
    if args_raw:
        args = [arg.strip().lower() for arg in args_raw.split(",") if arg.strip()]

    body = body.rstrip()

    # Treat simple value-only defines as preprocessor constants.
    if not args and body and "\\" not in body and len(body.split()) == 1:
        define_line = f"{indent}.define {name.lower()}={body}"
        if comment:
            define_line += comment
        return [define_line + line_ending]

    macro_names.add(name_upper)

    macro_header = f"{indent}{styled_name} .macro"
    if args:
        macro_header += " " + ", ".join(args)
    if comment:
        macro_header += comment

    lines = [macro_header + line_ending]

    for segment in split_backslash_segments(body):
        seg = segment.strip()
        if not seg:
            continue
        seg = lowercase_identifiers(seg, macro_names)
        seg = apply_param_escapes(seg, args)
        seg = normalize_directives(seg)
        seg = normalize_hex(seg)
        seg = space_shifts(seg)
        seg = convert_macro_invocation(seg, macro_names)
        seg = convert_undoc_opcodes(seg)
        lines.append(f"{INDENT}{seg}{line_ending}")

    lines.append(f"{indent}.endmacro{line_ending}")

    # Auto-generate LINKTO0 macro alongside LINKTO.
    args_lower = [arg.lower() for arg in args]
    if name_upper == "LINKTO" and args_lower == ["prev", "isimm", "len", "lastchar", "revchars"]:
        macro_names.add("LINKTO0")
        linkto0_args = ["prev", "isimm", "len", "lastchar"]
        linkto0_header = f"{indent}{style_macro_name('LINKTO0')} .macro " + ", ".join(linkto0_args)
        lines.append(linkto0_header + line_ending)
        for segment in split_backslash_segments(body):
            seg = segment.strip()
            if not seg:
                continue
            seg = re.sub(r",\s*revchars\b", "", seg, flags=re.IGNORECASE)
            seg = seg.replace("10000000b|lastchar,", "10000000b|lastchar")
            seg = lowercase_identifiers(seg, macro_names)
            seg = apply_param_escapes(seg, linkto0_args)
            seg = normalize_directives(seg)
            seg = normalize_hex(seg)
            seg = space_shifts(seg)
            seg = convert_macro_invocation(seg, macro_names)
            seg = convert_undoc_opcodes(seg)
            lines.append(f"{INDENT}{seg}{line_ending}")
        lines.append(f"{indent}.endmacro{line_ending}")

    return lines


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
        if ch == '"' and not is_escaped(expr, i):
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
        if ch == '"' and not is_escaped(expr, i):
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


def convert_line(line: str, macro_names: set[str]) -> list[str]:
    if not line.strip():
        return [line]

    code, comment = split_comment(line)
    if not code.strip():
        return [line]

    line_ending = "\n" if line.endswith("\n") else ""
    if code.endswith("\n"):
        code = code[:-1]
    if comment.endswith("\n"):
        comment = comment[:-1]

    # Drop .ADDINSTR lines (asm485 doesn't support custom mnemonics)
    if ADDINSTR_RE.match(code.strip()):
        return ["; " + line.lstrip()]

    # Normalize ECHO into comments (asm485 has no .echo)
    if re.match(r"^\s*[#.]?ECHO\b", code, re.IGNORECASE):
        code = re.sub(r"^\s*[#.]?ECHO", "; ECHO", code, count=1, flags=re.IGNORECASE)
        return [code + comment + line_ending]

    # Preserve original spacing before comments
    comment_pad = ""
    if comment:
        m = re.search(r"(\s*)$", code)
        comment_pad = m.group(1)
        code = code.rstrip()

    comment_full = f"{comment_pad}{comment}" if comment else ""

    macro_lines = convert_define_macro(code, comment_full, line_ending, macro_names)
    if macro_lines:
        return macro_lines

    # Convert label: ORG to .ORG then label on next line
    m = LABEL_ORG_RE.match(code)
    if m:
        indent, label, _, rest = m.groups()
        rest = rest.rstrip()
        org_indent = indent if indent else " "
        org_line = f"{org_indent}.org{rest}"
        org_line = normalize_hex(space_shifts(org_line))
        if comment:
            org_line += comment_full
        return [org_line + line_ending, f"{label.lower()}{line_ending}"]

    # Convert label: EQU/SET to asm485 assignments
    m = LABEL_EQU_RE.match(code)
    if m:
        indent, label, directive, rest = m.groups()
        op = "=" if directive.upper() == "EQU" else ":="
        code = f"{indent}{label.lower()} {op}{rest}"

    # Convert label EQU/SET without colon
    m = LABEL_ASSIGN_RE.match(code)
    if m:
        indent, label, _ws, directive, rest = m.groups()
        op = "=" if directive.upper() == "EQU" else ":="
        code = f"{indent}{label.lower()} {op}{rest}"

    # Normalize preprocessor/conditional directives (dot-prefixed)
    if not LABEL_RE.match(code):
        code = normalize_preproc(code)

    # LINKTO(...,"") -> LINKTO0(...)
    code = LINKTO_EMPTY_RE.sub(r"LINKTO0(\1)", code)

    # Strip label colons and lower-case labels (label: rest -> label rest)
    m = LABEL_DEF_RE.match(code)
    if m:
        indent, label, _ws, rest = m.groups()
        rest = rest.lstrip()
        if rest:
            code = f"{indent}{label.lower()} {rest}"
        else:
            code = f"{indent}{label.lower()}"

    # Add missing label colons (e.g., "PLUSLOOP    JMP" -> "PLUSLOOP: JMP")
    if ":" not in code:
        m = LABEL_LINE_RE.match(code)
        if m:
            indent, label, ws, rest = m.groups()
            if indent:
                m = None
            if m:
                first = label.upper().lstrip(".")
                second = re.split(r"\s+", rest.strip(), maxsplit=1)[0].upper()
                if (
                    first not in DIRECTIVES
                    and first not in OPCODES
                    and second in OPCODES
                ):
                    code = f"{indent}{label.lower()} {rest.lstrip()}"

    # Normalize directives, undocumented opcodes, and hex formatting
    code = normalize_directives(code)
    code = convert_undoc_opcodes(code)
    code = normalize_hex(code)
    code = space_shifts(code)

    # Remove trailing comma for .BYTE/.WORD without reformatting spacing
    data_match = re.match(r"^(\s*(?:[A-Za-z_.$][\w.$]*\s+)?)(\.byte|\.word)\b(.*)$", code, re.IGNORECASE)
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
        code = f"{prefix}{directive.lower()}{''.join(out)}"

    # Macro invocations: NAME(...) -> #NAME ...
    code = convert_macro_invocation(code, macro_names)

    # Lower-case symbols and directives (but keep opcodes/registers)
    code = lowercase_identifiers(code, macro_names)

    # Indent opcode-only lines starting at column 1
    stripped = code.lstrip()
    leading = code[: len(code) - len(stripped)]
    if not leading:
        token = re.split(r"\s+", stripped, maxsplit=1)[0]
        token_up = token.upper().lstrip(".")
        if token_up in OPCODES:
            code = INDENT + stripped

    # Reattach comment
    if comment:
        code = f"{code}{comment_pad}{comment}"

    return [code + line_ending]


def convert_text(text: str, macro_names: set[str]) -> str:
    out_lines = []
    for line in text.splitlines(keepends=True):
        converted = convert_line(line, macro_names)
        out_lines.extend(converted)
    return "".join(out_lines)


def collect_macro_names(paths: list[Path]) -> set[str]:
    names: set[str] = set()
    define_name_re = re.compile(r"^\s*[#.]?DEFINE\s+([A-Za-z_.$][\w.$]*)\b", re.IGNORECASE)
    for path in paths:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            m = define_name_re.match(line)
            if not m:
                continue
            name = m.group(1).upper()
            names.add(name)
            if name == "LINKTO":
                names.add("LINKTO0")
    return names


def convert_file(src: Path, dst: Path | None, macro_names: set[str]) -> None:
    data = src.read_text(errors="ignore")
    converted = convert_text(data, macro_names)
    if dst is None:
        sys.stdout.write(converted)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(converted)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert TASM-style MFORTH .asm files to asm485 syntax.")
    parser.add_argument("src", type=Path, help="Source file or directory")
    parser.add_argument("dst", nargs="?", type=Path, help="Destination file or directory")
    parser.add_argument("--in-place", action="store_true", help="Convert files in place (directory only)")
    args = parser.parse_args()

    if args.src.is_dir():
        all_sources = list(args.src.rglob("*.asm"))
        macro_names = collect_macro_names(all_sources)
        if args.in_place:
            if args.dst is not None:
                parser.error("--in-place cannot be used with a destination path")
            for path in all_sources:
                convert_file(path, path, macro_names)
            return 0
        if args.dst is None:
            parser.error("destination directory required when converting a directory")
        for path in all_sources:
            rel = path.relative_to(args.src)
            convert_file(path, args.dst / rel, macro_names)
        return 0

    if args.dst is None:
        macro_names = collect_macro_names([args.src])
        convert_file(args.src, None, macro_names)
        return 0

    macro_names = collect_macro_names([args.src])
    convert_file(args.src, args.dst, macro_names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
