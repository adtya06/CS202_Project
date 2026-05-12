from __future__ import annotations
from typing import List, Tuple, Set
import networkx as nx
from pycparser import c_ast, c_generator

generator = c_generator.CGenerator()


# --- 1. THE DATA-FLOW EXTRACTOR ---

class _IdCollector(c_ast.NodeVisitor):
    """
    Crawls an AST sub-tree and extracts every raw variable name (ID).
    """
    def __init__(self):
        self.names: set[str] = set()

    def visit_ID(self, node: c_ast.ID):
        self.names.add(node.name)

def _extract_ids(node: c_ast.Node | None) -> set[str]:
    if not node:
        return set()
    collector = _IdCollector()
    collector.visit(node)
    return collector.names

def _analyze_statement(stmt: c_ast.Node) -> Tuple[str, set[str], set[str]]:
    """
    Determines exactly which variables are Modified (defs) and Read (uses).
    This is the critical dependency for Reaching Definitions and Live Variables.
    """
    text = generator.visit(stmt)
    defs = set()
    uses = set()

    if isinstance(stmt, c_ast.Decl):
        # int x = y + 1; -> Defs: {x}, Uses: {y}
        if stmt.name:
            defs.add(stmt.name)
        uses = _extract_ids(stmt.init)
        
    elif isinstance(stmt, c_ast.Assignment):
        # x = y + z; -> Defs: {x}, Uses: {y, z}
        defs = _extract_ids(stmt.lvalue)
        uses = _extract_ids(stmt.rvalue)
        # If it is a compound assignment (+=, -=), the lvalue is also used.
        if stmt.op != '=':
            uses |= defs
            
    elif isinstance(stmt, c_ast.Return):
        # return x; -> Uses: {x}
        uses = _extract_ids(stmt.expr)
        
    elif isinstance(stmt, c_ast.UnaryOp) and stmt.op in ("p++", "p--", "++", "--"):
        # x++; -> Defs: {x}, Uses: {x}
        ids = _extract_ids(stmt.expr)
        defs, uses = ids, ids
        
    else:
        # Fallback: Treat everything else (like function calls) as a strict Use.
        uses = _extract_ids(stmt)

    return f"{text};", defs, uses


# --- 2. THE GRAPH ARCHITECTURE ---

class CFG:
    """The State Machine Wrapper"""
    def __init__(self, function_name: str):
        self.function_name = function_name
        self.graph = nx.DiGraph()
        self.entry = "start"
        self.exit = "end"
        self._counter = 1
        
        self.graph.add_node(self.entry, label="Start", defs=set(), uses=set())
        self.graph.add_node(self.exit, label="End", defs=set(), uses=set())

    def add_node(self, label: str, defs: set[str] = None, uses: set[str] = None) -> str:
        """Allocates the node and attaches the data-flow sets to NetworkX."""
        node_id = f"n{self._counter}"
        self._counter += 1
        self.graph.add_node(
            node_id, 
            label=label, 
            defs=defs or set(), 
            uses=uses or set()
        )
        return node_id

    def add_edge(self, src: str, dst: str, branch: str = None):
        self.graph.add_edge(src, dst, branch=branch)


# --- 3. THE RECURSIVE BUILDER ---

def _build_stmt(cfg: CFG, stmt: c_ast.Node, incoming: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    Recursively flattens the AST into basic blocks and tracks execution edges.
    """
    if isinstance(stmt, c_ast.Compound):
        out = incoming
        for inner_stmt in (stmt.block_items or []):
            out = _build_stmt(cfg, inner_stmt, out)
        return out

    if isinstance(stmt, c_ast.If):
        cond_text = f"if ({generator.visit(stmt.cond)})"
        # The condition evaluation reads variables, but defines none.
        cond_uses = _extract_ids(stmt.cond)
        cond_node = cfg.add_node(label=cond_text, defs=set(), uses=cond_uses)
        
        for src, branch in incoming:
            cfg.add_edge(src, cond_node, branch)

        then_out = [(cond_node, "T")]
        if stmt.iftrue:
            then_out = _build_stmt(cfg, stmt.iftrue, then_out)

        else_out = [(cond_node, "F")]
        if stmt.iffalse:
            else_out = _build_stmt(cfg, stmt.iffalse, else_out)

        return then_out + else_out

    if isinstance(stmt, c_ast.While):
        cond_text = f"while ({generator.visit(stmt.cond)})"
        cond_uses = _extract_ids(stmt.cond)
        cond_node = cfg.add_node(label=cond_text, defs=set(), uses=cond_uses)
        
        for src, branch in incoming:
            cfg.add_edge(src, cond_node, branch)

        if stmt.stmt:
            body_out = _build_stmt(cfg, stmt.stmt, [(cond_node, "T")])
            for src, _ in body_out:
                cfg.add_edge(src, cond_node)
        else:
            cfg.add_edge(cond_node, cond_node, branch="T")

        return [(cond_node, "F")]

    # Normal Sequential Instruction (Decl, Assignment, FuncCall, Return)
    text, defs, uses = _analyze_statement(stmt)
    node_id = cfg.add_node(label=text, defs=defs, uses=uses)
    
    for src, branch in incoming:
        cfg.add_edge(src, node_id, branch)
        
    # If the instruction is a return, execution terminates. 
    # We immediately route it to the Exit node and return an empty active frontier.
    if isinstance(stmt, c_ast.Return):
        cfg.add_edge(node_id, cfg.exit)
        return []

    return [(node_id, None)]


def build_cfg(func: c_ast.FuncDef, include_unreachable: bool = False) -> CFG:
    """The Architectural Entry Point"""
    cfg = CFG(func.decl.name)
    current_frontier = [(cfg.entry, None)]
    
    if func.body.block_items:
        final_frontier = _build_stmt(cfg, func.body, current_frontier)
        for src, branch in final_frontier:
            cfg.add_edge(src, cfg.exit, branch)
    else:
        # Empty function body
        cfg.add_edge(cfg.entry, cfg.exit)
        
    return cfg