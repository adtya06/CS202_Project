from __future__ import annotations

import argparse
import json
from pathlib import Path

from cfg_optimizer.analysis import analyses_to_report
from cfg_optimizer.ast_parser import get_function_defs, iter_c_files, parse_c_file
from cfg_optimizer.callgraph import build_call_graph, call_graph_to_report
from cfg_optimizer.cfg import build_cfg
from cfg_optimizer.optimizer import apply_all
from cfg_optimizer.visualize import export_call_graph_to_dot, export_cfg_to_dot


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_pipeline(input_path: str, out_dir: str, function_name: str | None = None, optimize: bool = True) -> int:
    source_paths = list(iter_c_files(input_path))
    if not source_paths:
        target = Path(input_path)
        if target.suffix.lower() == ".c":
            matches = sorted(Path.cwd().rglob(target.name))
            if matches:
                if len(matches) == 1:
                    source_paths = [matches[0]]
                    print(f"Auto-resolved input to: {matches[0]}")
                else:
                    print(f"No .c files found at: {input_path}")
                    print("Did you mean one of these?")
                    for match in matches[:5]:
                        print(f"  - {match}")
                    print(f"Try: python -m cfg_optimizer.cli {matches[0]} --out-dir {out_dir}")
                    return 1
            else:
                print(f"No .c files found at: {input_path}")
                print("Tip: pass a valid .c file path or a directory containing .c files.")
                return 1
        else:
            print(f"No .c files found at: {input_path}")
            print("Tip: pass a .c file path or a directory containing .c files.")
            return 1

    output_root = Path(out_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    processed = 0
    for c_file in source_paths:
        ast_root = parse_c_file(c_file)
        funcs = get_function_defs(ast_root)

        call_graph = build_call_graph(ast_root)
        callgraph_dot = output_root / f"{c_file.stem}.callgraph.dot"
        callgraph_json = output_root / f"{c_file.stem}.callgraph.json"
        export_call_graph_to_dot(call_graph, callgraph_dot)
        _write_json(
            callgraph_json,
            {
                "source_file": str(c_file),
                "call_graph": call_graph_to_report(call_graph),
            },
        )
        print(f"Program call graph for {c_file.name}")
        print(f"  - {callgraph_dot}")
        print(f"  - {callgraph_json}")

        if function_name:
            funcs = [f for f in funcs if f.decl.name == function_name]

        for func in funcs:
            cfg = build_cfg(func)
            name_prefix = f"{c_file.stem}.{func.decl.name}"

            original_dot = output_root / f"{name_prefix}.cfg.dot"
            optimized_dot = output_root / f"{name_prefix}.optimized.cfg.dot"
            analysis_json = output_root / f"{name_prefix}.analysis.json"
            optimizations_json = output_root / f"{name_prefix}.optimizations.json"

            export_cfg_to_dot(cfg, original_dot)
            analysis_before = analyses_to_report(cfg)

            actions = []
            if optimize:
                actions = apply_all(cfg)

            export_cfg_to_dot(cfg, optimized_dot)
            analysis_after = analyses_to_report(cfg)

            _write_json(
                analysis_json,
                {
                    "source_file": str(c_file),
                    "function": func.decl.name,
                    "before_optimization": analysis_before,
                    "after_optimization": analysis_after,
                },
            )
            _write_json(optimizations_json, actions)

            processed += 1
            print(f"Processed {c_file.name}:{func.decl.name}")
            print(f"  - {original_dot}")
            print(f"  - {optimized_dot}")
            print(f"  - {analysis_json}")
            print(f"  - {optimizations_json}")

    if processed == 0:
        print("No matching functions were processed.")
        return 1

    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C-to-CFG static analysis and optimization pipeline")
    parser.add_argument("input", help="Path to a C file or a directory containing .c files")
    parser.add_argument("--out-dir", default="artifacts", help="Output directory for DOT and JSON artifacts")
    parser.add_argument("--function", default=None, help="Optional function name filter")
    parser.add_argument("--no-opt", action="store_true", help="Disable optimization passes")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    exit_code = run_pipeline(
        input_path=args.input,
        out_dir=args.out_dir,
        function_name=args.function,
        optimize=not args.no_opt,
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
