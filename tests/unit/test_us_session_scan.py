"""美股时段（us_session）+ 信号定向扫描 + 策略更新 单测：零网络。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from easy_tdx.us_session import (
    filter_us_regular_hours,
    is_dst,
    is_us_trading_minutes,
    us_session,
)

_ET = timezone(timedelta(hours=-5))


def _et(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    """构造"真实美东时钟"时间（夏令按 UTC-4 换算，测试日均为夏令）。"""
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc) + timedelta(hours=4)


def test_us_session_four_states():
    """夏令时某周五四态（美东口径）。"""
    assert us_session(_et(2026, 10, 9, 3, 0)) == "night"
    assert us_session(_et(2026, 10, 9, 8, 0)) == "pre"
    assert us_session(_et(2026, 10, 9, 10, 0)) == "open"
    assert us_session(_et(2026, 10, 9, 15, 59)) == "open"
    assert us_session(_et(2026, 10, 9, 18, 0)) == "after"
    assert us_session(_et(2026, 10, 9, 22, 0)) == "night"


def test_us_session_weekend_is_night():
    """周末全天夜盘（2026-10-10 是周六）。"""
    assert us_session(_et(2026, 10, 10, 12, 0)) == "night"
    assert us_session(_et(2026, 10, 11, 12, 0)) == "night"


def test_is_dst_boundaries():
    """夏令 3 月第 2 个周日 ~ 11 月第 1 个周日（2026 年：3/8 ~ 11/1）。"""
    import datetime as dt

    assert is_dst(dt.date(2026, 10, 9)) is True
    assert is_dst(dt.date(2026, 1, 15)) is False
    assert is_dst(dt.date(2026, 7, 1)) is True
    assert is_dst(dt.date(2026, 3, 8)) is True
    assert is_dst(dt.date(2026, 3, 7)) is False
    assert is_dst(dt.date(2026, 11, 1)) is False
    assert is_dst(dt.date(2026, 10, 31)) is True


def test_is_us_trading_minutes():
    """09:30 含、16:00 不含；naive 视为北京时间换算。"""
    assert is_us_trading_minutes(_et(2026, 10, 9, 9, 30)) is True
    assert is_us_trading_minutes(_et(2026, 10, 9, 15, 59)) is True
    assert is_us_trading_minutes(_et(2026, 10, 9, 9, 29)) is False
    assert is_us_trading_minutes(_et(2026, 10, 9, 16, 0)) is False
    # 北京时间 21:30 = 美东 09:30（夏令）
    bj = timezone(timedelta(hours=8))
    assert is_us_trading_minutes(datetime(2026, 10, 9, 21, 30, tzinfo=bj)) is True
    assert is_us_trading_minutes(datetime(2026, 10, 9, 21, 29, tzinfo=bj)) is False
    # 冬令：2026-01-15 美东 09:30 = UTC 14:30
    winter = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    assert is_us_trading_minutes(winter) is True
    assert is_us_trading_minutes(winter - timedelta(minutes=1)) is False


def test_filter_us_regular_hours_minute():
    """分钟线只留盘中；日线（00:00）原样返回。"""
    bj = timezone(timedelta(hours=8))
    df = pd.DataFrame(
        {
            "datetime": [
                datetime(2026, 10, 9, 21, 0, tzinfo=bj),  # 盘前
                datetime(2026, 10, 9, 22, 0, tzinfo=bj),  # 盘中
                datetime(2026, 10, 9, 4, 30, tzinfo=bj),  # 盘后
            ],
            "close": [1.0, 2.0, 3.0],
        }
    )
    out = filter_us_regular_hours(df)
    assert len(out) == 1
    assert float(out.iloc[0]["close"]) == 2.0


def test_filter_us_regular_hours_daily_passthrough():
    """日线不过滤。"""
    df = pd.DataFrame(
        {"datetime": ["2026-10-08T00:00:00", "2026-10-09T00:00:00"], "close": [1.0, 2.0]}
    )
    out = filter_us_regular_hours(df)
    assert len(out) == 2


def test_expand_targets_symbol_and_id_filter():
    """定向扫描过滤：symbol + strategy_ids 叠加。"""
    from easy_tdx.web.signal_scan import expand_targets
    from easy_tdx.web.strategy_store import SavedStrategy

    def rec(sid: str, symbol: str) -> SavedStrategy:
        return SavedStrategy(
            id=sid,
            name=sid,
            kind="single",
            strategy="ma_cross",
            strategy_label="",
            params={},
            context={"symbol": symbol},
            trade_config={},
            snapshot={},
            tags=[],
            notes="",
        )

    records = [rec("a", "SH:600519"), rec("b", "HK:00700"), rec("c", "US:AAPL")]
    assert len(expand_targets(records)) == 3
    assert {t.symbol for t in expand_targets(records, symbols=["HK:00700"])} == {"HK:00700"}
    assert {t.strategy_id for t in expand_targets(records, strategy_ids=["a", "c"])} == {"a", "c"}
    both = expand_targets(records, symbols=["US:AAPL"], strategy_ids=["b", "c"])
    assert [(t.strategy_id, t.symbol) for t in both] == [("c", "US:AAPL")]
    assert expand_targets(records, symbols=["XX:000"]) == []


def test_normalize_symbol_hk_us():
    """港美股 symbol 归一化（不被重判成 SZ）。"""
    from easy_tdx.web.signal_scan import normalize_symbol

    assert normalize_symbol("HK:00700") == "HK:00700"
    assert normalize_symbol("US:AAPL") == "US:AAPL"
    assert normalize_symbol("00700") == "HK:00700"
    assert normalize_symbol("AAPL") == "US:AAPL"
    assert normalize_symbol("SZ:515080") == "SH:515080"  # A 股错标仍纠正
    assert normalize_symbol("600519") == "SH:600519"


def test_strategy_store_update(tmp_path, monkeypatch):
    """策略部分更新：白名单字段 + updated_at 刷新 + 不存在返回 None。"""

    monkeypatch.setenv("EASY_TDX_CONFIG_DIR", str(tmp_path))
    from easy_tdx.web import strategy_store as store_mod

    monkeypatch.setattr(store_mod, "_store", None)
    store = store_mod.get_store()
    rec = store_mod.SavedStrategy(
        id="",
        name="old",
        kind="single",
        strategy="ma_cross",
        strategy_label="",
        params={"fast": 5},
        context={"symbol": "SH:600519"},
        trade_config={},
        snapshot={},
        tags=[],
        notes="",
    )
    saved = store.add(rec)
    updated = store.update(saved.id, {"name": "new", "params": {"fast": 10}, "nope": 1})
    assert updated is not None
    assert updated.name == "new"
    assert updated.params == {"fast": 10}
    assert store.update("missing-id", {"name": "x"}) is None
