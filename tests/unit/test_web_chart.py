"""K 线图 option 路由测试（pyecharts 组装 + 终端口径，离线）。"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pyecharts")

from fastapi.testclient import TestClient  # noqa: E402

from easy_tdx.web import create_app  # noqa: E402


def _bars(n: int = 60) -> list[dict[str, object]]:
    return [
        {
            "datetime": f"2024-03-{i + 1:02d}",
            "open": 10.0 + i * 0.1,
            "high": 10.5 + i * 0.1,
            "low": 9.8 + i * 0.1,
            "close": 10.2 + i * 0.1,
            "vol": 1000.0 + i,
        }
        for i in range(n)
    ]


def _ma_item() -> dict[str, object]:
    return {
        "id": "ma",
        "formula": "MA5: MA(C,5);",
        "pane": "main",
        "display": {"MA5": "MA5"},
        "colors": {"MA5": "#f0a020"},
        "dashed": [],
        "bar_cols": [],
    }


def _macd_item() -> dict[str, object]:
    return {
        "id": "macd",
        "formula": "DIF: EMA(C,12)-EMA(C,26); DEA: EMA(DIF,9); MACD_HIST: (DIF-DEA)*2;",
        "pane": "sub",
        "display": {"DIF": "DIF", "DEA": "DEA", "MACD_HIST": "MACD"},
        "colors": {"DIF": "#f0a020", "DEA": "#4a9eff", "MACD_HIST": "#f0a020"},
        "dashed": [],
        "bar_cols": ["MACD_HIST"],
    }


def _client() -> TestClient:
    return TestClient(create_app())


def _option(body: dict[str, object]) -> dict[str, object]:
    client = _client()
    r = client.post("/api/v1/chart/kline-option", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == len(body["bars"])  # type: ignore[index]
    assert isinstance(data["option"], dict)
    return data["option"]  # type: ignore[no-any-return]


def _no_nan(obj: object) -> None:
    if isinstance(obj, float):
        assert not (math.isnan(obj) or math.isinf(obj)), f"NaN/inf 漏出：{obj}"
    elif isinstance(obj, dict):
        for v in obj.values():
            _no_nan(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_nan(v)


def test_structure_ma_macd():
    opt = _option({"bars": _bars(), "items": [_ma_item(), _macd_item()]})
    assert opt["backgroundColor"] == "transparent"
    assert len(opt["grid"]) == 3
    assert len(opt["xAxis"]) == 3 and len(opt["yAxis"]) == 3
    assert all(ax["data"][0] == "2024-03-01" for ax in opt["xAxis"])
    kinds = [(s["name"], s["type"]) for s in opt["series"]]
    assert kinds == [
        ("K线", "candlestick"),
        ("MA5", "line"),
        ("成交量", "bar"),
        ("DIF", "line"),
        ("DEA", "line"),
        ("MACD", "bar"),
    ]
    # 图例合并为单个（bar 不进副图图例，与旧口径一致）
    assert opt["legend"]["data"] == ["K线", "MA5", "DIF,DEA"]
    # dataZoom 双份 + 轴全覆盖
    assert len(opt["dataZoom"]) == 2
    assert opt["dataZoom"][0]["xAxisIndex"] == [0, 1, 2]
    # tooltip 由前端合并，后端不下发
    assert "tooltip" not in opt


def test_line_data_unwrapped_and_aligned():
    opt = _option({"bars": _bars(), "items": [_ma_item()]})
    ma = next(s for s in opt["series"] if s["name"] == "MA5")
    assert len(ma["data"]) == 60
    assert ma["data"][:4] == [None, None, None, None]
    assert ma["data"][4] == pytest.approx((10.2 + 10.3 + 10.4 + 10.5 + 10.6) / 5)
    assert ma["lineStyle"]["width"] == 1
    assert ma["lineStyle"]["type"] == "solid"
    _no_nan(opt)


def test_candle_and_volume_colors():
    opt = _option(
        {
            "bars": _bars(),
            "items": [],
            "axis_color": "#2a2e3a",
            "up_color": "#ef4146",
            "down_color": "#18a058",
        }
    )
    k = next(s for s in opt["series"] if s["name"] == "K线")
    assert k["itemStyle"] == {
        "color": "#ef4146",
        "color0": "#18a058",
        "borderColor": "#ef4146",
        "borderColor0": "#18a058",
    }
    assert k["data"][0] == [10.0, 10.2, 9.8, 10.5]  # [开, 收, 低, 高] 前端口径
    vol = next(s for s in opt["series"] if s["name"] == "成交量")
    assert vol["data"][0] == {"value": 1000.0, "itemStyle": {"color": "#ef4146"}}
    assert vol["barWidth"] == "60%"
    assert opt["yAxis"][0]["splitLine"]["lineStyle"]["color"] == "#2a2e3a"


def test_no_sub_two_grids():
    opt = _option({"bars": _bars(), "items": [_ma_item()]})
    assert len(opt["grid"]) == 2
    assert len(opt["xAxis"]) == 2
    assert opt["legend"]["data"] == ["K线", "MA5"]
    assert opt["dataZoom"][0]["xAxisIndex"] == [0, 1]


def test_unmapped_column_fallback():
    opt = _option(
        {
            "bars": _bars(),
            "items": [
                {"id": "c1", "formula": "XYZ: MA(C,5);", "pane": "main"},
            ],
        }
    )
    names = [s["name"] for s in opt["series"]]
    assert "XYZ" in names
    xyz = next(s for s in opt["series"] if s["name"] == "XYZ")
    assert xyz["lineStyle"]["color"] == "#f97316"  # 兜底色表首位


def test_values_length_normalized():
    opt = _option(
        {
            "bars": _bars(10),
            "items": [
                {
                    "id": "ma",
                    "formula": "MA5: MA(C,5);",
                    "pane": "main",
                    "display": {"MA5": "MA5"},
                    "colors": {"MA5": "#f0a020"},
                }
            ],
        }
    )
    ma = next(s for s in opt["series"] if s["name"] == "MA5")
    assert len(ma["data"]) == 10


def test_bad_formula_400_empty_bars_422():
    client = _client()
    r = client.post(
        "/api/v1/chart/kline-option",
        json={"bars": _bars(), "items": [{"id": "x", "formula": "A := ;", "pane": "main"}]},
    )
    assert r.status_code == 400
    r2 = client.post("/api/v1/chart/kline-option", json={"bars": [], "items": []})
    assert r2.status_code == 422
    r3 = client.post(
        "/api/v1/chart/kline-option",
        json={"bars": _bars(), "items": [], "axis_color": "red"},
    )
    assert r3.status_code == 422


def test_deterministic():
    body = {"bars": _bars(), "items": [_ma_item(), _macd_item()]}
    assert _option(body) == _option(body)
