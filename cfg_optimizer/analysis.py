from __future__ import annotations
from typing import Dict, Set, Tuple
from cfg_optimizer.cfg import CFG

# A Definition is a tuple of (Variable_Name, Node_ID_Where_It_Was_Defined)
Definition = Tuple[str, str]

def compute_reaching_definitions(cfg: CFG) -> Dict[str, Dict[str, Set[Definition]]]:
    """
    Forward Analysis. Computes which variable assignments survive to reach specific nodes.
    Required for: Constant Propagation.
    """
    g = cfg.graph
    nodes = list(g.nodes)

    all_defs_by_var: Dict[str, Set[Definition]] = {}
    gen: Dict[str, Set[Definition]] = {}
    kill: Dict[str, Set[Definition]] = {}

    # 1. Compute GEN and global definitions
    for node in nodes:
        defs = set(g.nodes[node].get("defs", set()))
        gen[node] = {(var, node) for var in defs}
        for var in defs:
            all_defs_by_var.setdefault(var, set()).add((var, node))

    # 2. Compute KILL (All other definitions of the same variables)
    for node in nodes:
        defs = set(g.nodes[node].get("defs", set()))
        node_kill: Set[Definition] = set()
        for var in defs:
            node_kill |= all_defs_by_var.get(var, set())
        kill[node] = node_kill - gen[node]

    in_sets: Dict[str, Set[Definition]] = {n: set() for n in nodes}
    out_sets: Dict[str, Set[Definition]] = {n: set() for n in nodes}

    # 3. Fixed-Point Iteration
    changed = True
    while changed:
        changed = False
        for node in nodes:
            next_in: Set[Definition] = set()
            for pred in g.predecessors(node):
                next_in |= out_sets[pred]

            next_out = gen[node] | (next_in - kill[node])
            
            if next_in != in_sets[node] or next_out != out_sets[node]:
                in_sets[node] = next_in
                out_sets[node] = next_out
                changed = True

    return {"in": in_sets, "out": out_sets}


def compute_live_variables(cfg: CFG) -> Dict[str, Dict[str, Set[str]]]:
    """
    Backward Analysis. Computes which variables will be read in the future.
    Required for: Dead Assignment Elimination.
    """
    g = cfg.graph
    nodes = list(g.nodes)

    in_sets: Dict[str, Set[str]] = {n: set() for n in nodes}
    out_sets: Dict[str, Set[str]] = {n: set() for n in nodes}

    changed = True
    while changed:
        changed = False
        # Traverse backwards for efficiency in Backward Analysis
        for node in reversed(nodes):
            uses = set(g.nodes[node].get("uses", set()))
            defs = set(g.nodes[node].get("defs", set()))

            next_out: Set[str] = set()
            for succ in g.successors(node):
                next_out |= in_sets[succ]

            next_in = uses | (next_out - defs)
            
            if next_in != in_sets[node] or next_out != out_sets[node]:
                in_sets[node] = next_in
                out_sets[node] = next_out
                changed = True

    return {"in": in_sets, "out": out_sets}