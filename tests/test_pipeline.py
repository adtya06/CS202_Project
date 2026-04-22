from cfg_optimizer.analysis import analyses_to_report
from cfg_optimizer.ast_parser import get_function_defs, parse_c_code
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
