#!/usr/bin/env python3
"""Copy a source tree and strip leading '#' from opForge preprocessor directives."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import re


PREPROC_RE = re.compile(
    r"^(\s*)([#.])(IFDEF|IFNDEF|IF|ELSEIF|ELSE|ENDIF|DEFINE|UNDEF|INCLUDE|ECHO)\b",
    re.IGNORECASE,
)
LABEL_RE = re.compile(
    r"^\s*[#.](IFDEF|IFNDEF|IF|ELSEIF|ELSE|ENDIF)\s*:",
    re.IGNORECASE,
)
CONDITIONALS = {"IF", "ELSEIF", "ELSE", "ENDIF"}
PREPROC_START = {"IFDEF", "IFNDEF"}
DIRECTIVES = {"DEFINE", "UNDEF", "INCLUDE", "ECHO"}


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


def normalize_preproc(text: str) -> str:
    out = []
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

        # Preserve label definitions (e.g., IF: / ELSE:)
        if LABEL_RE.match(code):
            if code.lstrip().startswith("#"):
                code = code.replace("#", "", 1)
            out.append(code + comment + line_ending)
            continue

        m = PREPROC_RE.match(code)
        if not m:
            out.append(line)
            continue

        keyword = m.group(3).lower()
        rest = code[m.end():]
        new_code = f".{keyword}{rest}"
        out.append(new_code + comment + line_ending)
    return "".join(out)


def copy_and_strip(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for path in dst.rglob("*.asm"):
        try:
            original = path.read_text()
        except UnicodeDecodeError:
            continue
        updated = normalize_preproc(original)
        if updated != original:
            path.write_text(updated)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    args = parser.parse_args()
    copy_and_strip(args.src, args.dst)


if __name__ == "__main__":
    main()
