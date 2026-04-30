from __future__ import annotations

import ast
import math
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

_INT_RE = re.compile(r"^[+-]?\d+$")
_SIMPLE_BIN_RE = re.compile(
    r"^\s*\(?\s*(?P<a>[A-Za-z_][A-Za-z0-9_]*|\d+)\s*\)?\s*"
    r"(?P<op><<|>>|\+|\-|\*|/|%|&|\||\^)\s*"
    r"\(?\s*(?P<b>[A-Za-z_][A-Za-z0-9_]*|\d+)\s*\)?\s*$"
)
_COMMUTATIVE_OPS = {"+", "*", "&", "|", "^"}
_FOR_COND_RE = re.compile(r"^for-cond\s*\((?P<cond>.+)\)\s*$")

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


def _strip_parens(token: str) -> str:
    text = token.strip()
    if text.startswith("(") and text.endswith(")"):
        inner = text[1:-1].strip()
        if inner:
            return inner
    return text


def _is_identifier(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token))


def _is_int_literal(token: str) -> bool:
    return bool(_INT_RE.match(token.strip()))


def _parse_simple_binary(expr: str) -> Optional[tuple[str, str, str]]:
    match = _SIMPLE_BIN_RE.match(expr.strip())
    if not match:
        return None
    left = _strip_parens(match.group("a"))
    op = match.group("op")
    right = _strip_parens(match.group("b"))
    return left, op, right


def _canonical_expr_key(left: str, op: str, right: str) -> str:
    if op in _COMMUTATIVE_OPS:
        left, right = sorted([left, right])
    return f"{op}|{left}|{right}"


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


def common_subexpression_elimination(cfg: CFG) -> List[Dict[str, str]]:
    g = cfg.graph
    actions: List[Dict[str, str]] = []

    available: Dict[str, str] = {}
    expr_operands: Dict[str, set[str]] = {}
    expr_result: Dict[str, str] = {}
    var_to_exprs: Dict[str, set[str]] = {}

    def clear_all() -> None:
        available.clear()
        expr_operands.clear()
        expr_result.clear()
        var_to_exprs.clear()

    def invalidate_var(var: str) -> None:
        keys = set(var_to_exprs.get(var, set()))
        for key in keys:
            operands = expr_operands.pop(key, set())
            result = expr_result.pop(key, None)
            available.pop(key, None)

            related = set(operands)
            if result:
                related.add(result)
            for name in related:
                exprs = var_to_exprs.get(name)
                if exprs is None:
                    continue
                exprs.discard(key)
                if not exprs:
                    var_to_exprs.pop(name, None)

        var_to_exprs.pop(var, None)

    def track_expr(key: str, operands: set[str], result: str) -> None:
        available[key] = result
        expr_operands[key] = set(operands)
        expr_result[key] = result
        for name in operands | {result}:
            var_to_exprs.setdefault(name, set()).add(key)

    for node in list(g.nodes):
        attrs = g.nodes[node]
        kind = attrs.get("kind")

        if kind in {"start", "end", "cond", "return", "unreachable"}:
            clear_all()
            continue

        if g.in_degree(node) > 1:
            clear_all()

        label = attrs.get("label", "")
        if _CALL_RE.search(label):
            clear_all()
            continue

        defs = set(attrs.get("defs", set()))
        for var in defs:
            invalidate_var(var)

        parsed = _parse_assignment(label)
        if not parsed:
            continue

        expr = parsed["expr"].strip()
        if _CALL_RE.search(expr):
            continue

        parsed_bin = _parse_simple_binary(expr)
        if not parsed_bin:
            continue

        left, op, right = parsed_bin
        key = _canonical_expr_key(left, op, right)
        dest = parsed["var"]
        operands = {token for token in (left, right) if _is_identifier(token)}

        if key in available:
            cached = available[key]
            if cached != dest:
                if parsed["kind"] == "assign":
                    new_label = f"{dest} = {cached};"
                else:
                    new_label = f"{parsed['prefix']}{dest} = {cached};"

                if new_label != label:
                    attrs["label"] = new_label
                    _refresh_node_data(cfg, node)
                    actions.append(
                        {
                            "pass": "common_subexpression_elimination",
                            "node": node,
                            "before": label,
                            "after": new_label,
                        }
                    )
            continue

        if dest in operands:
            continue

        track_expr(key, operands, dest)

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


