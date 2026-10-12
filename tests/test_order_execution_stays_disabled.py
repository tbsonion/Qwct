"""Compile-level research-only invariant across entire Qwct algorithm tree.

Not a LEAN integration test. New strategy modules cannot introduce
native order-submission calls while PR #7 is research-only.
"""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = [ROOT / "main.py", *(ROOT / "strategy").rglob("*.py")]

# API denylist restricted to native execution methods; cancel/liquidate
# remain in EOD code behind source-level _native_exit_enabled = False.
NATIVE_ORDER_CALLS = {
    "market_order", "limit_order", "stop_market_order",
    "stop_limit_order", "market_on_open_order",
    "market_on_close_order", "market_on_close",
    "trailing_stop_order", "combo_market_order",
    "combo_limit_order", "bracket_order", "set_holdings",
    "buy", "sell", "submit_order", "order",
}


def test_all_sources_are_parseable_and_no_order_submission_method_exists():
    for path in SOURCE:
        code = path.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(path))
        attempted = [
            (node.lineno, node.func.attr)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in NATIVE_ORDER_CALLS
        ]
        assert not attempted, (str(path.relative_to(ROOT)), attempted)


def test_only_known_disabled_main_eod_code_may_include_liquidate():
    seen = []
    for path in SOURCE:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "liquidate"):
                seen.append((path.relative_to(ROOT).as_posix(), node.lineno))
    assert len(seen) == 1 and seen[0][0] == "main.py"
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "self._native_exit_enabled = False" in main
    # Reject reassignments that would defeat the source-level kill switch.
    source_tree = ast.parse(main)
    enabling = [
        n for n in ast.walk(source_tree)
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        for target in (
            n.targets if isinstance(n, ast.Assign)
            else [n.target]
        )
        if isinstance(target, ast.Attribute)
        and target.attr == "_native_exit_enabled"
        and not (isinstance(n, ast.Assign)
                 and isinstance(n.value, ast.Constant)
                 and n.value.value is False)
    ]
    assert not enabling, "trading kill-switch reassigned"
    algorithm_class = next(
        n for n in source_tree.body
        if isinstance(n, ast.ClassDef)
        and n.name == "QwctGerchikAlgorithm")
    for method in ("_cancel_before_close", "_end_session",
                   "_verify_flat_before_close"):
        fn = next(
            n for n in algorithm_class.body
            if isinstance(n, ast.FunctionDef) and n.name == method)
        guards = [
            node for node in fn.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Attribute)
            and node.test.operand.attr == "_native_exit_enabled"
            and any(isinstance(t, ast.Return) for t in ast.walk(node))
        ]
        assert guards, f"{method} missing explicit no-trading return"
