from __future__ import annotations

from typing import Dict, List

import networkx as nx
from pycparser import c_ast

from cfg_optimizer.ast_parser import get_function_defs


class _CallCollector(c_ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[str] = set()

    def visit_FuncCall(self, node: c_ast.FuncCall) -> None:
        if isinstance(node.name, c_ast.ID):
            self.calls.add(node.name.name)
        self.generic_visit(node)


def build_call_graph(ast_root: c_ast.FileAST, include_external: bool = False) -> nx.DiGraph:
    """Build a directed call graph for functions defined in a C translation unit."""
    funcs = get_function_defs(ast_root)
    internal = {f.decl.name for f in funcs}

    graph = nx.DiGraph()
    for name in sorted(internal):
        graph.add_node(name, kind="internal")

    for func in funcs:
        caller = func.decl.name
        collector = _CallCollector()
        collector.visit(func.body)

        for callee in sorted(collector.calls):
            if callee in internal:
                graph.add_edge(caller, callee)
                continue
            if include_external:
                graph.add_node(callee, kind="external")
                graph.add_edge(caller, callee)

    return graph


def call_graph_to_report(graph: nx.DiGraph) -> Dict[str, List[Dict[str, str]]]:
    nodes = [
        {"name": name, "kind": attrs.get("kind", "internal")}
        for name, attrs in sorted(graph.nodes(data=True), key=lambda item: item[0])
    ]
    edges = [{"caller": src, "callee": dst} for src, dst in sorted(graph.edges())]
    return {"nodes": nodes, "edges": edges}
