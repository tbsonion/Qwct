"""The deployable Cloud-Free package must match main's tested pure rules."""
import ast
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

from tools.package_quantconnect_free import (
    BUNDLED, CLOUD_FILE_LIMIT, OPTIONAL_RESEARCH, build_sources, package_zip,
)

ROOT = Path(__file__).resolve().parents[1]


def _function_ast(source, name):
    tree = ast.parse(source)
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.dump(function, include_attributes=False)


def test_cloud_free_reserves_research_notebook_as_file_25():
    files = build_sources(ROOT)
    assert len(files) == CLOUD_FILE_LIMIT == 24  # research.ipynb is #25
    assert "main.py" in files
    assert "strategy/__init__.py" in files
    assert "strategy/native_second_tvx.py" in files
    assert "strategy/preclose_review.py" in files
    assert "strategy/risk_research.py" in files
    assert "strategy/corporate_action_guard.py" in files
    assert not (BUNDLED | OPTIONAL_RESEARCH) & set(files)
    assert all(path.endswith(".py") for path in files)
    assert "from strategy import choose_focus" in files["main.py"]
    assert "from strategy import select_liquid_fundamentals" in files["main.py"]
    assert "from .native_second_tvx import validate_m5_tradebar" in (
        files["strategy/m5_runtime.py"])
    assert "from .native_second_tvx import _duration_seconds" in (
        files["strategy/second_runtime.py"])
    assert "from .native_m5_validation import" not in "\n".join(files.values())
    assert "from strategy.reporting import write_reports" in files["main.py"]
    assert "strategy/runtime_reporting.py" not in files
    assert len(files["strategy/reporting.py"].encode("utf-8")) < 32_000
    assert len(files["main.py"].encode("utf-8")) < 32_000
    assert "_native_exit_enabled = False" in files["main.py"]


def test_cloud_free_uses_exact_main_source_function_bodies():
    files = build_sources(ROOT)
    for source_path, dest, funcs in (
        ("strategy/focus.py", "strategy/__init__.py", ("choose_focus",)),
        ("strategy/screener.py", "strategy/__init__.py",
         ("_positive", "select_liquid_fundamentals",
          "passes_gerchik_screener")),
        ("strategy/native_m5_validation.py", "strategy/native_second_tvx.py",
         ("_duration_seconds", "validate_m5_tradebar")),
        ("strategy/runtime_reporting.py", "strategy/reporting.py",
         ("write_reports",)),
    ):
        canonical = (ROOT/source_path).read_text(encoding="utf-8")
        bundled = files[dest]
        for name in funcs:
            assert _function_ast(canonical, name) == _function_ast(bundled, name)


def test_cloud_free_zip_has_no_extra_notebooks_tests_or_external_files(tmp_path):
    sources = build_sources(ROOT)
    output = tmp_path/"Qwct-QuantConnect-Free-24py.zip"
    package_zip(sources, output)
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == set(sources)
        for item in archive.namelist():
            assert archive.read(item).decode("utf-8") == sources[item]


def test_cloud_free_extracted_package_imports_real_rule_helpers(tmp_path):
    # Run in a separate interpreter to avoid accidentally importing the
    # canonical strategy from the normal repository test PYTHONPATH.
    sources = build_sources(ROOT)
    for relative, content in sources.items():
        dest = tmp_path/relative
        dest.parent.mkdir(exist_ok=True, parents=True)
        dest.write_text(content, encoding="utf-8")
    smoke = """
from datetime import datetime, timedelta
from types import SimpleNamespace
from collections import namedtuple
from zoneinfo import ZoneInfo
from strategy import choose_focus, select_liquid_fundamentals, passes_gerchik_screener
from strategy.config import StrategyConfig
from strategy.native_second_tvx import _duration_seconds, validate_m5_tradebar
from strategy.second_runtime import process_second_slice
from strategy.m5_runtime import process_m5
from strategy.reporting import write_reports
cfg = StrategyConfig()
Symbol = namedtuple("Symbol", "value")
a = SimpleNamespace(symbol=Symbol("AAA"),
                    price=50., volume=10., dollar_volume=500.,
                    has_fundamental_data=True)
assert select_liquid_fundamentals([a], cfg) == [a.symbol]
assert passes_gerchik_screener(50., 2., 900000., cfg)
decision = SimpleNamespace(accepted=True, symbol="AAA", model="bounce")
assert choose_focus([a.symbol], {a.symbol: decision}) == a.symbol
t = datetime(2024, 1, 3, 12, 0, tzinfo=ZoneInfo("America/New_York"))
b = SimpleNamespace(time=t, end_time=t+timedelta(minutes=5),
                    period=timedelta(minutes=5), open=100., high=101.,
                    low=99., close=100., volume=500.,
                    is_fill_forward=False)
assert _duration_seconds(b.period) == 300.
assert validate_m5_tradebar(b, b.end_time)[0] is True
assert callable(process_second_slice) and callable(process_m5) and callable(write_reports)
"""
    result = subprocess.run(
        [sys.executable, "-c", smoke], cwd=tmp_path,
        text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
