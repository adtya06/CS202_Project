from __future__ import annotations
import os
from pathlib import Path

# import pycparser
from pycparser import c_ast, parse_file

def _get_fake_libc_path() -> str:

    """
    Locates the fake headers locally within the project workspace.
    """
    # __file__ is ast_parser.py. .parent is cfg_optimizer. .parent.parent is CS202_Project.
    project_root = Path(__file__).resolve().parent.parent
    fake_libc_path = project_root / "utils" / "fake_libc_include"
    
    if not fake_libc_path.exists():
        raise FileNotFoundError(f"CRITICAL: Cannot find local fake headers at {fake_libc_path}")
        
    return str(fake_libc_path)

def parse_c_file(path: str | Path) -> c_ast.FileAST:
    """
    Hands the file to the C Preprocessor, strictly routing it to the fake headers 
    to prevent GNU extension crashes.
    """
    fake_libc = _get_fake_libc_path()
    
    # -I tells the compiler to add this directory to its include search path
    return parse_file(
        str(path), 
        use_cpp=True, 
        cpp_args=[f'-I{fake_libc}']
    )

def get_function_defs(ast_root: c_ast.FileAST) -> list[c_ast.FuncDef]:
    funcs: list[c_ast.FuncDef] = []
    for ext in ast_root.ext:
        if isinstance(ext, c_ast.FuncDef):
            funcs.append(ext)
    return funcs