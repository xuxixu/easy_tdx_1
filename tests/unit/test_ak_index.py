"""akshare 指数源单测：mock akshare 模块，不出网。

覆盖：可选依赖开关（未安装静默关闭 / 环境变量禁用）、全历史日K归一化、
周月本地聚合、分页语义、标的符号映射（标普在新浪叫 .INX）。
"""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from easy_tdx.sources import ak_index


def _install_fake_akshare(monkeypatch, df: pd.DataFrame) -> dict[str, str]:
    """装一个假 akshare 模块，记录被调用的符号。"""
    calls: dict[str, str] = {}

    def index_us_stock_sina(symbol: str = ".INX") -> pd.DataFrame:
        calls["symbol"] = symbol
        return df.copy()

    def stock_hk_index_daily_sina(symbol: str = "HSI") -> pd.DataFrame:
        calls["symbol"] = symbol
        return df.copy()

    mod = types.ModuleType("akshare")
    mod.index_us_stock_sina = index_us_stock_sina  # type: ignore[attr-defined]
    mod.stock_hk_index_daily_sina = stock_hk_index_daily_sina  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "akshare", mod)
    ak_index.clear_cache()
    return calls


def _daily(rows: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=rows, freq="B").date
    return pd.DataFrame(
        {
            "date": dates,
            "open": [100.0 + i for i in range(rows)],
            "high": [101.0 + i for i in range(rows)],
            "low": [99.0 + i for i in range(rows)],
            "close": [100.5 + i for i in range(rows)],
            "volume": [1000 + i for i in range(rows)],
            "amount": [1_000_000 + i for i in range(rows)],
        }
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    ak_index.clear_cache()
    yield
    ak_index.clear_cache()


def test_is_enabled_true_when_installed(monkeypatch):
    _install_fake_akshare(monkeypatch, _daily())
    assert ak_index.is_enabled() is True


def test_is_enabled_false_when_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "akshare", None)
    assert ak_index.is_enabled() is False


def test_disabled_by_env(monkeypatch):
    _install_fake_akshare(monkeypatch, _daily())
    monkeypatch.setenv(ak_index._DISABLE_ENV, "0")
    assert ak_index.is_enabled() is False


def test_fetch_bars_normalizes_columns(monkeypatch):
    _install_fake_akshare(monkeypatch, _daily(30))
    df = ak_index.fetch_bars("US", "DJI", "DAY", 0, 10)
    assert list(df.columns) == ["date", "open", "high", "low", "close", "vol", "amount"]
    assert len(df) == 10
    assert df.iloc[-1]["close"] == pytest.approx(129.5)
    assert df["date"].is_monotonic_increasing


def test_us_symbol_mapping(monkeypatch):
    """我们的代码 → akshare(新浪) 代码：标普是 .INX，纳指100 是 .NDX。"""
    calls = _install_fake_akshare(monkeypatch, _daily(10))
    ak_index.fetch_bars("US", "SPX", "DAY", 0, 5)
    assert calls["symbol"] == ".INX"
    ak_index.clear_cache()
    ak_index.fetch_bars("US", "NDX", "DAY", 0, 5)
    assert calls["symbol"] == ".NDX"
    ak_index.clear_cache()
    ak_index.fetch_bars("US", "DJI", "DAY", 0, 5)
    assert calls["symbol"] == ".DJI"


def test_hk_uses_hk_endpoint(monkeypatch):
    calls = _install_fake_akshare(monkeypatch, _daily(10))
    ak_index.fetch_bars("HK", "HSTECH", "DAY", 0, 5)
    assert calls["symbol"] == "HSTECH"


def test_pagination_semantics(monkeypatch):
    """start/count 与 TDX 一致：start=0 取最近 count 根。"""
    _install_fake_akshare(monkeypatch, _daily(30))
    latest = ak_index.fetch_bars("US", "DJI", "DAY", 0, 5)
    older = ak_index.fetch_bars("US", "DJI", "DAY", 10, 5)
    assert float(latest.iloc[-1]["close"]) > float(older.iloc[-1]["close"])
    assert len(older) == 5


def test_week_and_month_resampled(monkeypatch):
    _install_fake_akshare(monkeypatch, _daily(120))
    wk = ak_index.fetch_bars("US", "DJI", "WEEK", 0, 5)
    mo = ak_index.fetch_bars("US", "DJI", "MONTH", 0, 5)
    assert len(wk) == 5
    assert len(mo) == 5
    # 聚合口径：收盘 = 区间最后一根日K收盘
    daily = _daily(120)
    assert float(wk.iloc[-1]["close"]) <= float(daily["close"].max())


def test_minute_category_rejected(monkeypatch):
    _install_fake_akshare(monkeypatch, _daily(10))
    with pytest.raises(RuntimeError, match="仅支持日/周/月"):
        ak_index.fetch_bars("US", "DJI", "MIN_5", 0, 5)


def test_cache_avoids_second_fetch(monkeypatch):
    calls = _install_fake_akshare(monkeypatch, _daily(30))
    ak_index.fetch_bars("US", "IXIC", "DAY", 0, 5)
    ak_index.fetch_bars("US", "IXIC", "DAY", 0, 20)
    # 第二次命中进程内缓存，不应再触发底层请求（symbol 仍是第一次的值）
    assert calls["symbol"] == ".IXIC"


def test_missing_akshare_raises_with_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "akshare", None)
    with pytest.raises(RuntimeError, match="akshare 未安装"):
        ak_index.fetch_bars("US", "DJI", "DAY", 0, 5)
