"""240 分钟（4 小时）K 线与分钟图标签单元测试（bars.py / chart.py）。

覆盖：
- MIN_240 别名集；
- _resample_pairs factor=4 分组（余数丢最旧、聚合口径与 factor=2 一致）；
- /bars?category=MIN_120 可达（回归：别名分支曾写在 category_from_str
  之后，实际抛 ValueError → 400，MIN_120 从未生效）；
- /bars?category=MIN_240 标准客户端 60M×4 重采样；
- /bars/index?category=MIN_120 指数 60M×2 重采样；
- 港美股 MIN_240 走网关 60M 取数后本地重采样；
- /chart/kline-option 分钟线横轴标签为 "MM-DD HH:mm"，日线保持 "YYYY-MM-DD"。
"""

from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from easy_tdx.web.errors import register_exception_handlers  # noqa: E402
from easy_tdx.web.routers import bars as bars_router  # noqa: E402
from easy_tdx.web.routers import chart as chart_router  # noqa: E402
from easy_tdx.web.routers.bars import (  # noqa: E402
    _MIN_120_ALIASES,
    _MIN_240_ALIASES,
    _resample_pairs,
)


def _minute_df(n: int = 8) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-02 09:30", periods=n, freq="60min"),
            "open": [float(10 + i) for i in range(n)],
            "close": [float(10.5 + i) for i in range(n)],
            "high": [float(10.8 + i) for i in range(n)],
            "low": [float(9.9 + i) for i in range(n)],
            "vol": [float(100 * (i + 1)) for i in range(n)],
            "amount": [float(1000 * (i + 1)) for i in range(n)],
        }
    )


def test_min_240_aliases():
    assert _MIN_240_ALIASES == {"MIN_240", "240M", "240MIN"}
    assert _MIN_120_ALIASES == {"MIN_120", "120M", "120MIN"}


class TestResampleFactor4:
    def test_even_groups(self):
        """8 根 60M → 2 根 240M，聚合口径与 factor=2 一致。"""
        r = _resample_pairs(_minute_df(8), 10, factor=4)
        assert len(r) == 2
        row = r.iloc[0]  # bar0..bar3
        assert row["open"] == 10 and row["close"] == 13.5
        assert row["high"] == 13.8 and row["low"] == 9.9
        assert row["vol"] == 100 + 200 + 300 + 400
        assert str(row["datetime"]) == "2024-01-02 12:30:00"  # 组内后一根时间

    def test_remainder_drops_oldest(self):
        """9 根丢最旧 1 根（余数），保最新数据整组对齐。"""
        r = _resample_pairs(_minute_df(9), 10, factor=4)
        assert len(r) == 2
        assert r.iloc[0]["open"] == 11  # 从 bar1 起

    def test_count_trims_oldest_side(self):
        r = _resample_pairs(_minute_df(8), 1, factor=4)
        assert len(r) == 1 and r.iloc[0]["close"] == 17.5  # tail 保留最新组

    def test_factor_2_unchanged(self):
        r = _resample_pairs(_minute_df(4), 10)
        assert len(r) == 2 and r.iloc[0]["open"] == 10

    def test_bad_factor_raises(self):
        with pytest.raises(ValueError):
            _resample_pairs(_minute_df(4), 10, factor=1)

    def test_missing_datetime_raises_readable_error(self):
        """缺 datetime 列（如快照源的单日 date 行）转可读 ValueError，不抛 KeyError。"""
        with pytest.raises(ValueError, match="datetime"):
            _resample_pairs(_minute_df(4).rename(columns={"datetime": "date"}), 10)


# ── 路由测试替身 ─────────────────────────────────────────────────────────────


class _Std60M:
    """标准客户端替身：一律返回 8 根 60M，并记录请求的周期名。"""

    def __init__(self):
        self.categories: list[str] = []

    async def get_security_bars(self, *args, **kwargs):  # noqa: ANN002, ANN003
        cat = args[2] if len(args) > 2 else kwargs.get("category")
        self.categories.append(getattr(cat, "name", str(cat)))
        return _minute_df(8)

    async def get_index_bars(self, *args, **kwargs):  # noqa: ANN002, ANN003
        cat = args[2] if len(args) > 2 else kwargs.get("category")
        self.categories.append(getattr(cat, "name", str(cat)))
        return _minute_df(8)


class _FakeGateway:
    """网关替身：记录周期名，返回 8 根 60M（含 datetime 列）。"""

    def __init__(self):
        self.categories: list[str] = []

    async def bars(self, market, code, category, start=0, count=800, adjust=None):  # noqa: ANN001, ANN003
        self.categories.append(getattr(category, "name", str(category)))
        return _minute_df(8)


