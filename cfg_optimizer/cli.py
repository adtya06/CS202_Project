# command to run : python -m cfg_optimizer.cli --out-dir output

from __future__ import annotations

import argparse
from pathlib import Path


from cfg_optimizer.ast_parser import get_function_defs, parse_c_file
from cfg_optimizer.cfg import build_cfg
from cfg_optimizer.callgraph import build_call_graph
from cfg_optimizer.optimizer import apply_all
from cfg_optimizer.render import render_all_dot_to_png
from cfg_optimizer.visualize import export_cfg_to_dot, export_call_graph_to_dot


def run_pipeline(input_file: str, out_dir: str, optimize: bool = True) -> int:
    target = Path(input_file)
    if not target.is_file() or target.suffix.lower() != ".c":
        print(f"CRITICAL ERROR: Target must be a valid .c file: {input_file}")
        return 1

    output_root = Path(out_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"Parsing AST for: {target.name}")
    
    # 1. THE AST PIPELINE
    ast_root = parse_c_file(target)
    
    # --- NEW: THE CALL GRAPH PIPELINE ---
    print("\n--- Building Program Call Graph ---")
    cg = build_call_graph(ast_root)
    cg_dot = output_root / f"{target.stem}.callgraph.dot"
    export_call_graph_to_dot(cg, cg_dot)
    print(f"  [+] Exported Call Graph DOT: {cg_dot.name}")



    # 2. THE CFG PIPELINE
    funcs = get_function_defs(ast_root)
    if not funcs:
        print("CRITICAL FAILURE: No executable functions found in the AST.")
        return 1



    for func in funcs:
        print(f"\n--- Processing Function: {func.decl.name} ---")
        cfg = build_cfg(func, include_unreachable=True)
        name_prefix = f"{target.stem}.{func.decl.name}"

        original_dot = output_root / f"{name_prefix}.cfg.dot"
        export_cfg_to_dot(cfg, original_dot)
        print(f"  [+] Exported Pre-Optimization DOT : {original_dot.name}")

        if optimize:
            actions = apply_all(cfg)
            for action in actions:
                print(f"      -> {action['optimization']}: {action.get('old', '')} => {action.get('new', '')}")
            
            optimized_dot = output_root / f"{name_prefix}.optimized.cfg.dot"
            export_cfg_to_dot(cfg, optimized_dot)
            print(f"  [+] Exported Post-Optimization DOT: {optimized_dot.name}")



    # 3. THE RENDERING PIPELINE
    print("\nTriggering Graphviz Rendering...")
    try:
        rendered, skipped = render_all_dot_to_png(
            str(output_root),
            recursive=False,
            overwrite=True
        )
        print(f"EXECUTION COMPLETE: Rendered {rendered} PNG files to {out_dir}/")
    except FileNotFoundError as exc:
        print(f"CRITICAL RENDER FAILURE: {str(exc)}")
        return 1

    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimalist CFG & Call Graph Pipeline")
    parser.add_argument("input", help="Strict path to a single .c file")
    parser.add_argument("--out-dir", default="output", help="Output directory for artifacts")
    parser.add_argument("--no-opt", action="store_true", help="Bypass the mutation engine")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    exit_code = run_pipeline(
        input_file=args.input,
        out_dir=args.out_dir,
        optimize=not args.no_opt
    )
    raise SystemExit(exit_code)

if __name__ == "__main__":
    main()