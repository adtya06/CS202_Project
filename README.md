# CS-202 Project Part 1 - C to Optimized CFG

This project builds a pipeline that:
- parses C code into a basic-block control flow graph (CFG),
- runs static analyses (reaching definitions + live variables),
- applies optimization passes (constant folding, constant propagation, dead code elimination, unreachable code removal),
- exports CFG and reports.

## Quick Start

```bash
python -m pip install -r requirements.txt
python -m cfg_optimizer.cli examples/input/sample.c --out-dir artifacts
```

Or install as a package and use the script entrypoint:

```bash
python -m pip install -e .
cfg-opt examples/input/sample.c --out-dir artifacts
```

## Output

Given an input file `<name>.c`, the CLI writes:
- `artifacts/<name>.cfg.dot` - CFG in DOT format
- `artifacts/<name>.optimized.cfg.dot` - optimized CFG in DOT format
- `artifacts/<name>.analysis.json` - reaching definitions/live variable data
- `artifacts/<name>.optimizations.json` - list of applied optimization actions
- `artifacts/<name>.callgraph.dot` - whole-program call graph (functions and call edges)
- `artifacts/<name>.callgraph.json` - call graph nodes and caller/callee edges

## Project Structure

- `src/cfg_optimizer/ast_parser.py` - pycparser front-end
- `src/cfg_optimizer/cfg.py` - basic-block CFG construction
- `src/cfg_optimizer/analysis.py` - dataflow analyses
- `src/cfg_optimizer/optimizer.py` - optimization passes
- `src/cfg_optimizer/visualize.py` - DOT export
- `src/cfg_optimizer/cli.py` - command-line interface
- `tests/` - unit tests

## Notes

This is intentionally conservative and educational: it focuses on correctness and transparent reporting rather than aggressive compiler-grade transformations.

## Dataset Benchmarking

For large datasets, use the benchmark runner. It continues on parse errors and writes a summary JSON.

```bash
python -m cfg_optimizer.benchmark --dataset svbench --input datasets/sv-benchmarks/c --max-files 200 --out-dir artifacts/benchmarks
python -m cfg_optimizer.benchmark --dataset codenet --input datasets/Project_CodeNet/data --max-files 200 --out-dir artifacts/benchmarks
```

You can save optimized DOT artifacts too:

```bash
python -m cfg_optimizer.benchmark --dataset svbench --input datasets/sv-benchmarks/c --max-files 100 --save-artifacts --out-dir artifacts/benchmarks
```

## Batch Render DOT to PNG

Render all generated `.dot` files to `.png` in one command:

```bash
python -m cfg_optimizer.render --input-dir artifacts/benchmarks --recursive
```

If `dot` is not on PATH, pass the executable explicitly:

```bash
python -m cfg_optimizer.render --input-dir artifacts/benchmarks --recursive --dot-exe "C:/Program Files/Graphviz/bin/dot.exe"
```
