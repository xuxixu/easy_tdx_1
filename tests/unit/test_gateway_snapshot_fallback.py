"""MarketGateway 扩展报价回落免费快照源：mock，不出网。"""

from __future__ import annotations

import pandas as pd
import pytest


def _gw():
    from easy_tdx.web.market_gateway import MarketGateway

    return MarketGateway(mac_client=None, tdx_client=None, mac_ex_client=None)


async def test_ex_quotes_falls_back_without_client(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot

    df = pd.DataFrame([{"market": "US", "code": "AAPL", "price": 1.0, "source": "sina"}])
    monkeypatch.setattr(us_hk_snapshot, "fetch_quotes", lambda codes: df)
    out = await _gw().quotes("US", ["AAPL"])
    assert out.iloc[0]["price"] == 1.0
    # 逐行标记不被整列覆盖（混批 sina/em 时保持准确）
    assert out.iloc[0]["source"] == "sina"


async def test_ex_quotes_prefers_tdx_client(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot
    from easy_tdx.web.market_gateway import MarketGateway

    tdx_df = pd.DataFrame([{"market": "US", "code": "AAPL", "price": 2.0}])

    class _Client:
        async def goods_quotes(self, stocks):
            return tdx_df

    def _boom(codes):
        raise AssertionError("主链成功时不应调用兜底")

    monkeypatch.setattr(us_hk_snapshot, "fetch_quotes", _boom)
    gw = MarketGateway(mac_client=None, tdx_client=None, mac_ex_client=_Client())
    out = await gw.quotes("US", ["AAPL"])
    assert out.iloc[0]["price"] == 2.0
    assert out.iloc[0]["source"] == "tdx"


async def test_ex_quotes_tdx_failure_falls_back(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot
    from easy_tdx.web.market_gateway import MarketGateway

    class _Client:
        async def goods_quotes(self, stocks):
            raise ConnectionError("7727 抖动")

    snap = pd.DataFrame([{"market": "US", "code": "AAPL", "price": 3.0, "source": "em"}])
    monkeypatch.setattr(us_hk_snapshot, "fetch_quotes", lambda codes: snap)
    gw = MarketGateway(mac_client=None, tdx_client=None, mac_ex_client=_Client())
    out = await gw.quotes("US", ["AAPL"])
    assert out.iloc[0]["price"] == 3.0
    assert out.iloc[0]["source"] == "em"


async def test_ex_quotes_raises_when_all_fail(monkeypatch):
    from easy_tdx.exceptions import TdxConnectionError
    from easy_tdx.sources import us_hk_snapshot

    monkeypatch.setattr(us_hk_snapshot, "is_enabled", lambda: False)
    with pytest.raises(TdxConnectionError):
        await _gw().quotes("US", ["AAPL"])


async def test_ex_quotes_all_null_prices_falls_back(monkeypatch):
    """TDX 返回全空价格行（盘前/收盘后）→ 视同失败走兜底。"""
    from easy_tdx.sources import us_hk_snapshot
    from easy_tdx.web.market_gateway import MarketGateway

    class _Client:
        async def goods_quotes(self, stocks):
            return pd.DataFrame(
                [{"market": 74, "code": "AAPL", "price": None, "pre_close": 341.27}]
            )

    snap = pd.DataFrame([{"market": "US", "code": "AAPL", "price": 341.27, "source": "sina"}])
    monkeypatch.setattr(us_hk_snapshot, "fetch_quotes", lambda codes: snap)
    gw = MarketGateway(mac_client=None, tdx_client=None, mac_ex_client=_Client())
    out = await gw.quotes("US", ["AAPL"])
    assert out.iloc[0]["price"] == 341.27
    assert out.iloc[0]["source"] == "sina"


async def test_ex_quotes_partial_null_keeps_tdx(monkeypatch):
    """部分空价格不断整批：保留 TDX 行的深度数据。"""
    from easy_tdx.sources import us_hk_snapshot
    from easy_tdx.web.market_gateway import MarketGateway

    class _Client:
        async def goods_quotes(self, stocks):
            return pd.DataFrame(
                [
                    {"market": 74, "code": "AAPL", "price": 341.27},
                    {"market": 74, "code": "MSFT", "price": None},
                ]
            )

    def _boom(codes):
        raise AssertionError("部分可用时不应走兜底")

    monkeypatch.setattr(us_hk_snapshot, "fetch_quotes", _boom)
    gw = MarketGateway(mac_client=None, tdx_client=None, mac_ex_client=_Client())
    out = await gw.quotes("US", ["AAPL", "MSFT"])
    assert out.iloc[0]["source"] == "tdx"
    assert len(out) == 2
