"""Build Qwct's 24-Python-file package, reserving the 25th Free-tier slot for research.ipynb.

Never hand-edit a second copy of the strategy. Merge small pure modules
only in this packaging step, preserving the canonical GitHub Python files
and their normal tests. The ZIP contains exactly 24 Python files; keep the Cloud research.ipynb as file 25.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

# These two stand-alone comparators are not imported by the Qwct LEAN
# algorithm. Neither is an execution/risk substitute.
OPTIONAL_RESEARCH = {
    "strategy/opening_volume_research.py",
    "strategy/tvx_observation.py",
}
# Bundled into existing sources; no corresponding .py files in Cloud ZIP.
BUNDLED = {
    "strategy/focus.py",
    "strategy/screener.py",
    "strategy/native_m5_validation.py",
    "strategy/runtime_reporting.py",
}
CLOUD_FILE_LIMIT = 24  # 24 .py + existing research.ipynb = Free quota of 25


def _functions(source: str, names: tuple[str, ...], origin: str) -> str:
    tree = ast.parse(source, filename=origin)
    by_name = {node.name: node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = set(names).difference(by_name)
    if missing:
        raise ValueError(f"{origin} missing expected functions: {sorted(missing)}")
    # Full source segments preserve current code, docstrings and annotations.
    return "\n\n\n".join(
        ast.get_source_segment(source, by_name[name]) for name in names)


def _replace_once(source: str, old: str, new: str, path: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"{path} expected exactly one occurrence of {old!r}")
    return source.replace(old, new, 1)


def _verify_local_imports(package: dict[str, str]) -> None:
    """Never silently upload a Cloud package with a broken relative import."""
    for path, source in package.items():
        tree = ast.parse(source, filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level and path.startswith("strategy/"):
                    if node.level != 1:
                        raise ValueError(f"unsupported nested import: {path}")
                    if node.module:
                        dep = f"strategy/{node.module.split('.')[0]}.py"
                        if dep not in package:
                            raise ValueError(f"{path}: missing relative dependency {dep}")
                elif node.module and node.module.startswith("strategy."):
                    dep = "strategy/" + node.module.split(".")[1] + ".py"
                    if dep not in package:
                        raise ValueError(f"{path}: missing absolute dependency {dep}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("strategy."):
                        dep = "strategy/" + alias.name.split(".")[1] + ".py"
                        if dep not in package:
                            raise ValueError(f"{path}: missing import dependency {dep}")


def build_sources(repo: Path) -> dict[str, str]:
    """Return complete upload tree, assembled from canonical modules."""
    if not (repo / "main.py").is_file():
        raise FileNotFoundError(f"main.py missing in {repo}")
    sources = {"main.py": (repo / "main.py").read_text(encoding="utf-8")}
    sources.update({
        f"strategy/{file.name}": file.read_text(encoding="utf-8")
        for file in sorted((repo / "strategy").glob("*.py"))
    })
    required = {
        "strategy/__init__.py",
        "strategy/focus.py",
        "strategy/screener.py",
        "strategy/native_m5_validation.py",
        "strategy/native_second_tvx.py",
        "strategy/m5_runtime.py",
        "strategy/second_runtime.py",
        "strategy/risk_research.py",
        "strategy/preclose_review.py",
    }
    if required.difference(sources):
        raise ValueError(f"missing upstream modules: {sorted(required.difference(sources))}")

    # 1 + 2: focus and screener pure helpers live in the already
    # mandatory package __init__.py. Preserve *current* screener
    # signature (including max_results), not obsolete pasted snippets.
    screener = _functions(
        sources["strategy/screener.py"],
        ("_positive", "select_liquid_fundamentals", "passes_gerchik_screener"),
        "strategy/screener.py")
    focus = _functions(
        sources["strategy/focus.py"], ("choose_focus",), "strategy/focus.py")
    sources["strategy/__init__.py"] = (
        sources["strategy/__init__.py"].rstrip()
        + "\n\n# QuantConnect Free package: canonical pure screener/focus helpers.\n"
        + "from math import isfinite\n"
        + "from .config import StrategyConfig\n\n\n"
        + screener + "\n\n\n" + focus + "\n")
    main = sources["main.py"]
    main = _replace_once(
        main, "from strategy.focus import choose_focus",
        "from strategy import choose_focus", "main.py")
    main = _replace_once(
        main,
        "from strategy.screener import select_liquid_fundamentals, passes_gerchik_screener",
        "from strategy import select_liquid_fundamentals, passes_gerchik_screener",
        "main.py")
    sources["main.py"] = main

    # 3: keep LEAN SEC sample and native M5 time/volume shape checks
    # in one file. SEC and M5 use the *same* _duration_seconds code.
    funcs = _functions(
        sources["strategy/native_m5_validation.py"],
        ("_duration_seconds", "validate_m5_tradebar"),
        "strategy/native_m5_validation.py")
    sources["strategy/native_second_tvx.py"] = _replace_once(
        sources["strategy/native_second_tvx.py"],
        "from .native_m5_validation import _duration_seconds",
        "# Native M5+SEC validation share real LEAN bar duration logic.\n"
        + funcs,
        "strategy/native_second_tvx.py")
    sources["strategy/m5_runtime.py"] = _replace_once(
        sources["strategy/m5_runtime.py"],
        "from .native_m5_validation import validate_m5_tradebar",
        "from .native_second_tvx import validate_m5_tradebar",
        "strategy/m5_runtime.py")
    sources["strategy/second_runtime.py"] = _replace_once(
        sources["strategy/second_runtime.py"],
        "from .native_m5_validation import _duration_seconds",
        "from .native_second_tvx import _duration_seconds",
        "strategy/second_runtime.py")

    # 4: keep the existing Cloud research.ipynb by bundling runtime
    # reporting into the small reporting.py module (far below 32 KB).
    # Preserve the exact canonical write_reports function body.
    sources["strategy/reporting.py"] = (
        sources["strategy/reporting.py"].rstrip()
        + "\n\n# Cloud Free: include canonical end-of-backtest reporting.\n"
        + "from collections import Counter\n\n"
        + _functions(sources["strategy/runtime_reporting.py"],
                     ("write_reports",), "strategy/runtime_reporting.py")
        + "\n")
    sources["main.py"] = _replace_once(
        sources["main.py"],
        "from strategy.runtime_reporting import write_reports",
        "from strategy.reporting import write_reports", "main.py")

    for path in OPTIONAL_RESEARCH | BUNDLED:
        del sources[path]

    if len(sources) != CLOUD_FILE_LIMIT:
        raise ValueError(
            f"QuantConnect Free bundle must have exactly {CLOUD_FILE_LIMIT} files; "
            f"found {len(sources)}: {sorted(sources)}")
    if len(sources["main.py"]) >= 28_000:
        raise ValueError("main.py exceeds Qwct's Cloud edit headroom")
    _verify_local_imports(sources)
    for path, source in sources.items():
        compile(source, path, "exec")
    return dict(sorted(sources.items()))


def package_zip(sources: dict[str, str], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path, content in sorted(sources.items()):
            archive.writestr(path, content)
    print(f"Built {output}: {len(sources)} Python files, no missing local imports")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path("dist/Qwct-QuantConnect-Free-24py.zip"))
    args = parser.parse_args()
    package_zip(build_sources(Path(__file__).resolve().parents[1]), args.output)


if __name__ == "__main__":
    main()
