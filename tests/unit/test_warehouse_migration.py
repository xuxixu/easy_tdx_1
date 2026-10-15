"""仓库迁移分块+续拷与 symbols 兼容形状测试（handoff 遗留②验证）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("duckdb")

from easy_tdx.warehouse.store import KlineWarehouse  # noqa: E402


def _bars(n: int = 5, start: str = "2024-01-01", base: float = 10.0) -> pd.DataFrame:
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


def _make_legacy_db(path, symbols: list[tuple[str, str]], n: int = 5) -> int:
    """手工构造无 adjust 列的老库，返回总行数。"""
    import duckdb

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
    total = 0
    for mkt, code in symbols:
        df = _bars(n)
        for _, r in df.iterrows():
            conn.execute(
                "INSERT INTO klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    mkt,
                    code,
                    "DAILY",
                    r["datetime"].to_pydatetime(),
                    r["open"],
                    r["high"],
                    r["low"],
                    r["close"],
                    r["vol"],
                    r["amount"],
                    "completed",
                    None,
                ],
            )
            total += 1
    conn.close()
    return total


def test_chunked_migration_multi_symbol(tmp_path, monkeypatch):
    """多标的老库经分块迁移：行数一致、无残留、可重开。"""
    import easy_tdx.warehouse.store as store_mod

    monkeypatch.setattr(store_mod.KlineWarehouse, "_MIGRATE_CHUNK_SYMBOLS", 2)
    symbols = [("SH", "600519"), ("SZ", "000001"), ("SH", "600036"), ("BJ", "430047")]
    total = _make_legacy_db(tmp_path / "chunk.duckdb", symbols, n=5)

    wh = KlineWarehouse(tmp_path / "chunk.duckdb")
    try:
        assert len(wh.query("SH", "600519", adjust="QFQ")) == 5
        assert len(wh.query("BJ", "430047", adjust="QFQ")) == 5
        n = wh._conn.execute("SELECT count(*) FROM klines").fetchone()[0]
        assert int(n) == total
        legacy = wh._conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='klines_legacy'"
        ).fetchone()[0]
        assert int(legacy) == 0
    finally:
        wh.close()

    wh2 = KlineWarehouse(tmp_path / "chunk.duckdb")
    try:
        assert len(wh2.query("SZ", "000001", adjust="QFQ")) == 5
    finally:
        wh2.close()


def test_migration_resume_after_crash(tmp_path):
    """模拟崩溃（新表半截 + legacy 保留）：重开自动续拷并清理。"""
    import duckdb

    path = tmp_path / "resume.duckdb"
    total = _make_legacy_db(path, [("SH", "600519"), ("SZ", "000001")], n=5)
    assert total == 10

    conn = duckdb.connect(str(path))
    # 新表只拷了 SH 一半（5 行中的 3 行），legacy 保留 10 行
    conn.execute(
        """
        CREATE TABLE klines_new AS
        SELECT market, code, period, datetime, open, high, low, close,
               vol, amount, 'QFQ' AS adjust, status, updated_at
        FROM (
            SELECT * FROM klines WHERE code = '600519' LIMIT 3
        )
        """
    )
    conn.execute("ALTER TABLE klines RENAME TO klines_legacy")
    conn.execute("ALTER TABLE klines_new RENAME TO klines")
    # 注意：手工 klines 无主键约束也无妨，迁移逻辑只依赖列存在性
    conn.close()

    # 注意：手工 klines 无主键约束，迁移逻辑只依赖列存在性
    wh = KlineWarehouse(path)
    try:
        assert len(wh.query("SH", "600519", adjust="QFQ")) == 5
        assert len(wh.query("SZ", "000001", adjust="QFQ")) == 5
        legacy = wh._conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='klines_legacy'"
        ).fetchone()[0]
        assert int(legacy) == 0
    finally:
        wh.close()


def test_symbols_per_adjust_flag(tmp_path):
    """symbols() 默认按口径分组；per_adjust=False 回到历史形状。"""
    wh = KlineWarehouse(tmp_path / "sym.duckdb")
    try:
        wh.upsert_bars("SH", "600519", _bars(5), adjust="QFQ")
        wh.upsert_bars("SH", "600519", _bars(5), adjust="NONE")
        full = wh.symbols()
        assert len(full) == 2
        assert set(full["adjust"]) == {"QFQ", "NONE"}
        legacy = wh.symbols(per_adjust=False)
        assert len(legacy) == 1
        assert "adjust" not in legacy.columns
        assert set(legacy["code"]) == {"600519"}
    finally:
        wh.close()
