from __future__ import annotations

from pathlib import Path

import networkx as nx

from cfg_optimizer.cfg import CFG


def export_cfg_to_dot(cfg: CFG, path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    view = nx.DiGraph()
    for node, attrs in cfg.graph.nodes(data=True):
        kind = attrs.get("kind", "")
        label = attrs.get("label", "")
        defs = sorted(attrs.get("defs", set()))
        uses = sorted(attrs.get("uses", set()))
        text = f"{node}\\n[{kind}] {label}\\ndefs={defs} uses={uses}"
        view.add_node(node, label=text, shape="box")

    for src, dst, attrs in cfg.graph.edges(data=True):
        edge_label = attrs.get("branch", "")
        view.add_edge(src, dst, label=edge_label)

    nx.nx_pydot.write_dot(view, str(out_path))


def export_call_graph_to_dot(call_graph: nx.DiGraph, path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    view = nx.DiGraph()
    for node, attrs in call_graph.nodes(data=True):
        kind = attrs.get("kind", "internal")
        shape = "ellipse" if kind == "internal" else "diamond"
        text = f"{node}\\n[{kind}]"
        view.add_node(node, label=text, shape=shape)

    for src, dst in call_graph.edges():
        view.add_edge(src, dst, label="calls")

    nx.nx_pydot.write_dot(view, str(out_path))
