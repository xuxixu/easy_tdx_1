"""MarketGateway 取数契约：扩展栈 K 线续取、盘口归一化、价格列兼容。

对应三个实测缺陷：
1. 扩展栈单次上限 700 根，网关原样透传 count=800，导致按 800 步进的翻页
   每页漏 100 根（AAPL 日K 实测缺 2023-08-10~2024-01-02）。
2. 续取到的第二页是**更旧**数据，直接拼在尾部会让时间列非单调。
3. 扩展栈报价价格列叫 ``close``（非 ``price``），旧判空逻辑把每一帧都当
   「全空」→ 永远回落免费快照 → 港美股五档盘口永远拿不到。
"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.models.enums import KlineCategory
from easy_tdx.web.market_gateway import MarketGateway, _all_prices_null, validate_code


def _df(dates: pd.DatetimeIndex) -> pd.DataFrame:
    n = len(dates)
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "vol": [1.0] * n,
            "amount": [1.0] * n,
        }
    )


class _ExClient:
    """按调用顺序吐出预设页；记录 (start, count) 以便断言续取位置。"""

    def __init__(self, pages: list[pd.DataFrame]) -> None:
        self.pages = pages
        self.calls: list[tuple[int, int]] = []

    async def goods_kline(self, market, code, period, start, count, adjust=0):  # noqa: PLR0913
        self.calls.append((start, count))
        idx = len(self.calls) - 1
        if idx >= len(self.pages):
            return pd.DataFrame()
        return self.pages[idx]

    async def goods_quotes(self, stocks, fields=None):  # noqa: ARG002
        return pd.DataFrame()


# ── 1. K 线续取补满 ──────────────────────────────────────────────────────────


async def test_ex_kline_fills_count_beyond_protocol_cap():
    """count=800 而单页上限 700 时，必须续取剩余的 100 根。"""
    newer = _df(pd.date_range(end="2026-10-16", periods=700, freq="D"))
    older = _df(pd.date_range(end="2024-11-01", periods=100, freq="D"))
    client = _ExClient([newer, older])
    gw = MarketGateway(mac_ex_client=client)

    out = await gw.bars("US", "AAPL", KlineCategory.DAY, start=0, count=800)

    assert len(out) == 800, "必须补满 800 根，不能只返回协议上限 700"
    assert client.calls == [(0, 800), (700, 100)], "续取应从第 700 根起要剩余 100 根"


async def test_ex_kline_result_is_time_ascending():
    """续取的旧数据必须排到前面，保证时间单调（下游一律假设升序）。"""
    newer = _df(pd.date_range(end="2026-10-16", periods=700, freq="D"))
    older = _df(pd.date_range(end="2024-11-01", periods=100, freq="D"))
    client = _ExClient([newer, older])
    gw = MarketGateway(mac_ex_client=client)

    out = await gw.bars("US", "AAPL", KlineCategory.DAY, start=0, count=800)

    col = "date" if "date" in out.columns else "datetime"
    assert out[col].is_monotonic_increasing, "拼接后时间列必须单调递增"
    assert out[col].iloc[0] < out[col].iloc[-1]


async def test_ex_kline_single_page_when_count_within_cap():
    """count ≤ 700 时只发一次请求，不多余续取。"""
    client = _ExClient([_df(pd.date_range(end="2026-10-16", periods=300, freq="D"))])
    gw = MarketGateway(mac_ex_client=client)

    out = await gw.bars("US", "AAPL", KlineCategory.DAY, start=0, count=300)

    assert len(out) == 300
    assert client.calls == [(0, 300)]


async def test_ex_kline_stops_when_server_exhausted():
    """服务端提前取尽（返回不足）时不得死循环。"""
    client = _ExClient([_df(pd.date_range(end="2026-10-16", periods=700, freq="D"))])
    gw = MarketGateway(mac_ex_client=client)

    out = await gw.bars("US", "AAPL", KlineCategory.DAY, start=0, count=800)

    assert len(out) == 700, "第二页为空时只能返回已取到的 700 根"
    assert len(client.calls) == 2, "第二页空后应立即停止，不再续取"


async def test_ex_kline_empty_returns_empty_frame():
    """完全没有数据时返回空表而非抛错。"""
    gw = MarketGateway(mac_ex_client=_ExClient([]))
    out = await gw.bars("US", "AAPL", KlineCategory.DAY, start=0, count=800)
    assert out is not None
    assert len(out) == 0


# ── 2. 价格列兼容 ────────────────────────────────────────────────────────────


def test_all_prices_null_accepts_close_column():
    """扩展栈用 close 表示最新价，不能被判成「全空」。"""
    assert _all_prices_null(pd.DataFrame([{"close": 343.5}])) is False
    assert _all_prices_null(pd.DataFrame([{"price": 343.5}])) is False
    assert _all_prices_null(pd.DataFrame([{"close": None}])) is True
    assert _all_prices_null(pd.DataFrame([{"other": 1}])) is True
    assert _all_prices_null(None) is True


async def test_ex_quotes_keeps_tdx_rows_when_only_close_present(monkeypatch):
    """只有 close 的扩展栈报价应被采用，而不是回落免费快照。

    这是港美股拿不到五档的根因：判空永远命中 → 一定走快照源（无量档深度）。
    """
    from easy_tdx.sources import us_hk_snapshot

    tdx_df = pd.DataFrame([{"market": 74, "code": "AAPL", "close": 343.5, "bid1": 343.4}])

    class _Client:
        async def goods_quotes(self, stocks, fields=None):  # noqa: ARG002
            return tdx_df

    def _boom(codes):  # noqa: ARG001
        raise AssertionError("扩展栈可用时不应调用快照兜底")

    monkeypatch.setattr(us_hk_snapshot, "fetch_quotes", _boom)
    gw = MarketGateway(mac_ex_client=_Client())

    out = await gw.quotes("US", ["AAPL"])

    assert out.iloc[0]["close"] == 343.5
    assert "bid1" in out.columns


# ── 3. 盘口字段归一化 ────────────────────────────────────────────────────────


def test_normalize_ex_quotes_maps_depth_columns():
    """扩展栈档位名（bid_price / bid2_price …）→ 前端契约（bid1 / bid2 …）。"""
    gw = MarketGateway()
    df = pd.DataFrame(
        [
            {
                "bid_price": 343.4,
                "ask_price": 343.5,
                "bid_volume": 10,
                "ask_volume": 20,
                "bid2_price": 343.3,
                "ask5_volume": 5,
                "close": 343.5,
            }
        ]
    )

    out = gw._normalize_ex_quotes(df)

    row = out.iloc[0]
    assert row["bid1"] == 343.4
    assert row["ask1"] == 343.5
    assert row["bid_vol1"] == 10
    assert row["ask_vol1"] == 20
    assert row["bid2"] == 343.3
    assert row["ask_vol5"] == 5
    # 非档位列原样保留
    assert row["close"] == 343.5


def test_normalize_ex_quotes_adds_price_from_close():
    """无盘口列时仍要补 ``price``（扩展栈最新价叫 close）。

    A 股标准协议给 ``price``、扩展栈给 ``close``；出口不统一的话，前端
    ``normalizeQuote`` 与 SSE 的 ``_df_to_dicts`` 都得各自打补丁（现状确实各打了一次）。
    """
    gw = MarketGateway()
    df = pd.DataFrame([{"code": "AAPL", "close": 1.0}])

    out = gw._normalize_ex_quotes(df)

    assert list(out.columns) == ["code", "close", "price"]
    assert out.iloc[0]["price"] == 1.0


def test_normalize_ex_quotes_keeps_existing_price():
    """已有 price 时不覆盖（A 股口径优先）。"""
    gw = MarketGateway()
    df = pd.DataFrame([{"code": "600000", "close": 10.0, "price": 9.9}])
    out = gw._normalize_ex_quotes(df)
    assert out.iloc[0]["price"] == 9.9


def test_normalize_ex_quotes_no_price_without_close():
    """既无 price 也无 close 时不得凭空造列。"""
    gw = MarketGateway()
    out = gw._normalize_ex_quotes(pd.DataFrame([{"code": "X"}]))
    assert list(out.columns) == ["code"]


def test_normalize_ex_quotes_handles_empty():
    gw = MarketGateway()
    assert gw._normalize_ex_quotes(pd.DataFrame()).empty
    assert gw._normalize_ex_quotes(None) is None


# ── 4. validate_code：A 股板块指数（板块弹窗图表区）────────────────────────


def test_validate_code_accepts_a_share_board_index():
    """88 开头的 7 位数字是通达信板块指数，/minute 与 /bars 都靠它取数。

    回归点：旧校验对 SH/SZ/BJ 只放行「6 位数字」，板块弹窗传 8810202 时
    /minute、/bars 双双 400「A 股代码应为 6 位数字」，整个图表区空白。
    """
    for market in ("SH", "SZ", "BJ"):
        assert validate_code("8810202", market) == "8810202"
        assert validate_code("885001", market) == "885001"  # 6 位也属板块，仍按普通放行


def test_validate_code_accepts_normal_a_share():
    """普通个股 6 位数字不受影响。"""
    assert validate_code("600519", "SH") == "600519"
    assert validate_code("000001", "SZ") == "000001"


def test_validate_code_rejects_other_7_digit_a_share():
    """放行「88 开头」而非任意 7 位数字，避免把非法代码放进来。"""
    with pytest.raises(ValueError, match="6 位数字"):
        validate_code("1234567", "SH")
    with pytest.raises(ValueError, match="6 位数字"):
        validate_code("9910202", "SH")


def test_validate_code_board_prefixes_unchanged():
    """港美股板块（HK0285 / US0467）原有特判不能被本次修改破坏。"""
    assert validate_code("HK0285", "HK") == "HK0285"
    assert validate_code("US0467", "US") == "US0467"


# ── 5. minute(query_date)：美股盘前回退上一交易日分时 ─────────────────────


class _ExChartClient:
    """记录 goods_tick_chart 的 (market, code, query_date)，返回带 charts 的单行。"""

    def __init__(self) -> None:
        self.calls: list[tuple[object, str, object]] = []

    async def goods_tick_chart(self, market, code, query_date=None):  # noqa: ANN001
        self.calls.append((market, code, query_date))
        charts = [
            {"time": "22:30", "price": 100.0, "avg": 100.0, "vol": 1},
            {"time": "22:31", "price": 100.5, "avg": 100.2, "vol": 2},
        ]
        return pd.DataFrame(
            [{"market": market, "code": code, "name": "X", "pre_close": 99.0, "charts": charts}]
        )


async def test_minute_passes_query_date_to_ex_chart():
    """带 query_date 时透传给 goods_tick_chart（盘前回退上一交易日取完整分时）。"""
    client = _ExChartClient()
    gw = MarketGateway(mac_ex_client=client)
    out = await gw.minute("US", "SPY", 20261106)
    assert client.calls == [(74, "SPY", 20261106)]
    assert len(out) == 2, "charts 应展开为两行分时"


async def test_minute_without_query_date_keeps_default():
    """不传 query_date 时 goods_tick_chart 收 None，保持原有「取当日」行为。"""
    client = _ExChartClient()
    gw = MarketGateway(mac_ex_client=client)
    await gw.minute("US", "SPY")
    assert client.calls[0][2] is None
