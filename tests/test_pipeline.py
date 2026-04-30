from cfg_optimizer.analysis import analyses_to_report
from cfg_optimizer.ast_parser import get_function_defs, parse_c_code
from cfg_optimizer.callgraph import build_call_graph, call_graph_to_report
from cfg_optimizer.cfg import build_cfg
from cfg_optimizer.optimizer import apply_all


CODE = """
int compute(int a) {
    int x = 3 + 5;
    int y = x + 2;
    int dead = 100;
    if (a > 0) {
        y = y + 1;
    } else {
        y = 10;
    }
    return y;
}
"""


CALL_CODE = """
int helper(int x) {
    return x + 1;
}

int compute(int a) {
    int y = helper(a);
    return y;
}
"""


def test_cfg_build_and_analysis():
    ast_root = parse_c_code(CODE)
    funcs = get_function_defs(ast_root)
    assert len(funcs) == 1

    cfg = build_cfg(funcs[0])
    report = analyses_to_report(cfg)

    assert report["function"] == "compute"
    assert "reaching_definitions" in report
    assert "live_variables" in report


def test_optimizations_apply():
    ast_root = parse_c_code(CODE)
    cfg = build_cfg(get_function_defs(ast_root)[0])

    actions = apply_all(cfg)
    applied = {a["pass"] for a in actions}

    assert "constant_folding" in applied
    assert "constant_propagation" in applied


def test_whole_program_call_graph():
    ast_root = parse_c_code(CALL_CODE)
    cg = build_call_graph(ast_root)
    report = call_graph_to_report(cg)

    nodes = {n["name"] for n in report["nodes"]}
    edges = {(e["caller"], e["callee"]) for e in report["edges"]}

    assert "helper" in nodes
    assert "compute" in nodes
    assert ("compute", "helper") in edges


def test_unreachable_statements_are_in_unoptimized_cfg():
    code = """
    int f() {
        return 1;
        int after = 2;
    }
    """
    ast_root = parse_c_code(code)
    cfg = build_cfg(get_function_defs(ast_root)[0], include_unreachable=True)
    labels = [attrs.get("label", "") for _, attrs in cfg.graph.nodes(data=True)]
    assert any("unreachable" in label and "after" in label for label in labels)


def test_common_subexpression_elimination_reuses_value():
    code = """
    int f(int a, int b) {
        int x = a + b;
        int y = a + b;
        return x + y;
    }
    """
    ast_root = parse_c_code(code)
    cfg = build_cfg(get_function_defs(ast_root)[0])
    _ = apply_all(cfg)

    labels = [attrs.get("label", "") for _, attrs in cfg.graph.nodes(data=True)]
    assert any("y = x;" in label for label in labels)


def test_strength_reduction_rewrites_power_of_two_mul():
    code = """
    int f(int x) {
        int y = x * 8;
        int z = 4 * x;
        return y + z;
    }
    """
    ast_root = parse_c_code(code)
    cfg = build_cfg(get_function_defs(ast_root)[0])
    _ = apply_all(cfg)

    labels = [attrs.get("label", "") for _, attrs in cfg.graph.nodes(data=True)]
    assert any("x << 3" in label for label in labels)
    assert any("x << 2" in label for label in labels)


def test_loop_unrolling_repeats_body_for_small_trip_count():
    code = """
    int f() {
        int sum = 0;
        for (int i = 0; i < 3; i = i + 1) {
            sum = sum + 1;
        }
        return sum;
    }
    """
    ast_root = parse_c_code(code)
    cfg = build_cfg(get_function_defs(ast_root)[0])
    _ = apply_all(cfg)

    labels = [attrs.get("label", "").strip() for _, attrs in cfg.graph.nodes(data=True)]
    assert labels.count("sum = sum + 1;") == 3
