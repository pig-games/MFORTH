#!/usr/bin/env python3
import argparse
import subprocess
import tempfile
from pathlib import Path


def run(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def compare_files(a: Path, b: Path) -> int:
    a_lines = a.read_text().splitlines()
    b_lines = b.read_text().splitlines()
    if a_lines == b_lines:
        return 0
    max_len = max(len(a_lines), len(b_lines))
    for i in range(max_len):
        left = a_lines[i] if i < len(a_lines) else "<EOF>"
        right = b_lines[i] if i < len(b_lines) else "<EOF>"
        if left != right:
            print(f"Mismatch at line {i+1}:")
            print(f"  C#:  {left}")
            print(f"  Rust:{right}")
            return 1
    return 1


def main():
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Compare Rust phashgen output to C# output.")
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--sym", required=True, type=Path)
    parser.add_argument("--csharp-out", type=Path)
    parser.add_argument("--rust-out", type=Path)
    parser.add_argument("--phashgen-csproj", type=Path, default=repo_root / "tools/depricated/PhashGenOld/PhashGen.csproj")
    parser.add_argument("--cargo-dir", type=Path, default=repo_root / "tools/phashgen_rust")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        csharp_out = args.csharp_out or (tmp_path / "phash_csharp.asm")
        rust_out = args.rust_out or (tmp_path / "phash_rust.asm")

        # Build and run C# PhashGen
        print("== C# PhashGen ==")
        out_dir = tmp_path / "csharp"
        run([
            "dotnet",
            "build",
            "-c",
            "Release",
            str(args.phashgen_csproj),
            "-o",
            str(out_dir),
        ])
        run([
            "dotnet",
            str(out_dir / "PhashGen.dll"),
            str(args.rom),
            str(args.sym),
            str(csharp_out),
        ])

        # Build and run Rust phashgen
        print("== Rust phashgen ==")
        run([
            "cargo",
            "build",
            "-p",
            "phashgen",
        ], cwd=args.cargo_dir)
        run([
            str(args.cargo_dir / "target" / "debug" / "phashgen"),
            str(args.rom),
            str(args.sym),
            str(rust_out),
        ])

        print("== Compare ==")
        diff = compare_files(csharp_out, rust_out)
        if diff == 0:
            print("OK: outputs match")
        else:
            print("ERROR: outputs differ")
        raise SystemExit(diff)


if __name__ == "__main__":
    main()
