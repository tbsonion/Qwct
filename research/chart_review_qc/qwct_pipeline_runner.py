"""QWCT 5.11 plain-text research runner.

Save this file in the project root beside main.py.
No compression, encoding, network, orders, or dynamic source execution.
This first repair is a safe import/module audit.
"""

from importlib import import_module

REQUIRED_MODULES = (
    "strategy.config",
    "strategy.features",
    "strategy.levels",
    "strategy.scenarios",
    "strategy.m5_runtime",
    "strategy.native_m5_validation",
)

def run():
    print("QWCT 5.11 RUNNER: PLAIN_TEXT NO_ORDERS")
    failures = []
    for name in REQUIRED_MODULES:
        try:
            import_module(name)
        except Exception as exc:
            failures.append({"module": name, "error": f"{type(exc).__name__}: {exc}"})
    if failures:
        print({"status": "LOADER_ERROR", "failures": failures, "can_trade": False})
        return
    print({
        "status": "MODULE_IMPORTS_OK",
        "can_trade": False,
        "orders": "DISABLED",
        "risk_gate": "UNCHANGED",
        "note": "Full acceptance evaluation remains separate; no signal or trade was created."
    })
