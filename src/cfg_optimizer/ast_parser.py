from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from pycparser import c_ast, c_parser


def _strip_preprocessor_lines(code: str) -> str:
    """Remove preprocessor directives so pycparser can parse plain C snippets."""
    lines = []
    for line in code.splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _strip_c_comments(code: str) -> str:
    """Remove C comments while preserving quoted strings and newlines."""
    out: list[str] = []
    i = 0
    n = len(code)
    in_single = False
    in_double = False

    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""

        if in_single:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(code[i + 1])
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(code[i + 1])
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue

        if ch == "'":
            in_single = True
            out.append(ch)
            i += 1
            continue

        if ch == '"':
            in_double = True
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            i += 2
            while i < n and code[i] != "\n":
                i += 1
            continue

        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (code[i] == "*" and code[i + 1] == "/"):
                if code[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2 if i + 1 < n else 0
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def parse_c_code(code: str):
    parser = c_parser.CParser()
    cleaned = _strip_preprocessor_lines(code)
    cleaned = _strip_c_comments(cleaned)
    return parser.parse(cleaned)


def parse_c_file(path: str | Path):
    file_path = Path(path)
    code = file_path.read_text(encoding="utf-8")
    return parse_c_code(code)


def get_function_defs(ast_root: c_ast.FileAST) -> List[c_ast.FuncDef]:
    funcs: List[c_ast.FuncDef] = []
    for ext in ast_root.ext:
        if isinstance(ext, c_ast.FuncDef):
            funcs.append(ext)
    return funcs


def iter_c_files(path: str | Path) -> Iterable[Path]:
    target = Path(path)
    if target.is_file() and target.suffix.lower() == ".c":
        yield target
        return
    if target.is_dir():
        for c_file in sorted(target.rglob("*.c")):
            yield c_file
