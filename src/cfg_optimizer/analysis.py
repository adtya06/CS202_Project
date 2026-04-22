from __future__ import annotations

from typing import Dict, List, Set, Tuple

from cfg_optimizer.cfg import CFG

Definition = Tuple[str, str]


def compute_reaching_definitions(cfg: CFG) -> Dict[str, Dict[str, Set[Definition]]]:
    g = cfg.graph
    nodes = list(g.nodes)

    all_defs_by_var: Dict[str, Set[Definition]] = {}
    gen: Dict[str, Set[Definition]] = {}
    kill: Dict[str, Set[Definition]] = {}

    for node in nodes:
        defs = set(g.nodes[node].get("defs", set()))
        node_gen = {(var, node) for var in defs}
        gen[node] = node_gen
        for var in defs:
            all_defs_by_var.setdefault(var, set()).add((var, node))

    for node in nodes:
        defs = set(g.nodes[node].get("defs", set()))
        node_kill: Set[Definition] = set()
        for var in defs:
            node_kill |= all_defs_by_var.get(var, set())
        node_kill -= gen[node]
        kill[node] = node_kill

    in_sets: Dict[str, Set[Definition]] = {n: set() for n in nodes}
    out_sets: Dict[str, Set[Definition]] = {n: set() for n in nodes}

    changed = True
    while changed:
        changed = False
        for node in nodes:
            preds = list(g.predecessors(node))
            next_in: Set[Definition] = set()
            for pred in preds:
                next_in |= out_sets[pred]

            next_out = gen[node] | (next_in - kill[node])
            if next_in != in_sets[node] or next_out != out_sets[node]:
                in_sets[node] = next_in
                out_sets[node] = next_out
                changed = True

    return {"in": in_sets, "out": out_sets}


def compute_live_variables(cfg: CFG) -> Dict[str, Dict[str, Set[str]]]:
    g = cfg.graph
    nodes = list(g.nodes)

    in_sets: Dict[str, Set[str]] = {n: set() for n in nodes}
    out_sets: Dict[str, Set[str]] = {n: set() for n in nodes}

    changed = True
    while changed:
        changed = False
        for node in reversed(nodes):
            uses = set(g.nodes[node].get("uses", set()))
            defs = set(g.nodes[node].get("defs", set()))

            succs = list(g.successors(node))
            next_out: Set[str] = set()
            for succ in succs:
                next_out |= in_sets[succ]

            next_in = uses | (next_out - defs)
            if next_in != in_sets[node] or next_out != out_sets[node]:
                in_sets[node] = next_in
                out_sets[node] = next_out
                changed = True

    return {"in": in_sets, "out": out_sets}


def find_potential_uninitialized_uses(cfg: CFG, reaching: Dict[str, Dict[str, Set[Definition]]]) -> Dict[str, List[str]]:
    g = cfg.graph
    in_sets = reaching["in"]
    warnings: Dict[str, List[str]] = {}

    for node in g.nodes:
        uses = set(g.nodes[node].get("uses", set()))
        for var in sorted(uses):
            reaching_defs = {d for d in in_sets[node] if d[0] == var}
            if not reaching_defs:
                warnings.setdefault(node, []).append(var)

    return warnings


def _serialize_defs(defs: Set[Definition]) -> List[str]:
    return sorted([f"{var}@{node}" for var, node in defs])


def analyses_to_report(cfg: CFG) -> Dict[str, object]:
    reaching = compute_reaching_definitions(cfg)
    live = compute_live_variables(cfg)
    uninit = find_potential_uninitialized_uses(cfg, reaching)

    reaching_report = {
        "in": {node: _serialize_defs(defs) for node, defs in reaching["in"].items()},
        "out": {node: _serialize_defs(defs) for node, defs in reaching["out"].items()},
    }

    live_report = {
        "in": {node: sorted(vals) for node, vals in live["in"].items()},
        "out": {node: sorted(vals) for node, vals in live["out"].items()},
    }

    return {
        "function": cfg.function_name,
        "reaching_definitions": reaching_report,
        "live_variables": live_report,
        "potential_uninitialized_uses": uninit,
    }