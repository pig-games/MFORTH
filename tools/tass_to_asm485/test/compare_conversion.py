#!/usr/bin/env python3
import difflib
import subprocess
import tempfile
from pathlib import Path


def run(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def normalize_lines(path: Path):
    text = path.read_text(errors="ignore")
    return [line.rstrip() for line in text.splitlines()]


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[2]
    src_dir = script_dir / "MFORTH_TASS"
    expected_dir = script_dir / "MFORTH_ASM485"
    converter = repo_root / "tools" / "tass_to_asm485" / "convert_mforth_to_asm485.py"

    if not src_dir.is_dir():
        print(f"Missing source dir: {src_dir}")
        return 2
    if not expected_dir.is_dir():
        print(f"Missing expected dir: {expected_dir}")
        return 2
    if not converter.exists():
        print(f"Missing converter: {converter}")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        run(["python3", str(converter), str(src_dir), str(out_dir)])

        expected_files = {p.relative_to(expected_dir) for p in expected_dir.rglob("*.asm")}
        generated_files = {p.relative_to(out_dir) for p in out_dir.rglob("*.asm")}

        missing = sorted(expected_files - generated_files)
        extra = sorted(generated_files - expected_files)
        if missing or extra:
            if missing:
                print("Missing generated files:")
                for p in missing:
                    print(f"  {p}")
            if extra:
                print("Unexpected generated files:")
                for p in extra:
                    print(f"  {p}")
            return 1

        for rel in sorted(expected_files):
            expected_path = expected_dir / rel
            generated_path = out_dir / rel
            expected_lines = normalize_lines(expected_path)
            generated_lines = normalize_lines(generated_path)
            if expected_lines != generated_lines:
                diff = difflib.unified_diff(
                    expected_lines,
                    generated_lines,
                    fromfile=str(expected_path),
                    tofile=str(generated_path),
                    lineterm="",
                )
                print("Mismatch:")
                for i, line in enumerate(diff):
                    print(line)
                    if i > 200:
                        print("...diff truncated...")
                        break
                return 1

    print("OK: converted output matches expected asm485 sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
