from __future__ import annotations
from pathlib import Path
import networkx as nx

from cfg_optimizer.cfg import CFG



def export_cfg_to_dot(cfg: CFG, path: str | Path) -> None:
    """Translates the NetworkX memory state into a strict Graphviz DOT file."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    view = nx.DiGraph()
    
    # 1. Map the Nodes
    for node, attrs in cfg.graph.nodes(data=True):
        label = attrs.get("label", "")
        defs = list(attrs.get("defs", set()))
        uses = list(attrs.get("uses", set()))
        
        # Format the text block strictly. 
        # Only show defs/uses if they actually exist, keeping the graph visually clean.
        text = f"{node}\\n{label}"
        if defs or uses:
            text += f"\\ndefs={defs}\\nuses={uses}"
            
        view.add_node(node, label=text, shape="box")

    # 2. Map the Edges
    for src, dst, attrs in cfg.graph.edges(data=True):
        edge_label = attrs.get("branch")
        
        # Only attach a label if it's a True/False branch
        if edge_label:
            view.add_edge(src, dst, label=edge_label)
        else:
            view.add_edge(src, dst)

    # 3. Write to disk
    nx.nx_pydot.write_dot(view, str(out_path))




#for call graphs writing from graph to dot. 
def export_call_graph_to_dot(call_graph: nx.DiGraph, path: str | Path) -> None:
    """Translates the Call Graph memory state into Graphviz DOT syntax."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    view = nx.DiGraph()
    
    # Use ellipses for call graph nodes to visually distinguish them from CFG boxes
    for node in call_graph.nodes:
        view.add_node(node, label=node, shape="ellipse", style="filled", fillcolor="lightblue")

    for src, dst in call_graph.edges:
        view.add_edge(src, dst, label="calls")

    nx.nx_pydot.write_dot(view, str(out_path))