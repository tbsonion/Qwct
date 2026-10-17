"""Verify the readable Cloud diagnostic runner and import-only notebook.

This builder intentionally does NOT encode/compress or overwrite the runner.
The Python runner is edited and reviewed directly, then pasted once in Cloud.
"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "research/chart_review_qc"
RUNNER = DIR / "qwct_pipeline_runner.py"
CELL = DIR / "QWCT_5_11_RUN_CELL.py"
NOTEBOOK = DIR / "QWCT_5_11_RESEARCH.ipynb"
PY_LIMIT = 32000
NB_LIMIT = 64000
OUTPUT_BUDGET = 16000


def build():
    code = RUNNER.read_text(encoding="utf-8")
    cell = CELL.read_text(encoding="utf-8")
    notebook = NOTEBOOK.read_text(encoding="utf-8")
    ast.parse(code)
    ast.parse(cell)
    if any(term in code for term in ("import base64", "import bz2",
                                    "import zlib", "exec(", "eval(")):
        raise ValueError("CLOUD_PLAIN_TEXT_RULE_VIOLATION")
    if (len(code.encode("utf-8")) >= PY_LIMIT or
            len(code.replace("\n", "\r\n").encode("utf-8")) >= PY_LIMIT):
        raise ValueError("CLOUD_HELPER_EXCEEDS_32K")
    data = json.loads(notebook)
    assert len(data["cells"]) == 1
    assert data["cells"][0]["outputs"] == []
    assert "".join(data["cells"][0]["source"]).strip() == cell.strip()
    if len(notebook) >= 2000 or len(notebook) + OUTPUT_BUDGET * 3 + 2000 >= NB_LIMIT:
        raise ValueError("NOTEBOOK_OUTPUT_HEADROOM_INSUFFICIENT")
    return code, cell, notebook


if __name__ == "__main__":
    code, cell, notebook = build()
    print(f"Plain Cloud helper {len(code)} chars; notebook cell {len(cell)}; "
          f"notebook {len(notebook)}; NO_ORDERS")
