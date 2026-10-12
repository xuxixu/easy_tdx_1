"""K 线图 ECharts option 服务端构建（pyecharts 组装序列 + 终端口径拼装布局）。

前端 StockKline 的 option 改由本模块生成（POST /chart/kline-option），
前端只做 setOption + 本地 tooltip 合并 + 主题重建。

分工（刻意为之）：
- 序列（K/线/柱及其样式）经 pyecharts 组装，保证 schema 正确；
- 布局（grid/轴/dataZoom/图例/背景）按终端口径手拼，与前端旧
  buildOption 逐项对齐（见 tests/unit/test_web_chart.py）——多 grid
  终端布局用 pyecharts Grid API 表达笨拙且易漂移，手拼更可审；
- tooltip/title 一律不下发（formatter 是 JS 函数，过不了 JSON；
  标题前端自有）。

计算口径：各条目公式由调用方给文本，本模块只做 compile + compute
（与 /formula/compute 同引擎），不重复拉行情。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# 兜底配色（与前端 customColors 同表）：display/colors 未映射的列按序取用
FALLBACK_COLORS = ["#f97316", "#a3e635", "#f472b6", "#2dd4bf", "#facc15", "#818cf8"]


def _clean_num(v: Any) -> float | None:
    """数值清洗为 JSON 原生 float（NaN/±inf/非法 → None）。

    Starlette 以 allow_nan=False 序列化，NaN 漏出去整个响应 500。
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _normalize(values: list[Any], n: int) -> list[float | None]:
    """序列对齐到 K 线长度（短补 None、长截断），保证图表不错位。"""
    cleaned = [_clean_num(v) for v in values]
    if len(cleaned) < n:
        cleaned.extend([None] * (n - len(cleaned)))
    return cleaned[:n]


def _is_bar_col(name: str) -> bool:
    """副图列名约定（与前端 defaultIsBar 同规则）：含 HIST/柱/量画 bar。"""
    return "HIST" in name.upper() or "柱" in name or "量" in name


@dataclass
class ChartItemSpec:
    """单条指标的计算与展示规格（前端把预置/自定义决议成纯数据发过来）。"""

    id: str
    formula: str
    pane: str = "main"
    display: dict[str, str] = field(default_factory=dict)
    colors: dict[str, str] = field(default_factory=dict)
    dashed: list[str] = field(default_factory=list)
    bar_cols: list[str] = field(default_factory=list)
    # 叠加 K 线列（自定义指标“叠加K线显示”）：4 个数值输出列名
    # [开, 高, 低, 收]，命中后画成主图叠加蜡烛、不再画线
    candle_cols: list[str] = field(default_factory=list)


@dataclass
class BuiltLine:
    """一条已算好的图例线。"""

    name: str
    values: list[float | None]
    color: str
    dashed: bool = False
    bar: bool = False
    pane: str = "main"


@dataclass
class BuiltCandle:
    """一组叠加 K 线（自定义指标公式输出的 [开,高,低,收] 四列）。"""

    name: str
    rows: list[list[float] | None]  # pyecharts 行：[开, 收, 低, 高]，缺值整行 None
    pane: str = "main"