def _bars_app(tdx_client, gateway=None):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(bars_router.router, prefix="/api/v1")
    app.state.tdx_client = tdx_client
    app.state.mac_client = None
    app.state.gateway = gateway
    return app


def test_bars_min120_reachable_via_std_client():
    """回归：MIN_120 曾因先转换后特判而 400，此处应 200 且 4 根 60M→2 根。"""
    std = _Std60M()
    with TestClient(_bars_app(std)) as client:
        resp = client.get(
            "/api/v1/bars", params={"market": "SH", "code": "600519", "category": "MIN_120"}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 4
    assert std.categories == ["MIN_60"]
    rows = body["data"]
    assert rows[0]["open"] == 10 and rows[0]["close"] == 11.5
    assert rows[1]["open"] == 12 and rows[1]["close"] == 13.5


def test_bars_min240_std_resample():
    std = _Std60M()
    with TestClient(_bars_app(std)) as client:
        resp = client.get(
            "/api/v1/bars", params={"market": "SH", "code": "600519", "category": "MIN_240"}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 2
    assert std.categories == ["MIN_60"]
    rows = body["data"]
    assert rows[0]["open"] == 10 and rows[0]["close"] == 13.5
    assert rows[0]["vol"] == 100 + 200 + 300 + 400


def test_bars_index_min120_resample():
    std = _Std60M()
    with TestClient(_bars_app(std)) as client:
        resp = client.get(
            "/api/v1/bars/index",
            params={"market": "SH", "code": "000001", "category": "MIN_120"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 4
    assert std.categories == ["MIN_60"]


def test_bars_ex_min240_gateway_resample():
    gw = _FakeGateway()
    with TestClient(_bars_app(_Std60M(), gateway=gw)) as client:
        resp = client.get(
            "/api/v1/bars", params={"market": "HK", "code": "00700", "category": "MIN_240"}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 2
    assert gw.categories == ["MIN_60"]


def test_bars_ex_resample_without_60m_is_400_not_500():
    """网关只有快照单日行（无 datetime 列，如 HSI）时诚实 400，不 500。"""

    class _SnapshotGateway(_FakeGateway):
        async def bars(self, market, code, category, start=0, count=800, adjust=None):  # noqa: ANN001, ANN003
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2026-10-12"]),
                    "open": [24434.93],
                    "close": [24233.78],
                    "high": [24455.95],
                    "low": [24193.30],
                    "vol": [131981246862.0],
                    "amount": [0.0],
                }
            )

    with TestClient(_bars_app(_Std60M(), gateway=_SnapshotGateway())) as client:
        resp = client.get(
            "/api/v1/bars", params={"market": "HK", "code": "HSI", "category": "MIN_240"}
        )
    assert resp.status_code == 400, resp.text
    assert "60 分钟" in resp.json()["detail"]


def test_bars_ex_min120_gateway_resample():
    gw = _FakeGateway()
    with TestClient(_bars_app(_Std60M(), gateway=gw)) as client:
        resp = client.get(
            "/api/v1/bars", params={"market": "US", "code": "AAPL", "category": "MIN_120"}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 4  # 8 根 60M → 4 根 120M
    assert gw.categories == ["MIN_60"]


# ── 图表标签 ─────────────────────────────────────────────────────────────────


def _chart_app():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(chart_router.router, prefix="/api/v1")
    return app


def _minute_bars(n: int = 10) -> list[dict[str, object]]:
    return [
        {
            "datetime": f"2024-03-01T09:{30 + i:02d}:00",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "vol": 1000.0,
        }
        for i in range(n)
    ]


def test_chart_intraday_axis_labels():
    """分钟线横轴为 "MM-DD HH:mm"，不再是重复的同一天日期。"""
    with TestClient(_chart_app()) as client:
        r = client.post("/api/v1/chart/kline-option", json={"bars": _minute_bars(), "items": []})
    assert r.status_code == 200, r.text
    opt = r.json()["option"]
    for ax in opt["xAxis"]:
        assert ax["data"][0] == "03-01 09:30"
        assert ax["data"][9] == "03-01 09:39"
        assert len(set(ax["data"])) == 10  # 互不相同


def test_chart_daily_axis_labels_unchanged():
    """日线标签保持 "YYYY-MM-DD"（旧契约不变）。"""
    bars = [
        {
            "datetime": f"2024-03-{i + 1:02d}T00:00:00",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "vol": 1000.0,
        }
        for i in range(5)
    ]
    with TestClient(_chart_app()) as client:
        r = client.post("/api/v1/chart/kline-option", json={"bars": bars, "items": []})
    assert r.status_code == 200, r.text
    for ax in r.json()["option"]["xAxis"]:
        assert ax["data"][0] == "2024-03-01"
