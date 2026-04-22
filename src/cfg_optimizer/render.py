from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def _find_dot_executable(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    found = shutil.which("dot")
    if found:
        return found

    fallback = Path("C:/Program Files/Graphviz/bin/dot.exe")
    if fallback.exists():
        return str(fallback)

    raise FileNotFoundError(
        "Graphviz 'dot' executable not found. Install Graphviz or pass --dot-exe with full path."
    )


def render_all_dot_to_png(input_dir: str, recursive: bool, overwrite: bool, dot_exe: str | None = None) -> tuple[int, int]:
    root = Path(input_dir)
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")

    dot_cmd = _find_dot_executable(dot_exe)
    pattern = "**/*.dot" if recursive else "*.dot"
    dot_files = sorted(root.glob(pattern))

    rendered = 0
    skipped = 0

    for dot_file in dot_files:
        png_file = dot_file.with_suffix(".png")
        if png_file.exists() and not overwrite:
            skipped += 1
            continue

        cmd = [dot_cmd, "-Tpng", str(dot_file), "-o", str(png_file)]
        subprocess.run(cmd, check=True)
        rendered += 1

    return rendered, skipped


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch render .dot files to .png using Graphviz")
    parser.add_argument("--input-dir", default="artifacts", help="Directory containing .dot files")
    parser.add_argument("--recursive", action="store_true", help="Recursively search for .dot files")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing .png files")
    parser.add_argument("--dot-exe", default=None, help="Optional full path to dot executable")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    rendered, skipped = render_all_dot_to_png(
        input_dir=args.input_dir,
        recursive=args.recursive,
        overwrite=args.overwrite,
        dot_exe=args.dot_exe,
    )
    print(f"Rendered {rendered} PNG files. Skipped {skipped} files.")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
