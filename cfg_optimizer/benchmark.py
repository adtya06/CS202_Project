from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

from cfg_optimizer.analysis import analyses_to_report
from cfg_optimizer.ast_parser import get_function_defs, iter_c_files, parse_c_file
from cfg_optimizer.callgraph import build_call_graph, call_graph_to_report
from cfg_optimizer.cfg import build_cfg
from cfg_optimizer.optimizer import apply_all
from cfg_optimizer.visualize import export_call_graph_to_dot, export_cfg_to_dot


@dataclass
class FileResult:
    path: str
    status: str
    parse_time_sec: float
    function_count: int = 0
    processed_functions: int = 0
    action_count: int = 0
    error: str | None = None


@dataclass
class BenchmarkReport:
    dataset: str
    input_path: str
    max_files: int
    optimize: bool
    save_artifacts: bool
    started_at_epoch_sec: float
    finished_at_epoch_sec: float
    total_time_sec: float
    files_discovered: int
    files_attempted: int
    files_succeeded: int
    files_failed: int
    functions_processed: int
    total_optimization_actions: int
    action_breakdown: Dict[str, int] = field(default_factory=dict)
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    file_results: List[FileResult] = field(default_factory=list)


def _json_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _record_error(errors_by_type: Dict[str, int], exc: Exception) -> None:
    name = type(exc).__name__
    errors_by_type[name] = errors_by_type.get(name, 0) + 1


def run_benchmark(
    dataset: str,
    input_path: str,
    out_dir: str,
    max_files: int,
    optimize: bool,
    save_artifacts: bool,
) -> Path:
    started = time.time()

    discovered = list(iter_c_files(input_path))
    selected = discovered[:max_files] if max_files > 0 else discovered

    files_succeeded = 0
    files_failed = 0
    functions_processed = 0
    total_actions = 0
    action_breakdown: Dict[str, int] = {}
    errors_by_type: Dict[str, int] = {}
    results: List[FileResult] = []

    report_root = Path(out_dir)
    file_artifact_root = report_root / f"{dataset}_artifacts"

    for c_file in selected:
        parse_start = time.time()
        try:
            ast_root = parse_c_file(c_file)
            parse_time = time.time() - parse_start
            funcs = get_function_defs(ast_root)

            if save_artifacts:
                call_graph = build_call_graph(ast_root)
                stem = Path(c_file).stem
                export_call_graph_to_dot(call_graph, file_artifact_root / f"{stem}.callgraph.dot")
                _json_write(file_artifact_root / f"{stem}.callgraph.json", call_graph_to_report(call_graph))

            file_result = FileResult(
                path=str(c_file),
                status="ok",
                parse_time_sec=parse_time,
                function_count=len(funcs),
            )

            for func in funcs:
                cfg = build_cfg(func)
                _ = analyses_to_report(cfg)
                actions = apply_all(cfg) if optimize else []
                _ = analyses_to_report(cfg)

                file_result.processed_functions += 1
                file_result.action_count += len(actions)
                functions_processed += 1
                total_actions += len(actions)

                for action in actions:
                    p = action.get("pass", "unknown")
                    action_breakdown[p] = action_breakdown.get(p, 0) + 1

                if save_artifacts:
                    prefix = f"{Path(c_file).stem}.{func.decl.name}"
                    export_cfg_to_dot(cfg, file_artifact_root / f"{prefix}.optimized.cfg.dot")
                    _json_write(file_artifact_root / f"{prefix}.optimizations.json", actions)

            files_succeeded += 1
            results.append(file_result)

        except Exception as exc:
            parse_time = time.time() - parse_start
            files_failed += 1
            _record_error(errors_by_type, exc)
            results.append(
                FileResult(
                    path=str(c_file),
                    status="error",
                    parse_time_sec=parse_time,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    finished = time.time()

    report = BenchmarkReport(
        dataset=dataset,
        input_path=str(Path(input_path)),
        max_files=max_files,
        optimize=optimize,
        save_artifacts=save_artifacts,
        started_at_epoch_sec=started,
        finished_at_epoch_sec=finished,
        total_time_sec=finished - started,
        files_discovered=len(discovered),
        files_attempted=len(selected),
        files_succeeded=files_succeeded,
        files_failed=files_failed,
        functions_processed=functions_processed,
        total_optimization_actions=total_actions,
        action_breakdown=action_breakdown,
        errors_by_type=errors_by_type,
        file_results=results,
    )

    summary_path = report_root / f"{dataset}.benchmark.summary.json"
    _json_write(summary_path, asdict(report))
    return summary_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run batch benchmark on C files for the CFG optimizer pipeline")
    parser.add_argument("--dataset", required=True, help="Dataset label used in report filenames")
    parser.add_argument("--input", required=True, help="Path to C file or directory with .c files")
    parser.add_argument("--out-dir", default="artifacts/benchmarks", help="Directory for benchmark summaries")
    parser.add_argument("--max-files", type=int, default=100, help="Maximum number of .c files to attempt (0 = all)")
    parser.add_argument("--no-opt", action="store_true", help="Disable optimization passes")
    parser.add_argument("--save-artifacts", action="store_true", help="Save per-function optimized DOT and actions")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    summary_path = run_benchmark(
        dataset=args.dataset,
        input_path=args.input,
        out_dir=args.out_dir,
        max_files=args.max_files,
        optimize=not args.no_opt,
        save_artifacts=args.save_artifacts,
    )

    print(f"Benchmark complete: {summary_path}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