def compute_item_lines(
    df: pd.DataFrame, items: list[ChartItemSpec]
) -> tuple[list[BuiltLine], list[BuiltLine], list[BuiltCandle]]:
    """逐条目编译公式并计算，返回（主图线，副图线，叠加 K 线）。

    只取数值输出列（信号列不画线，与 full_series 口径一致）；
    ``candle_cols`` 命中的四列拼成蜡烛、不再逐列画线；
    未知条目 id 由调用方过滤；公式错误 fail fast（调用方转 400）。
    """
    from easy_tdx.formula import FormulaError, compile_formula

    mains: list[BuiltLine] = []
    subs: list[BuiltLine] = []
    candles: list[BuiltCandle] = []
    fallback_idx = 0
    for item in items:
        pane = "sub" if item.pane == "sub" else "main"
        candle_cols = [c for c in (item.candle_cols or []) if c]
        if candle_cols and pane != "main":
            raise ValueError(f"指标 {item.id} 的叠加 K 线只支持主图")
        if candle_cols and len(candle_cols) != 4:
            raise ValueError(f"指标 {item.id} 的叠加 K 线需指定 4 列[开,高,低,收]")
        try:
            compiled = compile_formula(item.formula)
        except FormulaError as exc:
            raise ValueError(f"指标 {item.id} 公式错误：{exc}") from exc
        try:
            result = compiled.compute(df)
        except FormulaError as exc:
            raise ValueError(f"指标 {item.id} 计算失败：{exc}") from exc
        frame = result.to_frame()
        n = len(df)
        if candle_cols:
            missing = [c for c in candle_cols if c not in result.values]
            if missing:
                raise ValueError(f"指标 {item.id} 的叠加 K 线列缺失数值输出：{missing}")
            co, ch, cl, cc = (frame[c].tolist() for c in candle_cols)
            rows: list[list[float] | None] = []
            for o, h, lo, c in zip(co, ch, cl, cc):
                nums = [_clean_num(o), _clean_num(h), _clean_num(lo), _clean_num(c)]
                if any(v is None for v in nums):
                    rows.append(None)
                else:
                    oo, hh, ll, cc2 = nums
                    assert oo is not None and hh is not None and ll is not None and cc2 is not None
                    rows.append([oo, cc2, ll, hh])
            rows = (rows + [None] * n)[:n]
            candles.append(
                BuiltCandle(name=item.display.get(candle_cols[0], item.id), rows=rows, pane=pane)
            )
        skip = set(candle_cols)
        for col in result.values:
            if col not in frame.columns or col in skip:
                continue
            raw: list[Any] = frame[col].tolist()
            color = item.colors.get(col)
            if color is None:
                color = FALLBACK_COLORS[fallback_idx % len(FALLBACK_COLORS)]
                fallback_idx += 1
            line = BuiltLine(
                name=item.display.get(col, col),
                values=_normalize(raw, n),
                color=color,
                dashed=col in item.dashed,
                bar=col in item.bar_cols
                or (pane == "sub" and not item.bar_cols and _is_bar_col(col)),
                pane=pane,
            )
            (subs if pane == "sub" else mains).append(line)
    return mains, subs, candles


def _series_json(chart: Any) -> list[dict[str, Any]]:
    """pyecharts 图表 → series JSON（公开 dump_options 接口，不碰内部）。"""
    import json

    opt = json.loads(chart.dump_options())
    series = opt.get("series")
    if not isinstance(series, list):
        return []
    return [s for s in series if isinstance(s, dict)]


def _plain_values(data: list[Any]) -> list[Any]:
    """pyecharts Line 会把值 zip 成 [x, y] 对；x 轴已有日期，此处只留 y。

    字典项（逐点着色的柱）原样保留。
    """
    out: list[Any] = []
    for d in data:
        if isinstance(d, list) and len(d) == 2 and isinstance(d[0], str):
            out.append(d[1])
        else:
            out.append(d)
    return out


