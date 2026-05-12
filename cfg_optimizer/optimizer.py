from __future__ import annotations
import re
from typing import List, Dict
import networkx as nx

from cfg_optimizer.cfg import CFG
from cfg_optimizer.analysis import compute_live_variables, compute_reaching_definitions


#checks all descendants of the start block anyone who is not is removed. 
def unreachable_code_removal(cfg: CFG) -> List[Dict[str, str]]:
    reachable = nx.descendants(cfg.graph, cfg.entry)
    reachable.add(cfg.entry)
    
    dead_nodes = set(cfg.graph.nodes()) - reachable
    if cfg.exit in dead_nodes:
        dead_nodes.remove(cfg.exit)
        
    if not dead_nodes:
        return []
        
    cfg.graph.remove_nodes_from(dead_nodes)
    return [{"optimization": "Unreachable Code Removal", "details": f"Destroyed {len(dead_nodes)} nodes."}]


def dead_code_elimination(cfg: CFG) -> List[Dict[str, str]]:
    """
    Pass 2: Deletes assignments to variables that are never used again.
    CRITICAL MECHANIC: Must bridge incoming and outgoing edges so the CFG doesn't break.
    """
    actions = []
    live_vars = compute_live_variables(cfg)
    nodes_to_delete = []


    for node in list(cfg.graph.nodes):
        if node in [cfg.entry, cfg.exit]: 
            continue
            
        defs = cfg.graph.nodes[node].get("defs", set())
        label = cfg.graph.nodes[node].get("label", "")
        
        # If it doesn't define anything, or it's a function call (side-effects), skip it.
        if not defs or "(" in label:
            continue
            
        live_out = live_vars["out"].get(node, set())
        
        # If ALL defined variables in this block are mathematically dead
        if all(v not in live_out for v in defs):
            nodes_to_delete.append((node, label))



    for node, label in nodes_to_delete:
        # Bridge the graph gap
        preds = list(cfg.graph.predecessors(node))
        succs = list(cfg.graph.successors(node))
        
        for p in preds:
            edge_data = cfg.graph.get_edge_data(p, node)
            branch = edge_data.get("branch")
            for s in succs:
                cfg.graph.add_edge(p, s, branch=branch)
                
        cfg.graph.remove_node(node)
        actions.append({"optimization": "Dead Code Elimination", "old": label, "new": "[DELETED]"})
        
    return actions


def constant_folding(cfg: CFG) -> List[Dict[str, str]]:
    """
    Pass 3: Computes raw integers at compile-time. (e.g., "x = 2 + 3;" -> "x = 5;")
    """
    actions = []
    # Matches simple integer math: "x = 5 + 10;"
    pattern = re.compile(r'^(\s*\w+\s*=\s*)(-?\d+)\s*([\+\-\*\/])\s*(-?\d+)\s*;$')
    
    for node in cfg.graph.nodes:
        label = cfg.graph.nodes[node].get("label", "")
        match = pattern.match(label)
        
        if match:
            prefix, left_str, op, right_str = match.groups()
            try:
                left, right = int(left_str), int(right_str)
                if op == '+': res = left + right
                elif op == '-': res = left - right
                elif op == '*': res = left * right
                elif op == '/': res = left // right  # C uses floor division for ints
                
                new_label = f"{prefix}{res};"
                cfg.graph.nodes[node]["label"] = new_label
                cfg.graph.nodes[node]["uses"] = set() # No variables used anymore
                
                actions.append({"optimization": "Constant Folding", "old": label, "new": new_label})
            except ZeroDivisionError:
                pass
                
    return actions


