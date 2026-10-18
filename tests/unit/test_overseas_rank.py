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


# ── 翻页上限（防无限循环 / 内存无界增长）──────────────────────────────────────


class _EndlessClient:
    """坏服务端：忽略 start 参数、每页都返回满页，且总数查询失败。"""

    def __init__(self) -> None:
        self.calls = 0

    def goods_count(self, market: int) -> int:
        return 0

    def goods_quotes_list(self, market: int, start: int = 0, count: int = 80):
        self.calls += 1
        return _quotes_df([_row(f"C{self.calls}_{i}", f"股{i}", 10.0, 10.0) for i in range(count)])


def test_build_with_client_stops_at_page_cap(monkeypatch):
    """服务端总是返回满页时，必须靠翻页上限退出。

    回归：旧实现只有「返回空」「不满一页」两个出口，服务端忽略 start 参数时
    循环永不退出、frames 持续增长 —— 后台线程卡死 + 内存无界增长。
    """
    monkeypatch.setattr(rank_mod, "_MAX_PAGES_PER_MARKET", 3)
    client = _EndlessClient()

    rank_mod._build_with_client("US", client)

    assert client.calls == 3, "达到上限后必须停止翻页"


def test_build_with_client_stops_on_short_page():
    """最后不满一页时正常退出（不得因上限而多翻）。"""

    class _TwoPage:
        def __init__(self) -> None:
            self.calls = 0

        def goods_count(self, market: int) -> int:
            return 0

        def goods_quotes_list(self, market: int, start: int = 0, count: int = 80):
            self.calls += 1
            n = 80 if start == 0 else 20
            return _quotes_df([_row(f"C{start + i}", f"股{i}", 10.0, 10.0) for i in range(n)])

    client = _TwoPage()
    rank_mod._build_with_client("US", client)
    assert client.calls == 2


def test_build_with_client_stops_when_total_reached():
    """已拉够市场总数即停（与 symbol_index._fetch_all 同口径）。"""

    class _Exact:
        def __init__(self) -> None:
            self.calls = 0

        def goods_count(self, market: int) -> int:
            return 100

        def goods_quotes_list(self, market: int, start: int = 0, count: int = 80):
            self.calls += 1
            return _quotes_df([_row(f"C{start + i}", f"股{i}", 10.0, 10.0) for i in range(80)])

    client = _Exact()
    rank_mod._build_with_client("US", client)
    # 第一页 offset=80 < 100 继续；第二页后 offset=160 >= 100 停止
    assert client.calls == 2
