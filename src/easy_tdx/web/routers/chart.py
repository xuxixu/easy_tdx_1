"""K 线图 option 路由：服务端组装 ECharts option JSON，前端照画。

POST /chart/kline-option：K 线 + 已决议的指标条目（公式文本与展示映射
由前端发过来）→ 后端公式引擎计算 → pyecharts 组装 option。tooltip 与
标题前端合并，不经过网络（formatter 是 JS 函数）。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from easy_tdx.kline_option import ChartItemSpec, build_kline_option, compute_item_lines

router = APIRouter(tags=["chart"])

_HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class ChartBar(BaseModel):
    """K 线 OHLCV（指标计算与作图输入）。"""

    datetime: str = Field(..., min_length=1, max_length=32)
    open: float = Field(...)
    high: float = Field(...)
    low: float = Field(...)
    close: float = Field(...)
    vol: float = Field(...)


class ChartItem(BaseModel):
    """单条指标：公式文本 + 展示映射（列→图例名/颜色/虚线/bar）。"""

    id: str = Field(..., min_length=1, max_length=64)
    formula: str = Field(..., min_length=1, max_length=8000)
    pane: Literal["main", "sub"] = Field(default="main")
    display: dict[str, str] = Field(default_factory=dict)
    colors: dict[str, str] = Field(default_factory=dict)
    dashed: list[str] = Field(default_factory=list, max_length=16)
    bar_cols: list[str] = Field(default_factory=list, max_length=16)
    # 叠加 K 线列（自定义指标“叠加K线显示”）：4 个输出列名[开,高,低,收]
    candle_cols: list[str] = Field(default_factory=list, max_length=4)


class KlineOptionRequest(BaseModel):
    """K 线图 option 构建请求。"""

    bars: list[ChartBar] = Field(..., min_length=1, max_length=2000)
    items: list[ChartItem] = Field(default_factory=list, max_length=12)
    axis_color: str = Field(
        default="#2a2e3a", pattern=_HEX_COLOR, description="Y 轴分割线色（前端当前主题 --border）"
    )
    up_color: str = Field(default="#ef4146", pattern=_HEX_COLOR)
    down_color: str = Field(default="#18a058", pattern=_HEX_COLOR)


def _axis_labels(datetimes: list[str]) -> list[str]:
    """K 线横轴标签：日线及以上取日期，分钟线取 "MM-DD HH:mm"。

    前端 datetime 已归一为 "YYYY-MM-DD[ T]HH:MM:SS"（日线为 T00:00:00）。
    分钟线若只截日期，整轴是同一天重复上百次，无法分辨。
    """
    norm = [d.replace("T", " ") for d in datetimes]
    intraday = any(len(d) > 13 and d[11:16] != "00:00" for d in norm)
    if intraday:
        return [d[5:16] if len(d) >= 16 else d[:10] for d in norm]
    return [d[:10] for d in norm]


@router.post("/chart/kline-option")
async def kline_option(req: KlineOptionRequest) -> dict[str, Any]:
    """构建 K 线图完整 option（不含 tooltip/title，前端合并）。"""
    import pandas as pd

    df = pd.DataFrame(
        {
            "open": [b.open for b in req.bars],
            "high": [b.high for b in req.bars],
            "low": [b.low for b in req.bars],
            "close": [b.close for b in req.bars],
            "vol": [b.vol for b in req.bars],
        }
    )
    specs = [
        ChartItemSpec(
            id=it.id,
            formula=it.formula,
            pane=it.pane,
            display=dict(it.display),
            colors=dict(it.colors),
            dashed=list(it.dashed),
            bar_cols=list(it.bar_cols),
            candle_cols=list(it.candle_cols),
        )
        for it in req.items
    ]
    try:
        mains, subs, candles = compute_item_lines(df, specs)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    n = len(req.bars)
    dates = _axis_labels([b.datetime for b in req.bars])
    ohlc = [[b.open, b.close, b.low, b.high] for b in req.bars]
    vols = [b.vol for b in req.bars]
    ups = [b.close >= b.open for b in req.bars]
    option = build_kline_option(
        dates,
        ohlc,
        vols,
        ups,
        mains,
        subs,
        axis_color=req.axis_color,
        up_color=req.up_color,
        down_color=req.down_color,
        candles=candles,
    )
    assert len(option["series"]) >= 2  # 至少 K 线 + 成交量
    return {"option": option, "count": n}
