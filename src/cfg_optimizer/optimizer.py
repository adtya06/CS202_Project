from __future__ import annotations

import ast
import operator
import re
from typing import Dict, List, Optional

from cfg_optimizer.analysis import compute_live_variables, compute_reaching_definitions
from cfg_optimizer.cfg import CFG

_KEYWORDS = {
    "if",
    "else",
    "while",
    "for",
    "return",
    "sizeof",
    "int",
    "long",
    "short",
    "float",
    "double",
    "char",
    "unsigned",
    "signed",
    "void",
    "const",
    "static",
    "struct",
}

_ID_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+);\s*$")
_DECL_ASSIGN_RE = re.compile(r"^\s*((?:[A-Za-z_][A-Za-z0-9_]*\s+)+)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+);\s*$")

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _extract_ids(text: str) -> set[str]:
    names = set(_ID_RE.findall(text))
    call_names = set(_CALL_RE.findall(text))
    return {n for n in names if n not in _KEYWORDS and n not in call_names}


def _refresh_node_data(cfg: CFG, node: str) -> None:
    attrs = cfg.graph.nodes[node]
    label = attrs.get("label", "")
    defs = set(attrs.get("defs", set()))
    uses = _extract_ids(label) - defs
    attrs["defs"] = defs
    attrs["uses"] = uses


def _safe_eval(expr: str) -> Optional[float | int]:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def _eval(node: ast.AST):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            left = _eval(node.left)
            right = _eval(node.right)
            return _BIN_OPS[type(node.op)](left, right)
        raise ValueError("unsupported expression")

    try:
        return _eval(tree)
    except Exception:
        return None


def _parse_assignment(label: str):
    m = _ASSIGN_RE.match(label)
    if m:
        return {"kind": "assign", "prefix": "", "var": m.group(1), "expr": m.group(2)}
    d = _DECL_ASSIGN_RE.match(label)
    if d:
        return {"kind": "decl", "prefix": d.group(1), "var": d.group(2), "expr": d.group(3)}
    return None


def _format_number(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def constant_folding(cfg: CFG) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    for node in list(cfg.graph.nodes):
        attrs = cfg.graph.nodes[node]
        if attrs.get("kind") != "stmt":
            continue

        label = attrs.get("label", "")
        parsed = _parse_assignment(label)
        if not parsed:
            continue

        expr = parsed["expr"].strip()
        if _extract_ids(expr):
            continue

        folded = _safe_eval(expr)
        if folded is None:
            continue

        folded_text = _format_number(folded)
        if parsed["kind"] == "assign":
            new_label = f"{parsed['var']} = {folded_text};"
        else:
            new_label = f"{parsed['prefix']}{parsed['var']} = {folded_text};"

        if new_label != label:
            attrs["label"] = new_label
            _refresh_node_data(cfg, node)
            actions.append(
                {
                    "pass": "constant_folding",
                    "node": node,
                    "before": label,
                    "after": new_label,
                }
            )
    return actions


def _replace_var_in_expr(expr: str, var: str, value: str) -> str:
    pattern = re.compile(rf"\b{re.escape(var)}\b")
    return pattern.sub(value, expr)


def _replace_var_uses(label: str, var: str, value: str, defs: set[str]) -> str:
    parsed = _parse_assignment(label)
    if parsed:
        prefix = "" if parsed["kind"] == "assign" else parsed["prefix"]
        lhs = parsed["var"]
        rhs = parsed["expr"]
        replaced_rhs = _replace_var_in_expr(rhs, var, value)
        if parsed["kind"] == "assign":
            return f"{lhs} = {replaced_rhs};"
        return f"{prefix}{lhs} = {replaced_rhs};"

    if defs and var in defs:
        return label

    return _replace_var_in_expr(label, var, value)


def constant_propagation(cfg: CFG) -> List[Dict[str, str]]:
    reaching = compute_reaching_definitions(cfg)
    in_sets = reaching["in"]
    actions: List[Dict[str, str]] = []

    const_defs: Dict[tuple[str, str], str] = {}
    for node in cfg.graph.nodes:
        attrs = cfg.graph.nodes[node]
        if attrs.get("kind") != "stmt":
            continue
        parsed = _parse_assignment(attrs.get("label", ""))
        if not parsed:
            continue
        expr = parsed["expr"].strip()
        if _extract_ids(expr):
            continue
        value = _safe_eval(expr)
        if value is None:
            continue
        const_defs[(parsed["var"], node)] = _format_number(value)

    for node in list(cfg.graph.nodes):
        attrs = cfg.graph.nodes[node]
        uses = set(attrs.get("uses", set()))
        if not uses:
            continue

        before = attrs.get("label", "")
        after = before
        defs = set(attrs.get("defs", set()))

        for var in sorted(uses):
            defs_for_var = {d for d in in_sets[node] if d[0] == var}
            if len(defs_for_var) != 1:
                continue
            def_key = next(iter(defs_for_var))
            const_value = const_defs.get(def_key)
            if const_value is None:
                continue
            after = _replace_var_uses(after, var, const_value, defs)

        if after != before:
            attrs["label"] = after
            _refresh_node_data(cfg, node)
            actions.append(
                {
                    "pass": "constant_propagation",
                    "node": node,
                    "before": before,
                    "after": after,
                }
            )

    return actions


def _has_side_effects(label: str) -> bool:
    parsed = _parse_assignment(label)
    if not parsed:
        return True
    expr = parsed["expr"]
    return bool(_CALL_RE.search(expr))


def _remove_node_keep_flow(cfg: CFG, node: str) -> None:
    g = cfg.graph
    preds = list(g.in_edges(node, data=True))
    succs = list(g.out_edges(node, data=True))

    for pred, _, pred_data in preds:
        for _, succ, succ_data in succs:
            branch = pred_data.get("branch") if pred_data else None
            if branch is None:
                branch = succ_data.get("branch") if succ_data else None
            if branch is None:
                g.add_edge(pred, succ)
            else:
                g.add_edge(pred, succ, branch=branch)

    g.remove_node(node)


def dead_code_elimination(cfg: CFG) -> List[Dict[str, str]]:
    live = compute_live_variables(cfg)
    live_out = live["out"]
    actions: List[Dict[str, str]] = []

    for node in list(cfg.graph.nodes):
        attrs = cfg.graph.nodes[node]
        if attrs.get("kind") != "stmt":
            continue
        defs = set(attrs.get("defs", set()))
        if not defs:
            continue
        if _has_side_effects(attrs.get("label", "")):
            continue
        if defs & set(live_out.get(node, set())):
            continue

        before = attrs.get("label", "")
        _remove_node_keep_flow(cfg, node)
        actions.append({"pass": "dead_code_elimination", "node": node, "before": before, "after": "<removed>"})

    return actions


def unreachable_code_removal(cfg: CFG) -> List[Dict[str, str]]:
    g = cfg.graph
    reachable = set()
    stack = [cfg.entry]

    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        stack.extend(list(g.successors(node)))

    actions: List[Dict[str, str]] = []
    for node in list(g.nodes):
        if node in reachable:
            continue
        if node in {cfg.entry, cfg.exit}:
            continue
        before = g.nodes[node].get("label", "")
        g.remove_node(node)
        actions.append({"pass": "unreachable_code_removal", "node": node, "before": before, "after": "<removed>"})

    return actions


def apply_all(cfg: CFG) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    actions.extend(constant_folding(cfg))
    actions.extend(constant_propagation(cfg))
    actions.extend(constant_folding(cfg))
    actions.extend(dead_code_elimination(cfg))
    actions.extend(unreachable_code_removal(cfg))
    return actions
