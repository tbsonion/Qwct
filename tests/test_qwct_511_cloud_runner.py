"""Checks for QWCT 5.13 readable research runner (no Cloud data proof)."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "_q513builder", ROOT / "tools/build_qwct_pipeline_runner.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def runner():
    spec = importlib.util.spec_from_file_location("_q513runner", builder.RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_plain_helper_and_import_only_notebook_fit_both_cloud_limits():
    code, cell, notebook = builder.build()
    assert len(code) > len(cell) * 10
    assert len(code.encode()) < 32000
    assert len(code.replace("\n", "\r\n").encode()) < 32000
    assert len(notebook) < 1000
    assert len(notebook) + 16000 * 3 + 2000 < 64000
    payload = json.loads(notebook)
    assert len(payload["cells"]) == 1
    assert payload["cells"][0]["outputs"] == []
    assert "qwct_pipeline_runner.run()" in cell


def test_import_is_quiet_and_no_native_history_executes_on_import(capsys):
    r = runner()
    assert r.SYMBOLS == ("AMAT", "NFLX", "SRPT", "MSFT")
    assert capsys.readouterr().out == ""
    assert callable(r.run)


def test_complete_rejection_reasons_retained_when_short():
    r = runner()
    evidence = ["bounce@120.01: score 2 < 4", "нет уровней рядом"]
    assert r.summarize_rejections(evidence) == {
        "total": 2, "reasons": evidence, "omitted": 0,
    }


def test_bounded_rejection_output_discloses_omissions():
    r = runner()
    evidence = [f"level-{i}" for i in range(20)]
    result = r.summarize_rejections(evidence, limit=3)
    assert result["total"] == 20
    assert result["reasons"] == evidence[:3]
    assert result["omitted"] == 17
    with pytest.raises(ValueError, match="REJECTION_LIMIT_INVALID"):
        r.summarize_rejections(evidence, limit=0)


def test_missing_cloud_module_is_explicit_loader_error(monkeypatch, capsys):
    r = runner()
    def fail(name):
        raise ModuleNotFoundError("test missing " + name)
    monkeypatch.setattr(r, "import_module", fail)
    output = r.run()
    printed = capsys.readouterr().out
    assert output == {"status": "LOADER_ERROR", "can_trade": False}
    assert "LOADER_ERROR" in printed
    assert "QWCT 5.13 END" not in printed
    assert "can_trade" in printed and "false" in printed


def test_critical_scope_remains_d1_research_only():
    source = builder.RUNNER.read_text(encoding="utf-8")
    assert "_load_daily" in source and "Decision" not in source
    assert "D1_LEVEL" in source and "rejection_details" in source
    assert "score_provenance" in source and "bsu_eligibility_checks" in source
    assert 'm5="NOT_RUN"' in source
    assert 'gates_8="NOT_EVALUATED"' in source
    assert 'orders="DISABLED"' in source
    assert "qb.history[ai.TradeBar]" in source
    assert "data_normalization_mode=ai.DataNormalizationMode.RAW" in source
    assert "QuantBook()" in source


def test_bsu_eligibility_explains_mirror_exclusion():
    r = runner()
    class Level:
        kind = "mirror"
        source = "swing_cluster"
        valid_from = __import__("datetime").date(2024, 1, 1)
        formed_at = __import__("datetime").date(2023, 1, 1)
        touches = 3
        strength = 3.0
    class Cfg:
        min_touches = 2
        min_level_strength = 2.0
    ok, checks = r._bsu_eligibility(Level(), __import__("datetime").date(2024, 6, 3), Cfg())
    assert ok is False
    assert checks["kind_support_or_resistance"] is False
    assert all(v is True for k, v in checks.items() if k != "kind_support_or_resistance")


def test_explicit_no_orders_and_unknown_author_proof(capsys):
    r = runner()
    r._emit("CHECK", author_verified=False, can_trade=False)
    result = capsys.readouterr().out
    assert '"author_verified": false' in result
    assert '"can_trade": false' in result