def strength_reduction(cfg: CFG) -> List[Dict[str, str]]:
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
        parsed_bin = _parse_simple_binary(expr)
        if not parsed_bin:
            continue

        left, op, right = parsed_bin
        if op != "*":
            continue

        if _is_int_literal(left) and _is_identifier(right):
            const_token = left
            var_token = right
        elif _is_int_literal(right) and _is_identifier(left):
            const_token = right
            var_token = left
        else:
            continue

        const_value = int(const_token)
        if const_value <= 1:
            continue
        if const_value & (const_value - 1) != 0:
            continue

        shift = int(math.log2(const_value))
        new_expr = f"{var_token} << {shift}"

        if parsed["kind"] == "assign":
            new_label = f"{parsed['var']} = {new_expr};"
        else:
            new_label = f"{parsed['prefix']}{parsed['var']} = {new_expr};"

        if new_label != label:
            attrs["label"] = new_label
            _refresh_node_data(cfg, node)
            actions.append(
                {
                    "pass": "strength_reduction",
                    "node": node,
                    "before": label,
                    "after": new_label,
                }
            )

    return actions


def _parse_for_condition(label: str) -> Optional[tuple[str, str, int]]:
    match = _FOR_COND_RE.match(label.strip())
    if not match:
        return None

    cond = match.group("cond").strip()
    left_id = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(<=|<|>=|>)\s*(\d+)\s*$", cond)
    if left_id:
        var = left_id.group(1)
        op = left_id.group(2)
        bound = int(left_id.group(3))
        if op in {">", ">="}:
            return None
        return var, op, bound

    right_id = re.match(r"^(\d+)\s*(<=|<|>=|>)\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", cond)
    if not right_id:
        return None

    bound = int(right_id.group(1))
    op = right_id.group(2)
    var = right_id.group(3)
    if op == ">":
        return var, "<", bound
    if op == ">=":
        return var, "<=", bound
    return None


def _parse_increment(label: str, var: str) -> Optional[int]:
    assign = _parse_assignment(label)
    if assign and assign["var"] == var:
        expr = assign["expr"].strip()
        match = re.match(rf"^{re.escape(var)}\s*\+\s*1$", expr)
        if match:
            return 1
    if re.match(rf"^\s*{re.escape(var)}\s*\+\+\s*;\s*$", label):
        return 1
    if re.match(rf"^\s*\+\+\s*{re.escape(var)}\s*;\s*$", label):
        return 1
    return None


