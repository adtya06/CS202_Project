from __future__ import annotations
import networkx as nx
from pycparser import c_ast

class FuncCallVisitor(c_ast.NodeVisitor):
    """
    Crawls a function body and extracts the names of every function being called.
    """
    def __init__(self):
        self.calls: set[str] = set()

    def visit_FuncCall(self, node: c_ast.FuncCall) -> None:
        if isinstance(node.name, c_ast.ID):
            self.calls.add(node.name.name)
        # generic_visit ensures we catch nested calls, e.g., printf(get_data());
        self.generic_visit(node)


def build_call_graph(ast_root: c_ast.FileAST) -> nx.DiGraph:
    """
    Constructs the macro-level directed graph mapping caller -> callee.
    """
    cg = nx.DiGraph()

    for ext in ast_root.ext:
        if isinstance(ext, c_ast.FuncDef):
            caller_name = ext.decl.name
            
            # Ensure the node exists even if it doesn't call anything
            cg.add_node(caller_name) 

            # Sweep the function body for outgoing calls
            visitor = FuncCallVisitor()
            visitor.visit(ext.body)

            for callee_name in visitor.calls:
                # Add the target node and the directed edge
                cg.add_node(callee_name)
                cg.add_edge(caller_name, callee_name)

    return cg   