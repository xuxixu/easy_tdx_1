"""仓库复权隔离回归测试（B1/B2/B3 修复验证）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("duckdb")

from easy_tdx.warehouse.store import KlineWarehouse  # noqa: E402


def _bars(n: int = 10, start: str = "2024-01-01", base: float = 10.0) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    close = base + np.linspace(0, 1, n)
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "vol": 1000.0,
            "amount": close * 1000,
        }
    )


def test_baostock_accepts_adjust_enum(monkeypatch):
    """B1：fetch_bars 接受 Adjust 枚举，不抛 AttributeError。"""
    import importlib

    from easy_tdx.mac.enums import Adjust
    from easy_tdx.sources import baostock as bs_mod

    assert bs_mod._adjust_name(Adjust.QFQ) == "QFQ"
    assert bs_mod._adjust_name(Adjust.NONE) == "NONE"
    assert bs_mod._adjust_name("qfq") == "QFQ"

    class _Rs:
        error_code = "0"

        def next(self):
            return False

    class _FakeBS:
        def login(self):
            return type("R", (), {"error_code": "0"})()

        def query_history_k_data_plus(self, **kwargs):
            assert kwargs.get("adjustflag") in ("1", "2", "3")
            return _Rs()

    monkeypatch.setattr(bs_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(importlib, "import_module", lambda name: _FakeBS())
    # 无行 → 返回 None，但关键是不在 adjust.upper() 处崩溃
    assert bs_mod.fetch_bars("SH", "600000", "DAY", 0, 10, Adjust.QFQ) is None
    assert bs_mod.fetch_bars("SH", "600000", "DAY", 0, 10, "NONE") is None


def test_baostock_client_passes_adjust_enum(monkeypatch):
    """B1：BaostockClient.get_stock_kline 传枚举不崩溃（透传给 fetch_bars）。"""
    from easy_tdx.mac.enums import Adjust
    from easy_tdx.sources import baostock as bs_mod
    from easy_tdx.sources.baostock import BaostockClient

    captured: dict = {}
    monkeypatch.setattr(bs_mod, "is_enabled", lambda: True)

    def _fake_fetch(market, code, category, start, count, adjust, is_index=False):
        captured["adjust"] = adjust
        # 模拟修复后的归一化：枚举也能解析
        assert bs_mod._adjust_name(adjust) in ("NONE", "QFQ", "HFQ")
        return None

    monkeypatch.setattr(bs_mod, "fetch_bars", _fake_fetch)
    out = BaostockClient().get_stock_kline(1, "600000", adjust=Adjust.HFQ)
    assert out is not None and len(out) == 0
    assert bs_mod._adjust_name(captured["adjust"]) == "HFQ"


def test_health_check_isolated_by_adjust(tmp_path):
    """B2：QFQ/NONE 混存时健康检查按口径分别计算，不误报跨口径跳空。"""
    wh = KlineWarehouse(tmp_path / "mix.duckdb")
    try:
        wh.upsert_bars("SH", "600519", _bars(20), adjust="QFQ")
        # 同一标的另一口径：整体平移（模拟未复权价差），各自序列平滑
        wh.upsert_bars("SH", "600519", _bars(20, base=7.0), adjust="NONE")
        report = wh.health_check()
        assert report["symbols_checked"] == 2
        assert [i for i in report["issues"] if i["kind"] == "price_jump"] == []
        # 口径过滤
        qfq_only = wh.health_check(adjust="QFQ")
        assert qfq_only["symbols_checked"] == 1
        assert all(i.get("adjust") == "QFQ" for i in qfq_only["issues"])
    finally:
        wh.close()


def test_migrate_legacy_table_atomic(tmp_path):
    """B3：无 adjust 列的老库迁移行数一致、无残留、可重开。"""
    import duckdb

    path = tmp_path / "legacy.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(
        """
        CREATE TABLE klines (
            market TEXT NOT NULL, code TEXT NOT NULL, period TEXT NOT NULL,
            datetime TIMESTAMP NOT NULL, open DOUBLE, high DOUBLE, low DOUBLE,
            close DOUBLE, vol DOUBLE, amount DOUBLE,
            status TEXT NOT NULL DEFAULT 'completed', updated_at TIMESTAMP,
            PRIMARY KEY (market, code, period, datetime)
        )
        """
    )
    conn.execute(
        "INSERT INTO klines VALUES "
        "('SH','600519','DAILY','2024-01-02 00:00:00',10,10.1,9.9,10,1000,10000,"
        "'completed',NULL)"
    )
    conn.close()

    wh = KlineWarehouse(path)
    try:
        out = wh.query("SH", "600519", adjust="QFQ")
        assert len(out) == 1
        assert out["adjust"].iloc[0] == "QFQ"
        # 无残留表
        legacy = wh._conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='klines_legacy'"
        ).fetchone()[0]
        assert int(legacy) == 0
    finally:
        wh.close()

    # 可重开（幂等）
    wh2 = KlineWarehouse(path)
    try:
        assert len(wh2.query("SH", "600519", adjust="QFQ")) == 1
    finally:
        wh2.close()