def loop_unrolling(cfg: CFG, max_unroll: int = 4) -> List[Dict[str, str]]:
    g = cfg.graph
    actions: List[Dict[str, str]] = []

    for cond_node in list(g.nodes):
        if cond_node not in g:
            continue
        attrs = g.nodes[cond_node]
        if attrs.get("kind") != "cond":
            continue

        cond_label = attrs.get("label", "")
        parsed_cond = _parse_for_condition(cond_label)
        if not parsed_cond:
            continue

        var, op, bound = parsed_cond

        t_succs = [
            succ
            for _, succ, edge_attrs in g.out_edges(cond_node, data=True)
            if edge_attrs.get("branch") == "T"
        ]
        if len(t_succs) != 1:
            continue

        body_start = t_succs[0]
        body_nodes: List[str] = []
        visited: set[str] = set()
        current = body_start
        increment_node: Optional[str] = None

        while True:
            if current in visited or current == cond_node:
                break
            visited.add(current)

            current_attrs = g.nodes[current]
            if current_attrs.get("kind") != "stmt":
                break

            if g.in_degree(current) > 1:
                break

            body_nodes.append(current)

            if g.has_edge(current, cond_node):
                increment_node = current
                break

            succs = list(g.successors(current))
            if len(succs) != 1:
                break
            if g.out_degree(current) != 1:
                break

            current = succs[0]

        if increment_node is None:
            continue

        if increment_node not in body_nodes:
            continue

        if g.out_degree(increment_node) != 1:
            continue

        if _parse_increment(g.nodes[increment_node].get("label", ""), var) != 1:
            continue

        preds = list(g.predecessors(cond_node))
        if len(preds) != 2:
            continue

        init_node = preds[0] if preds[1] == increment_node else preds[1] if preds[0] == increment_node else None
        if init_node is None:
            continue

        init_attrs = g.nodes[init_node]
        if init_attrs.get("kind") != "stmt":
            continue

        init_parsed = _parse_assignment(init_attrs.get("label", ""))
        if not init_parsed or init_parsed["var"] != var:
            continue

        init_expr = init_parsed["expr"].strip()
        if _extract_ids(init_expr):
            continue
        init_value = _safe_eval(init_expr)
        if init_value is None or not isinstance(init_value, int):
            continue

        if op == "<":
            trip_count = bound - init_value
        else:
            trip_count = bound - init_value + 1

        if trip_count <= 0 or trip_count > max_unroll:
            continue

        after_succs = [
            (succ, edge_attrs)
            for _, succ, edge_attrs in g.out_edges(cond_node, data=True)
            if edge_attrs.get("branch") == "F"
        ]
        if not after_succs:
            continue

        incoming_edges = list(g.in_edges(cond_node, data=True))

        clone_iterations: List[List[str]] = []
        for _ in range(trip_count):
            clone_nodes: List[str] = []
            for original in body_nodes:
                original_attrs = g.nodes[original]
                clone_id = cfg.add_node(
                    kind=original_attrs.get("kind", "stmt"),
                    label=original_attrs.get("label", ""),
                    defs=set(original_attrs.get("defs", set())),
                    uses=set(original_attrs.get("uses", set())),
                )
                clone_nodes.append(clone_id)

            for idx in range(len(clone_nodes) - 1):
                cfg.add_edge(clone_nodes[idx], clone_nodes[idx + 1])

            clone_iterations.append(clone_nodes)

        if not clone_iterations:
            continue

        first_clone = clone_iterations[0][0]
        last_clone = clone_iterations[-1][-1]

        for pred, _, edge_attrs in incoming_edges:
            if pred == increment_node:
                continue
            branch = edge_attrs.get("branch") if edge_attrs else None
            if branch is None:
                cfg.add_edge(pred, first_clone)
            else:
                cfg.add_edge(pred, first_clone, branch=branch)

        for iteration_idx in range(len(clone_iterations) - 1):
            cfg.add_edge(clone_iterations[iteration_idx][-1], clone_iterations[iteration_idx + 1][0])

        for succ, edge_attrs in after_succs:
            branch = edge_attrs.get("branch") if edge_attrs else None
            if branch is None:
                cfg.add_edge(last_clone, succ)
            else:
                cfg.add_edge(last_clone, succ, branch=branch)

        for node_id in body_nodes + [cond_node]:
            if node_id in g:
                g.remove_node(node_id)

        actions.append(
            {
                "pass": "loop_unrolling",
                "node": cond_node,
                "before": cond_label,
                "after": f"unrolled {trip_count}x",
            }
        )

    return actions


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
    actions.extend(common_subexpression_elimination(cfg))
    actions.extend(strength_reduction(cfg))
    actions.extend(loop_unrolling(cfg))
    actions.extend(dead_code_elimination(cfg))
    actions.extend(unreachable_code_removal(cfg))
    return actions
