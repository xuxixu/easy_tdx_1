"""港美股榜单（overseas_rank）单元测试：零网络、零真实服务器。"""

from __future__ import annotations

import pandas as pd

from easy_tdx.web import overseas_rank as rank_mod


def _quotes_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _row(code: str, name: str, close: float, pre: float, amount: float = 100.0):
    return {
        "market": 74,
        "code": code,
        "name": name,
        "close": close,
        "pre_close": pre,
        "amount": amount,
        "vol": 10.0,
    }


def test_to_payload_sorts_and_counts():
    """涨跌家数统计 + 三榜排序正确。"""
    df = _quotes_df(
        [
            _row("A", "甲", 11.0, 10.0, 50.0),  # +10%
            _row("B", "乙", 9.0, 10.0, 900.0),  # -10%
            _row("C", "丙", 10.0, 10.0, 100.0),  # 0%
        ]
    )
    payload = rank_mod._to_payload("US", [df])
    assert payload["total"] == 3
    assert payload["up"] == 1
    assert payload["down"] == 1
    assert payload["flat"] == 1
    assert payload["gainers"][0]["code"] == "A"
    assert payload["losers"][0]["code"] == "B"
    assert payload["by_amount"][0]["code"] == "B"
    assert abs(payload["gainers"][0]["change_pct"] - 10.0) < 1e-9


def test_to_payload_excludes_warrants_from_gain_losers():
    """涨跌榜排除权证（名称含"权证"），成交额榜保留，统计总数不变。"""
    df = _quotes_df(
        [
            _row("W", "某某权证", 20.0, 10.0, 10.0),  # +100%，但应被排除
            _row("S", "正股", 11.0, 10.0, 10.0),  # +10%
        ]
    )
    payload = rank_mod._to_payload("US", [df])
    assert payload["total"] == 2  # 统计保留权证
    assert [r["code"] for r in payload["gainers"]] == ["S"]
    assert [r["code"] for r in payload["by_amount"]][0] == "W"  # 成交额榜不过滤


def test_to_payload_empty_frames():
    """空输入返回零值 payload，不抛错。"""
    payload = rank_mod._to_payload("HK", [])
    assert payload["total"] == 0
    assert payload["gainers"] == []
    assert payload["losers"] == []
    assert payload["by_amount"] == []


def test_to_payload_drops_invalid_rows():
    """昨收 ≤0 / 缺失的行不计入（除零保护）。"""
    df = _quotes_df(
        [
            _row("A", "甲", 11.0, 10.0),
            _row("BAD", "坏", 5.0, 0.0),  # pre_close=0
            {"market": 74, "code": "NAN", "name": "空", "close": None, "pre_close": 10.0},
        ]
    )
    payload = rank_mod._to_payload("US", [df])
    assert payload["total"] == 1
    assert payload["gainers"][0]["code"] == "A"


def test_rank_snapshot_rejects_a_share():
    """A 股调榜单直接 ValueError（不进 building）。"""
    try:
        rank_mod.rank_snapshot("SH")
    except ValueError as exc:
        assert "港股/美股" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("SH 应抛 ValueError")