def constant_propagation(cfg: CFG) -> List[Dict[str, str]]:
    """
    Pass 4: Pushes known constants forward into subsequent equations.
    """
    actions = []
    reaching = compute_reaching_definitions(cfg)
    
    # 1. Map all strict constant assignments: "x = 5;"
    const_defs = {}
    const_pattern = re.compile(r'^\s*(\w+)\s*=\s*(-?\d+)\s*;$')
    for node in cfg.graph.nodes:
        label = cfg.graph.nodes[node].get("label", "")
        match = const_pattern.match(label)
        if match:
            var, val = match.groups()
            const_defs[node] = (var, val)
            
    # 2. Inject constants forward
    for node in cfg.graph.nodes:
        uses = cfg.graph.nodes[node].get("uses", set())
        if not uses: continue
        
        label = cfg.graph.nodes[node].get("label", "")
        reaching_in = reaching["in"].get(node, set())
        mutated = False
        
        for use_var in list(uses):
            # Isolate definitions of THIS variable that reach THIS node
            defs_for_var = {d_node for d_var, d_node in reaching_in if d_var == use_var}
            
            # Mathematical certainty: It is ONLY safe to propagate if exactly ONE definition reaches it.
            if len(defs_for_var) == 1:
                def_node = list(defs_for_var)[0]
                
                # Verify that the single definition is a known constant
                if def_node in const_defs and const_defs[def_node][0] == use_var:
                    const_val = const_defs[def_node][1]
                    
                    # Regex \b ensures we replace whole variables ('x'), not substrings of ('x_pos')
                    new_label = re.sub(rf'\b{use_var}\b', const_val, label)
                    
                    # Prevent replacing the left side of assignments (e.g. replacing 'x' in 'x = x + 1')
                    defs_here = cfg.graph.nodes[node].get("defs", set())
                    for d in defs_here:
                        new_label = re.sub(rf'^{const_val}\s*=', f"{d} =", new_label)

                    if new_label != label:
                        label = new_label
                        cfg.graph.nodes[node]["uses"].remove(use_var)
                        mutated = True
                        
        if mutated:
            actions.append({"optimization": "Constant Propagation", "old": cfg.graph.nodes[node]["label"], "new": label})
            cfg.graph.nodes[node]["label"] = label
            
    return actions


def strength_reduction(cfg: CFG) -> List[Dict[str, str]]:
    """
    Pass 5: Replaces expensive CPU operations (multiplication/division) with bitwise shifts.
    """
    actions = []
    
    # regex patterns for x * 2, 2 * x, x / 2
    pattern_mul2 = re.compile(r'\b(\w+)\s*\*\s*2\b')
    pattern_2mul = re.compile(r'\b2\s*\*\s*(\w+)\b')
    pattern_div2 = re.compile(r'\b(\w+)\s*\/\s*2\b')
    
    for node in cfg.graph.nodes:
        label = cfg.graph.nodes[node].get("label", "")
        original = label
        
        label = pattern_mul2.sub(r'\1 << 1', label)
        label = pattern_2mul.sub(r'\1 << 1', label)
        label = pattern_div2.sub(r'\1 >> 1', label)
        
        if label != original:
            cfg.graph.nodes[node]["label"] = label
            actions.append({"optimization": "Strength Reduction", "old": original, "new": label})
            
    return actions


def apply_all(cfg: CFG) -> List[Dict[str, str]]:
    """
    The Orchestrator. Cascades the mutations in the exact required order.
    """
    actions: List[Dict[str, str]] = []
    actions.extend(constant_propagation(cfg)); 
    actions.extend(constant_folding(cfg))
    actions.extend(constant_propagation(cfg))
    actions.extend(constant_folding(cfg))
    actions.extend(strength_reduction(cfg))
    actions.extend(dead_code_elimination(cfg))
    actions.extend(unreachable_code_removal(cfg))
    
    return actions

# def apply_all(cfg: CFG) -> List[Dict[str, str]]:
#     actions = []
    
#     # The Fixed-Point Loop
#     graph_mutated = True
#     while graph_mutated:
#         graph_mutated = False
        
#         # Run Propagation. If it changes anything, flip the flag.
#         prop_actions = constant_propagation(cfg)
#         if prop_actions:
#             actions.extend(prop_actions)
#             graph_mutated = True
            
#         # Run Folding. If it changes anything, flip the flag.
#         fold_actions = constant_folding(cfg)
#         if fold_actions:
#             actions.extend(fold_actions)
#             graph_mutated = True

#     # Once the loop exits (fixed-point reached), run the cleanup passes
#     actions.extend(strength_reduction(cfg))
#     actions.extend(dead_code_elimination(cfg))
#     actions.extend(unreachable_code_removal(cfg))
    
#     return actions