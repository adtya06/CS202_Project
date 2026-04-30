from __future__ import annotations

from pathlib import Path

from cfg_optimizer.cli import run_pipeline


def main() -> None:
    root = Path(__file__).resolve().parent
    sample = root / "examples" / "input" / "sample.c"
    out_dir = root / "artifacts"

    exit_code = run_pipeline(str(sample), str(out_dir), optimize=True)
    if exit_code != 0:
        raise SystemExit(exit_code)

    print(f"Rendered PNGs in: {out_dir}")


if __name__ == "__main__":
    main()
