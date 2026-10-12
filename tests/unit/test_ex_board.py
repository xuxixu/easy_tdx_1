"""港美股板块路由（board-mac ex 分流）单测：零网络、零真实服务器。

覆盖：
- /board-mac/list?board_type=HK_HY 走 mac_ex（不碰 A 股 client）
- /board-mac/members?board_symbol=HK0285 走 mac_ex
- /board-mac/overview?board_type=US_HY 走 mac_ex
- ex 栈未连接时 503（不静默回落）
- A 股 board_type 不受影响（mac_ex=None 的最小 app 照常 200）
"""

from __future__ import annotations

import pandas as pd
import pytest


def _board_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class _FakeExClient:
    """扩展栈替身：记录调用，返回港美股形状数据。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def get_board_list(self, board_type=None, count=500, sort_column=None):
        name = getattr(sort_column, "name", None) or getattr(board_type, "name", "?")
        self.calls.append(("list", getattr(board_type, "name", str(board_type)), name))
        return _board_df(
            [
                {
                    "market": 70,
                    "code": "HK0285",
                    "name": "港股-恒大系",
                    "price": 1309.77,
                    "sort_value": 0.0,
                    "pre_close": 1239.12,
                    "symbol_market": 31,
                    "symbol_code": "06666",
                    "symbol_name": "恒大物业",
                    "symbol_price": 1.205,
                    "symbol_pre_close": 1.14,
                }
            ]
        )

    async def get_board_members(self, board_symbol="", count=100, sort_type=None, sort_order=None):
        self.calls.append(("members", board_symbol))
        return _board_df(
            [
                {
                    "market": 31,
                    "code": "06666",
                    "name": "恒大物业",
                    "pre_close": 1.14,
                    "open": 1.14,
                    "high": 1.215,
                    "low": 1.13,
                    "close": 1.205,
                    "vol": 23940000.0,
                    "amount": 27762270.0,
                }
            ]
        )


class _FakeAClient:
    """A 股替身：被调用即测试失败（ex 请求绝不能打到 A 股栈）。"""

    async def get_board_list(self, *args, **kwargs):  # noqa: ANN001,ANN002,ANN003
        raise AssertionError("ex 板块请求打到了 A 股 client")

    async def get_board_members(self, *args, **kwargs):  # noqa: ANN001,ANN002,ANN003
        raise AssertionError("ex 成分请求打到了 A 股 client")


def _board_app(a_client, ex_client):
    from fastapi import FastAPI

    from easy_tdx.web.routers import board_mac

    app = FastAPI()
    app.include_router(board_mac.router, prefix="/api/v1")
    app.state.mac_client = a_client
    app.state.mac_ex_client = ex_client
    return app


def test_ex_board_list_routes_to_mac_ex():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    with TestClient(_board_app(_FakeAClient(), _FakeExClient())) as client:
        resp = client.get("/api/v1/board-mac/list", params={"board_type": "HK_HY", "count": 5})
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert len(rows) == 1
    assert rows[0]["code"] == "HK0285"


def test_ex_board_members_routes_to_mac_ex():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    with TestClient(_board_app(_FakeAClient(), _FakeExClient())) as client:
        resp = client.get(
            "/api/v1/board-mac/members", params={"board_symbol": "HK0285", "count": 5}
        )
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert rows[0]["code"] == "06666"
    assert rows[0]["market"] == "31" or rows[0]["market"] == 31


def test_ex_board_overview_routes_to_mac_ex():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    with TestClient(_board_app(_FakeAClient(), _FakeExClient())) as client:
        resp = client.get(
            "/api/v1/board-mac/overview",
            params={"board_type": "US_HY", "metrics": "SPEED", "count": 10},
        )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["board_type"] == "US_HY"
    assert body["count"] == 1
    assert body["rows"][0]["code"] == "HK0285"  # fake 数据复用


def test_ex_board_without_stack_returns_503():
    """mac_ex 未连接 → 503，不回落成 A 股数据。"""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    with TestClient(_board_app(_FakeAClient(), None)) as client:
        resp = client.get("/api/v1/board-mac/list", params={"board_type": "HK_HY"})
    assert resp.status_code == 503


def test_a_share_board_unaffected_without_mac_ex():
    """A 股请求在 mac_ex=None 的最小 app 下照常（回归守卫）。"""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    class _OK:
        async def get_board_list(self, board_type=None, count=500, sort_column=None):
            return _board_df(
                [
                    {
                        "market": 1,
                        "code": "881001",
                        "name": "测试板块",
                        "price": 100.0,
                        "sort_value": 0.0,
                        "pre_close": 99.0,
                        "symbol_market": 1,
                        "symbol_code": "600000",
                        "symbol_name": "领涨",
                        "symbol_price": 10.0,
                        "symbol_pre_close": 9.9,
                    }
                ]
            )

    with TestClient(_board_app(_OK(), None)) as client:
        resp = client.get("/api/v1/board-mac/list", params={"board_type": "HY", "count": 5})
    assert resp.status_code == 200
    assert resp.json()["data"][0]["code"] == "881001"