def build_kline_option(
    dates: list[str],
    ohlc: list[list[float]],
    vols: list[float],
    ups: list[bool],
    mains: list[BuiltLine],
    subs: list[BuiltLine],
    *,
    axis_color: str,
    up_color: str,
    down_color: str,
    candles: list[BuiltCandle] | None = None,
) -> dict[str, Any]:
    """组装完整 option（不含 tooltip/title，前端合并）。

    dates/ohlc/vols/ups 等长；mains/subs 为已算好且对齐的线；
    candles 为叠加 K 线（与主 K 线同轴，多画一组蜡烛）。
    """
    from pyecharts import options as opts
    from pyecharts.charts import Bar, Candlestick, Line

    has_sub = len(subs) > 0
    n = len(dates)

    kchart = Candlestick()
    kchart.add_xaxis(dates)
    kchart.add_yaxis(
        "K线",
        ohlc,
        itemstyle_opts=opts.ItemStyleOpts(
            color=up_color, color0=down_color, border_color=up_color, border_color0=down_color
        ),
    )
    for m in mains:
        li = Line()
        li.add_xaxis(dates)
        li.add_yaxis(
            m.name,
            m.values,
            is_symbol_show=False,
            linestyle_opts=opts.LineStyleOpts(
                width=1, color=m.color, type_="dashed" if m.dashed else "solid"
            ),
            label_opts=opts.LabelOpts(is_show=False),
        )
        kchart = kchart.overlap(li)

    for cd in candles or []:
        # 叠加 K 线：与主 K 线同轴，空心，涨跌随主题色；缺值行传 null 断开
        cc = Candlestick()
        cc.add_xaxis(dates)
        cc.add_yaxis(
            cd.name,
            cd.rows,
            itemstyle_opts=opts.ItemStyleOpts(
                color="transparent",
                color0="transparent",
                border_color=up_color,
                border_color0=down_color,
            ),
        )
        kchart = kchart.overlap(cc)

    vchart = Bar()
    vchart.add_xaxis(dates)
    vchart.add_yaxis(
        "成交量",
        [
            {"value": v, "itemStyle": {"color": up_color if u else down_color}}
            for v, u in zip(vols, ups)
        ],
        label_opts=opts.LabelOpts(is_show=False),
        bar_width="60%",
    )

    sub_series: list[dict[str, Any]] = []
    for s in subs:
        c = Bar() if s.bar else Line()
        c.add_xaxis(dates)
        if s.bar:
            c.add_yaxis(
                s.name,
                [
                    {"value": v, "itemStyle": {"color": up_color if (v or 0) >= 0 else down_color}}
                    for v in s.values
                ],
                label_opts=opts.LabelOpts(is_show=False),
                bar_width="50%",
            )
        else:
            c.add_yaxis(
                s.name,
                s.values,
                is_symbol_show=False,
                linestyle_opts=opts.LineStyleOpts(width=1, color=s.color),
                label_opts=opts.LabelOpts(is_show=False),
            )
        sub_series.extend(_series_json(c))

    series: list[dict[str, Any]] = []
    for sj in _series_json(kchart):
        sj["xAxisIndex"] = 0
        sj["yAxisIndex"] = 0
        if isinstance(sj.get("data"), list):
            sj["data"] = _plain_values(sj["data"])
        series.append(sj)
    for sj in _series_json(vchart):
        sj["xAxisIndex"] = 1
        sj["yAxisIndex"] = 1
        series.append(sj)
    for sj in sub_series:
        sj["xAxisIndex"] = 2
        sj["yAxisIndex"] = 2
        if isinstance(sj.get("data"), list):
            sj["data"] = _plain_values(sj["data"])
        series.append(sj)

    grids: list[dict[str, Any]] = [
        {"left": 56, "right": 16, "top": 28, "height": "48%" if has_sub else "60%"},
        {
            "left": 56,
            "right": 16,
            "top": "64%" if has_sub else "74%",
            "height": "13%" if has_sub else "18%",
        },
    ]
    x_axes: list[dict[str, Any]] = [
        {
            "type": "category",
            "gridIndex": 0,
            "data": dates,
            "boundaryGap": True,
            "axisLabel": {"show": False},
            "axisTick": {"show": False},
        },
        {
            "type": "category",
            "gridIndex": 1,
            "data": dates,
            "boundaryGap": True,
            "axisTick": {"show": False},
        },
    ]
    y_axes: list[dict[str, Any]] = [
        {
            "gridIndex": 0,
            "scale": True,
            "axisLabel": {},
            "splitLine": {"lineStyle": {"color": axis_color}},
        },
        {"gridIndex": 1, "axisLabel": {"show": False}, "splitLine": {"show": False}},
    ]
    axis_idx = [0, 1]
    if has_sub:
        grids.append({"left": 56, "right": 16, "top": "81%", "height": "13%"})
        x_axes.append(
            {
                "type": "category",
                "gridIndex": 2,
                "data": dates,
                "boundaryGap": True,
                "axisTick": {"show": False},
            }
        )
        y_axes.append(
            {
                "gridIndex": 2,
                "scale": True,
                "axisLabel": {"fontSize": 10},
                "splitLine": {"show": False},
            }
        )
        axis_idx.append(2)

    legend_names = ["K线", *(m.name for m in mains), *(c.name for c in candles or [])]
    sub_legend = ",".join(s.name for s in subs if not s.bar)
    if has_sub and sub_legend != "":
        legend_names.append(sub_legend)

    start = max(0, 100 - (120 / n) * 100) if n > 0 else 0
    return {
        "backgroundColor": "transparent",
        "legend": {"data": legend_names, "top": 0, "textStyle": {"fontSize": 11}},
        "grid": grids,
        "xAxis": x_axes,
        "yAxis": y_axes,
        "dataZoom": [
            {"type": "inside", "xAxisIndex": axis_idx, "start": start, "end": 100},
            {
                "type": "slider",
                "xAxisIndex": axis_idx,
                "bottom": 4,
                "start": start,
                "end": 100,
                "height": 16,
            },
        ],
        "series": series,
    }
