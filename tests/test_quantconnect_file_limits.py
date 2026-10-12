from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 32000

def test_python_file_size_limit():
    files = [ROOT / "main.py", *(ROOT / "strategy").glob("*.py")]
    for path in files:
        count = len(path.read_text(encoding="utf-8"))
        assert count <= LIMIT, f"{path.name}={count} exceeds {LIMIT}"

def test_entrypoint_headroom():
    code = (ROOT / "main.py").read_text(encoding="utf-8")
    assert len(code) < 28000
    assert "self._native_exit_enabled = False" in code
    assert "def _on_m5(self, bar: TradeBar) -> None:" in code
    assert "def _write_reports(self) -> None:" in code
