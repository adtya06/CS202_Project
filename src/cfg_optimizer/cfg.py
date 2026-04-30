from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

import networkx as nx
from pycparser import c_ast, c_generator


generator = c_generator.CGenerator()


class _IdCollector(c_ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_ID(self, node: c_ast.ID) -> None:
        self.names.add(node.name)


def _extract_ids(node: c_ast.Node | None) -> set[str]:
    if node is None:
        return set()
    collector = _IdCollector()
    collector.visit(node)
    return collector.names


def _node_to_text(node: c_ast.Node | None) -> str:
    if node is None:
        return ""
    return generator.visit(node)


def _as_stmt_list(stmt: c_ast.Node | None) -> List[c_ast.Node]:
    if stmt is None:
        return []
    if isinstance(stmt, c_ast.Compound):
        return list(stmt.block_items or [])
    return [stmt]


def _analyze_simple_statement(stmt: c_ast.Node) -> Tuple[str, set[str], set[str]]:
    if isinstance(stmt, c_ast.Decl):
        defs = {stmt.name} if stmt.name else set()
        uses = _extract_ids(stmt.init)
        return f"{_node_to_text(stmt)};", defs, uses

    if isinstance(stmt, c_ast.Assignment):
        defs = _extract_ids(stmt.lvalue)
        uses = _extract_ids(stmt.rvalue) | (_extract_ids(stmt.lvalue) - defs)
        return f"{_node_to_text(stmt)};", defs, uses

    if isinstance(stmt, c_ast.Return):
        uses = _extract_ids(stmt.expr)
        return f"{_node_to_text(stmt)};", set(), uses

    if isinstance(stmt, c_ast.FuncCall):
        uses = _extract_ids(stmt)
        return f"{_node_to_text(stmt)};", set(), uses

    if isinstance(stmt, c_ast.UnaryOp) and stmt.op in {"p++", "p--", "++", "--"}:
        ids = _extract_ids(stmt.expr)
        return f"{_node_to_text(stmt)};", ids, ids

    if isinstance(stmt, c_ast.Break):
        return "break;", set(), set()

    if isinstance(stmt, c_ast.Continue):
        return "continue;", set(), set()

    return f"{_node_to_text(stmt)};", set(), _extract_ids(stmt)


@dataclass
class CFG:
    function_name: str
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    entry: str = "start"
    exit: str = "end"
    _counter: int = 1

    def __post_init__(self) -> None:
        self.graph.add_node(self.entry, kind="start", label="Start", defs=set(), uses=set())
        self.graph.add_node(self.exit, kind="end", label="End", defs=set(), uses=set())

    def add_node(self, kind: str, label: str, defs: set[str] | None = None, uses: set[str] | None = None) -> str:
        node_id = f"n{self._counter}"
        self._counter += 1
        self.graph.add_node(node_id, kind=kind, label=label, defs=defs or set(), uses=uses or set())
        return node_id

    def add_edge(self, src: str, dst: str, branch: str | None = None) -> None:
        attrs = {}
        if branch is not None:
            attrs["branch"] = branch
        self.graph.add_edge(src, dst, **attrs)


def _connect_incoming(cfg: CFG, incoming: Sequence[Tuple[str, str | None]], dst: str) -> None:
    for src, branch in incoming:
        cfg.add_edge(src, dst, branch)


def _emit_simple_stmt(cfg: CFG, stmt: c_ast.Node, incoming: Sequence[Tuple[str, str | None]]) -> List[Tuple[str, str | None]]:
    text, defs, uses = _analyze_simple_statement(stmt)
    kind = "return" if isinstance(stmt, c_ast.Return) else "stmt"
    node_id = cfg.add_node(kind=kind, label=text, defs=defs, uses=uses)
    _connect_incoming(cfg, incoming, node_id)

    if isinstance(stmt, c_ast.Return):
        cfg.add_edge(node_id, cfg.exit)
        return []

    return [(node_id, None)]


def _emit_for_init(cfg: CFG, init: c_ast.Node | None, incoming: Sequence[Tuple[str, str | None]]) -> List[Tuple[str, str | None]]:
    if init is None:
        return list(incoming)

    if isinstance(init, c_ast.DeclList):
        out = list(incoming)
        for decl in init.decls:
            out = _emit_simple_stmt(cfg, decl, out)
        return out

    if isinstance(init, c_ast.ExprList):
        out = list(incoming)
        for expr in init.exprs:
            out = _emit_simple_stmt(cfg, expr, out)
        return out

    return _emit_simple_stmt(cfg, init, incoming)


def _emit_for_next(cfg: CFG, nxt: c_ast.Node | None, incoming: Sequence[Tuple[str, str | None]]) -> List[Tuple[str, str | None]]:
    if nxt is None:
        return list(incoming)
    if isinstance(nxt, c_ast.ExprList):
        out = list(incoming)
        for expr in nxt.exprs:
            out = _emit_simple_stmt(cfg, expr, out)
        return out
    return _emit_simple_stmt(cfg, nxt, incoming)


def _build_stmt(
    cfg: CFG,
    stmt: c_ast.Node,
    incoming: Sequence[Tuple[str, str | None]],
    include_unreachable: bool,
) -> List[Tuple[str, str | None]]:
    if isinstance(stmt, c_ast.Compound):
        return _build_stmt_list(cfg, _as_stmt_list(stmt), incoming, include_unreachable)

    if isinstance(stmt, c_ast.If):
        cond_text = f"if ({_node_to_text(stmt.cond)})"
        cond_node = cfg.add_node(kind="cond", label=cond_text, defs=set(), uses=_extract_ids(stmt.cond))
        _connect_incoming(cfg, incoming, cond_node)

        then_stmts = _as_stmt_list(stmt.iftrue)
        else_stmts = _as_stmt_list(stmt.iffalse)

        then_out = (
            _build_stmt_list(cfg, then_stmts, [(cond_node, "T")], include_unreachable)
            if then_stmts
            else [(cond_node, "T")]
        )
        else_out = (
            _build_stmt_list(cfg, else_stmts, [(cond_node, "F")], include_unreachable)
            if else_stmts
            else [(cond_node, "F")]
        )

        return then_out + else_out

    if isinstance(stmt, c_ast.While):
        cond_text = f"while ({_node_to_text(stmt.cond)})"
        cond_node = cfg.add_node(kind="cond", label=cond_text, defs=set(), uses=_extract_ids(stmt.cond))
        _connect_incoming(cfg, incoming, cond_node)

        body_stmts = _as_stmt_list(stmt.stmt)
        if body_stmts:
            body_out = _build_stmt_list(cfg, body_stmts, [(cond_node, "T")], include_unreachable)
            for src, _ in body_out:
                cfg.add_edge(src, cond_node)
        else:
            cfg.add_edge(cond_node, cond_node, branch="T")

        return [(cond_node, "F")]

    if isinstance(stmt, c_ast.For):
        init_out = _emit_for_init(cfg, stmt.init, incoming)
        cond_text = "for-cond (true)" if stmt.cond is None else f"for-cond ({_node_to_text(stmt.cond)})"
        cond_uses = set() if stmt.cond is None else _extract_ids(stmt.cond)
        cond_node = cfg.add_node(kind="cond", label=cond_text, defs=set(), uses=cond_uses)
        _connect_incoming(cfg, init_out, cond_node)

        body_stmts = _as_stmt_list(stmt.stmt)
        body_out = (
            _build_stmt_list(cfg, body_stmts, [(cond_node, "T")], include_unreachable)
            if body_stmts
            else [(cond_node, "T")]
        )
        next_out = _emit_for_next(cfg, stmt.next, body_out)
        for src, _ in next_out:
            cfg.add_edge(src, cond_node)

        return [(cond_node, "F")]

    return _emit_simple_stmt(cfg, stmt, incoming)


def _emit_unreachable(cfg: CFG, stmt: c_ast.Node) -> None:
    if isinstance(stmt, c_ast.Compound):
        for inner in _as_stmt_list(stmt):
            _emit_unreachable(cfg, inner)
        return

    text, defs, uses = _analyze_simple_statement(stmt)
    label = f"unreachable: {text}"
    cfg.add_node(kind="unreachable", label=label, defs=defs, uses=uses)


def _build_stmt_list(
    cfg: CFG,
    stmts: Sequence[c_ast.Node],
    incoming: Sequence[Tuple[str, str | None]],
    include_unreachable: bool,
) -> List[Tuple[str, str | None]]:
    out = list(incoming)
    for stmt in stmts:
        if not out:
            if include_unreachable:
                _emit_unreachable(cfg, stmt)
                continue
            break
        out = _build_stmt(cfg, stmt, out, include_unreachable)
    return out


def build_cfg(func: c_ast.FuncDef, include_unreachable: bool = False) -> CFG:
    cfg = CFG(function_name=func.decl.name)
    body_stmts = _as_stmt_list(func.body)
    out = _build_stmt_list(cfg, body_stmts, [(cfg.entry, None)], include_unreachable)
    for src, branch in out:
        cfg.add_edge(src, cfg.exit, branch)
    if not body_stmts:
        cfg.add_edge(cfg.entry, cfg.exit)
    return cfg
