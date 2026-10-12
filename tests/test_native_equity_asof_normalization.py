"""As-of US equity normalization regression (source contract only).

LEAN Cloud must still verify native RAW D1/M5 parity and the specific
NVDA split-era pivot. These tests never authorize trading.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_native_minute_and_second_subscriptions_use_same_raw_basis():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "self._equity_normalization_mode = DataNormalizationMode.RAW" in source
    assert "data_normalization_mode=self._equity_normalization_mode" in source
    assert "self._tvx_normalization_mode" not in source
    assert "self.universe_settings.data_normalization_mode = (" in source
    assert "self._equity_normalization_mode)" in source
    assert not re.search(
        r"data_normalization_mode\s*=\s*DataNormalizationMode\.SPLIT_ADJUSTED",
        source)


def test_native_daily_history_warms_with_official_asof_scaled_raw():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "self.history[TradeBar](" in source
    assert "symbols, 180, Resolution.DAILY," in source
    assert "data_normalization_mode=DataNormalizationMode.SCALED_RAW" in source
    # No separate minute path allowed: both data resolutions warm in the
    # same at-time adjusted historical basis.
    assert "if self._tvx_seconds_enabled\n                        else DataNormalizationMode.SPLIT_ADJUSTED" not in source


def test_conservative_bsu_guard_and_broker_kill_switch_unchanged():
    bridge = (ROOT / "strategy/bsu_bridge.py").read_text(encoding="utf-8")
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "BSU historical origin off native tick grid; normalization unsafe" in bridge
    assert "create_bsu_research_observer(" in source
    assert "self._native_exit_enabled = False" in source


def test_cloud_package_carries_asof_mode_without_hidden_extra_files():
    from tools.package_quantconnect_free import build_sources
    package = build_sources(ROOT)
    assert len(package) == 24
    assert "self._equity_normalization_mode = DataNormalizationMode.RAW" in package["main.py"]
    assert "data_normalization_mode=DataNormalizationMode.SCALED_RAW" in package["main.py"]
    assert "strategy/bsu_bridge.py" in package
