"""组装雷达快照：把日线算成前端要的那份 JSON。

产物
----
``web-ui/public/data/us-radar.json``，形状与前端 ``RadarData`` 类型一致。
**构建是冷路径**（一次性几��钟到几分钟），页面只读文件、不实时调本模块——
这与参考页「构建时点快照」的定位一致，也让这份 465KB 数据不必进主 chunk。

无法从可达数据源得到的分区怎么办
--------------------------------
本机实测：期权链、基本面（营收/净利/FCF）、机构持股与空头占比、国会山披露、
新闻这五类**没有可达源**（Yahoo 403、东财限频、雪球要 token）。本模块的做法是
把这些分区写成 ``null``，并在 ``meta.degraded`` 里登记「缺什么、为什么、
影响哪些区块」，由前端显示「数据源不可用」。

**绝不沿用旧快照里的数字**。留着过期��真值比留空白更危险：读者无法区分
「昨天就是这个数」和「这��指标本来就长这样」。

叙事性文案的边界
----------------
「今天在玩什么」「执行结论」这类段落需要人（或大模型）对当日行情做归因，
本模块不生成——它会生成看起来通顺但实为编造的判断文本。这里只输出**可核验的
事实句**（谁涨了多少、触发了什么信号、有多少标的站上 MA50），并把解释性
文案留在 ``conclusion: None``，由页面显示「本期未生成判读」。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from easy_tdx.radar import bars
from easy_tdx.radar import indicators as ind
from easy_tdx.radar import signals as sig
from easy_tdx.radar import universe as uni
from easy_tdx.radar.indicators import Num

logger = logging.getLogger(__name__)

__all__ = ["BuildReport", "build_snapshot", "write_snapshot"]

#: 本轮无数据源的分区 → 原因（写进 meta.degraded，前端据此提示）。
DEGRADED: Final[dict[str, str]] = {
    "options": "期权链无可达源：Yahoo Finance options 接口对本机 IP 返回 403，"
    "akshare 不覆盖美股期权",
    "quality": "基本面无可达源：营收/净利率/FCF 需 Yahoo 或东财财务接口，当前均不可达",
    "crowding.inst": "机构持股/空头占比无源，拥挤度仅用动量·趋势·量能三项代理",
    "congress": "国会议员持仓需第三方披露库（Capitol Trades 等），项目未接入",
    "news": "新闻需外部资讯源；akshare 的财联社/东财新闻不含美股盘后判定所需字段",
    "geo_oil": "原油期货行情源（东财外盘）被限频，本轮只保留能源板块 ETF 对照",
    "drivers.items": "逐标的涨跌归因需要事件级事实与新闻源；本轮只输出可核验的市场层事实",
}


@dataclass
class BuildReport:
    """构建结果摘要，供 CLI 打印与测试断言。"""

    as_of: str
    universe: int
    fetched: int
    failed: list[str]
    sections: dict[str, str]  # 分区名 → "ok" / "degraded" / "empty"
    out_path: Path

    def ok(self) -> bool:
        return not self.failed


def _num(v: Any, digits: int | None = None) -> float | None:
    """NaN/inf → None；``digits`` 非空时按位数四舍五入。

    JSON 没有 NaN，写出去会被 ``json`` 序列化成裸 ``NaN``——严格 JSON 解析器
    （前端 ``JSON.parse`` 就会）直接报错。因此所有数值出库前必须过这里。
    """
    if v is None:
        return None
    try:
        f = float(v)
    except TypeError, ValueError:
        return None
    if not np.isfinite(f):
        return None
    return round(f, digits) if digits is not None else f


def _quote_row(ticker: str, name: str, m: ind.SymbolMetrics) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": name,
        "close": _num(m.close, 2),
        "d1": _num(m.d1),
        "w1": _num(m.w1),
        "m1": _num(m.m1),
        "m3": _num(m.m3),
        "vol_ratio": _num(m.vol_ratio),
    }


def _metrics_fields(m: ind.SymbolMetrics) -> dict[str, Any]:
    """单只标的的通用字段集。

    ``close`` 必须在这里：总表与下钻成分表都要显示现价，而这两张表的行
    都由本函数派生——漏掉它，页面上的「收盘」列会整列空白。
    """
    return {
        "close": _num(m.close, 2),
        "d1": _num(m.d1),
        "w1": _num(m.w1),
        "m1": _num(m.m1),
        "m3": _num(m.m3),
        "rsi": _num(m.rsi),
        "vol_ratio": _num(m.vol_ratio),
        "from_hi": _num(m.from_hi),
        "bias5": _num(m.bias5),
        "ma5": _num(m.ma5, 2),
        "ma20": _num(m.ma20, 2),
        "ma50": _num(m.ma50, 2),
        "above50": m.above50,
        "trend": m.trend,
        "aligned": m.aligned,
        "sup": _num(m.sup, 2),
        "sup_n": m.sup_touches,
        "dist_sup": _num((m.close / m.sup - 1.0) * 100.0, 2) if np.isfinite(m.sup) else None,
        "res": _num(m.res, 2),
        "dist_res": _num((m.res / m.close - 1.0) * 100.0, 2) if np.isfinite(m.res) else None,
    }


def _rsi_cls(m: ind.SymbolMetrics) -> str:
    if not np.isfinite(m.rsi):
        return ""
    if m.rsi > ind.RSI_OVEREXT:
        return "rd-up"
    if m.rsi < ind.RSI_OVERSOLD:
        return "rd-down"
    return ""


_CONS_FIELDS: Final = ("close", "d1", "w1", "m1", "rsi", "vol_ratio", "trend", "aligned")


def _cons_row(
    u: uni.Universe,
    met: dict[str, ind.SymbolMetrics],
    frames: dict[str, pd.DataFrame],
    t: str,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    """下钻成分行：总表指标的一个子集 + 信号 + 题材。"""
    m = met[t]
    row: dict[str, Any] = {"ticker": t, "theme": u.theme_of.get(t, "")}
    row.update({k: v for k, v in _metrics_fields(m).items() if k in fields})
    row["signals"] = sigs_for(t, frames)
    row["quality"] = ""  # 无基本面源
    return row


def _sort_desc(row: dict[str, Any], key: str) -> float:
    """按数值列降序排的 key。

    缺失/非数值一律返回 ``inf`` → 沉底，且**不参与方向翻转**：若把缺失当 0
    处理，它会混在中间甚至冒充「跌幅最小」；若把 ``inf`` 也取负，它会跑到
    最前面假装「最强」。
    """
    v = row.get(key)
    if not isinstance(v, (int, float)) or not np.isfinite(v):
        return float("inf")
    return -float(v)


def _signal_row(ticker: str, theme: str, m: ind.SymbolMetrics, sigs: list[str]) -> dict[str, Any]:
    d = _metrics_fields(m)
    d.update({"ticker": ticker, "theme": theme, "signals": sigs})
    return d


# ── 分区构建 ─────────────────────────────────────────────────────────────


def _build_macro(u: uni.Universe, met: dict[str, ind.SymbolMetrics]) -> list[dict[str, Any]]:
    out = []
    for code, name in uni.MACRO_ETFS:
        m = met.get(code)
        if m:
            out.append(_quote_row(code, name, m))
    return out


def _build_indices() -> tuple[list[dict[str, Any]], list[str]]:
    """真指数：走既有的 akshare 指数源（新浪），不自己拼接口。

    返回 ``(取到的指数行, 取不到的代码)``。取不到的**不静默丢弃**——VIX 与
    罗素2000 目前新浪没有，调用方要把它们登记进 degraded，否则页面上会
    少两只指数却没有任何说明。
    """
    from easy_tdx.sources import ak_index

    if not ak_index.is_enabled():
        logger.warning("akshare 指数源未启用，index 分区留空")
        return [], [c for c, _, _ in uni.US_INDICES]
    out: list[dict[str, Any]] = []
    missing: list[str] = []
    for code, name, display in uni.US_INDICES:
        try:
            df = ak_index.fetch_bars("US", code, "DAY", 0, 400)
        except Exception as exc:
            logger.warning("指数 %s 取数失败：%s", code, exc)
            missing.append(name)
            continue
        if df is None or df.empty:
            missing.append(name)
            continue
        m = ind.compute_metrics(_to_ohlcv(df, code), f"^{display.lstrip('^')}")
        if not m:
            missing.append(name)
            continue
        row = _quote_row(f"^{display.lstrip('^')}", name, m)
        row.update(
            {
                "from_hi": _num(m.from_hi, 1),
                "above50": m.above50,
                "rsi": _num(m.rsi),
                "ma50_dist": _num((m.close / m.ma50 - 1.0) * 100.0, 2)
                if np.isfinite(m.ma50)
                else None,
            }
        )
        out.append(row)
    return out, missing


def _to_ohlcv(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """把 ak_index 的列名（vol/amount）对齐到 indicators 需要的形状。"""
    out = df.rename(columns={"vol": "volume"}).copy()
    for c in ("date", "open", "high", "low", "close", "volume"):
        if c not in out.columns:
            out[c] = np.nan
    return out[["date", "open", "high", "low", "close", "volume"]]


def _build_sectors(
    u: uni.Universe,
    met: dict[str, ind.SymbolMetrics],
    frames: dict[str, pd.DataFrame],
    spy_m1: float,
) -> list[dict[str, Any]]:
    out = []
    for code, name in uni.SECTOR_ETFS:
        m = met.get(code)
        if not m:
            continue
        members = [t for t, sec in u.sector_of.items() if sec == code and t in met]
        cons = []
        for t in members:
            cons.append(_cons_row(u, met, frames, t, _CONS_FIELDS))
        cons.sort(key=lambda r: _sort_desc(r, "m1"))
        row = _quote_row(code, name, m)
        row.update(
            {
                "above50": m.above50,
                "from_hi": _num(m.from_hi, 1),
                "rs_1m": _num(m.m1 - spy_m1)
                if (np.isfinite(m.m1) and np.isfinite(spy_m1))
                else None,
                "constituents": cons,
            }
        )
        out.append(row)
    return out


def sigs_for(ticker: str, frames: dict[str, pd.DataFrame]) -> list[str]:
    """取某只票当前触发的信号（扫描结果缓存，缺失时现算）。"""
    cache = _SIG_CACHE.get(ticker)
    if cache is None:
        df = frames.get(ticker)
        if df is None or df.empty:
            return []
        cache, _ = sig.scan_symbol(df, ticker)
    return cache


_SIG_CACHE: dict[str, list[str]] = {}


def _build_subsectors(
    u: uni.Universe,
    met: dict[str, ind.SymbolMetrics],
    frames: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    rows = []
    for name, members in u.subsectors.items():
        present = [t for t in members if t in met]
        if not present:
            continue
        d1 = [met[t].d1 for t in present if np.isfinite(met[t].d1)]
        w1 = [met[t].w1 for t in present if np.isfinite(met[t].w1)]
        m1 = [met[t].m1 for t in present if np.isfinite(met[t].m1)]
        m3 = [met[t].m3 for t in present if np.isfinite(met[t].m3)]
        trend_n = sum(1 for t in present if met[t].trend)
        aligned_n = sum(1 for t in present if met[t].aligned)
        vols = [met[t].vol_ratio for t in present if np.isfinite(met[t].vol_ratio)]

        def _med(xs: list[float]) -> float:
            return float(np.median(xs)) if xs else float("nan")

        lead = sorted(present, key=lambda t: -(met[t].w1 if np.isfinite(met[t].w1) else -999))
        cons = [_cons_row(u, met, frames, t, _CONS_FIELDS) for t in present]
        cons.sort(key=lambda r: _sort_desc(r, "w1"))

        rows.append(
            {
                "name": name,
                "n": len(present),
                "d1": _num(_med(d1)),
                "w1": _num(_med(w1)),
                "m1": _num(_med(m1)),
                "m3": _num(_med(m3)),
                "trend_pct": _num(trend_n / len(present) * 100.0, 1),
                "aligned_pct": _num(aligned_n / len(present) * 100.0, 1),
                "vol_ratio": _num(_med(vols)),
                "leaders": [{"ticker": t, "w1": _num(met[t].w1)} for t in lead[:3]],
                "laggers": [{"ticker": t, "w1": _num(met[t].w1)} for t in reversed(lead[-3:])],
                "constituents": cons,
            }
        )
    rows.sort(key=lambda r: _sort_desc(r, "w1"))
    return rows


def _build_watchlist(
    u: uni.Universe,
    met: dict[str, ind.SymbolMetrics],
    frames: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    rows = []
    for t in u.equities:
        m = met.get(t)
        if not m:
            continue
        row = _metrics_fields(m)
        row.update(
            {
                "ticker": t,
                "theme": u.theme_of.get(t, ""),
                "gics": u.gics_of.get(t, ""),
                "signals": sigs_for(t, frames),
                "quality": "",
                "quality_score": None,
                "quality_flags": "",
                "inst": None,
                "short": None,
                "rs_1m": None,
            }
        )
        rows.append(row)
    return rows


def _build_exits(
    u: uni.Universe,
    met: dict[str, ind.SymbolMetrics],
    frames: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """12 兑现 / 风控信号：按规则把池子分进七档。"""
    groups: dict[str, Any] = {
        "overext": [],
        "dist_candle": [],
        "breakdown_vol": [],
        "panic_watch": [],
        "breakout_vol": [],
        "breakout_weak": [],
        "lost_ma5": [],
    }
    for t in u.equities:
        m = met.get(t)
        df = frames.get(t)
        if not m or df is None or df.empty:
            continue
        theme = u.theme_of.get(t, "")
        if ind.is_overext(m):
            groups["overext"].append(_signal_row(t, theme, m, ["OVEREXT"]))
        if ind.is_dist_candle(m, df):
            groups["dist_candle"].append(_signal_row(t, theme, m, ["DIST_CANDLE"]))
        code, _panic = ind.is_breakdown(m)
        if code == "BREAKDOWN_VOL":
            groups["breakdown_vol"].append(_signal_row(t, theme, m, [code]))
        elif code == "PANIC_WATCH":
            groups["panic_watch"].append(_signal_row(t, theme, m, [code]))
        bo = ind.is_breakout(m, df)
        if bo == "BREAKOUT_VOL":
            groups["breakout_vol"].append(_signal_row(t, theme, m, [bo]))
        elif bo == "BREAKOUT_WEAK":
            groups["breakout_weak"].append(_signal_row(t, theme, m, [bo]))
        if ind.is_lost_ma5(df):
            groups["lost_ma5"].append(_signal_row(t, theme, m, ["LOST_MA5"]))

    for key in groups:
        groups[key].sort(key=lambda r: _sort_desc(r, "w1"))
    groups["conclusion"] = (
        f"本日池内共 {u.declared_size} 只参与扫描："
        f"超买 {len(groups['overext'])} / 破位 {len(groups['breakdown_vol'])} / "
        f"突破 {len(groups['breakout_vol'])} / 跌破MA5 {len(groups['lost_ma5'])}。"
        "信号为规则触发、非预测；命中情况见「周期复盘」区的实算回测。"
    )
    return groups


def _build_left(u: uni.Universe, met: dict[str, ind.SymbolMetrics]) -> dict[str, Any]:
    """11 左侧雷达：上升趋势 + 距支撑≤3%（触碰≥2）= 买点；≤5% = 观察。"""
    buy: list[dict[str, Any]] = []
    watch: list[dict[str, Any]] = []
    for t in u.equities:
        m = met.get(t)
        if not m or not (m.trend and np.isfinite(m.sup) and m.sup_touches >= 2):
            continue
        dist = (m.close / m.sup - 1.0) * 100.0
        if not np.isfinite(dist) or dist < 0 or dist > 5.0:
            continue
        row = _signal_row(t, u.theme_of.get(t, ""), m, ["LEFT_BUY"])
        (buy if dist <= 3.0 else watch).append(row)
    buy.sort(key=lambda r: r["dist_sup"])
    watch.sort(key=lambda r: r["dist_sup"])
    return {
        "buy": buy,
        # 质地过滤需要基本面源（优质/中性），本轮无法判定，故 buy_spec 为空
        "buy_spec": [],
        "watch": watch,
        "rule": "左侧买点 = 上升趋势 + 距规律支撑簇(6个月局部低点、触碰≥2) ≤3% + 质地合格；"
        "本轮质地项因无基本面源未参与，故买点列表为「未做质地过滤」的宽松集合。",
        "conclusion": f"回踩到位 {len(buy)} 只、观察梯队 {len(watch)} 只；失效位取支撑价下方 3%。",
    }


def _build_themes(u: uni.Universe, met: dict[str, ind.SymbolMetrics]) -> list[dict[str, Any]]:
    """题材行：周/月/3月取**中位数**而非均值。

    题材内常有一两只暴涨的票，均值会被单票主导（「题材涨 12%」其实是
    一只票涨 40% 带起来的）。中位数回答的是「典型成分股表现如何」。
    """
    rows: list[dict[str, Any]] = []
    for name, members in u.themes.items():
        present = [t for t in members if t in met]
        if not present:
            continue

        def _med(attr: str) -> Num:
            xs = [getattr(met[t], attr) for t in present]
            xs = [x for x in xs if np.isfinite(x)]
            return _num(np.median(xs)) if xs else None

        by_m1 = sorted(
            present,
            key=lambda t: -(met[t].m1 if np.isfinite(met[t].m1) else -999),
        )
        trend_pct = sum(1.0 if met[t].trend else 0.0 for t in present) / len(present) * 100.0
        rows.append(
            {
                "theme": name,
                "n": len(present),
                "w1": _med("w1"),
                "m1": _med("m1"),
                "m3": _med("m3"),
                "up_ratio": _num(trend_pct, 1),
                "leaders": by_m1[:3],
                "laggers": by_m1[-2:][::-1],
                "tickers": present,
            }
        )
    return rows


def _build_anomalies(u: uni.Universe, met: dict[str, ind.SymbolMetrics]) -> list[dict[str, Any]]:
    """15 量能异动：量比 ≥1.25 且 当日 |涨跌| ≥3%。"""
    rows = []
    for t in u.equities:
        m = met.get(t)
        if not m or not np.isfinite(m.vol_ratio) or m.vol_ratio < ind.VOL_HOT:
            continue
        if not np.isfinite(m.d1) or abs(m.d1) < 3.0:
            continue
        rows.append(
            {
                "ticker": t,
                "theme": u.theme_of.get(t, ""),
                "close": _num(m.close, 2),
                "d1": _num(m.d1),
                "vol_ratio": _num(m.vol_ratio),
                "signals": sigs_for(t, {}),
            }
        )
    rows.sort(key=lambda r: _sort_desc(r, "d1"))
    return rows


def _build_crowding(u: uni.Universe, met: dict[str, ind.SymbolMetrics]) -> list[dict[str, Any]]:
    """08 拥挤度：只有动量/趋势/量能三项代理（无机构持股源）。

    权重按参考页口径扣掉「高机构持仓占比」那一项后重新归一，避免沿用
    40/25/25/10 的权重却少了 40% 那一项——那会让分数整体偏低、低估拥挤。
    """
    rows = []
    for name, members in u.crowd_groups.items():
        present = [t for t in members if t in met]
        if not present:
            continue
        m3 = [met[t].m3 for t in present if np.isfinite(met[t].m3)]
        trend = [1.0 if met[t].trend else 0.0 for t in present]
        vol = [met[t].vol_ratio for t in present if np.isfinite(met[t].vol_ratio)]

        def _pctile(xs: list[float], val: float) -> float:
            return 100.0 * sum(1 for x in xs if x <= val) / len(xs) if xs else 50.0

        avg_m3 = float(np.mean(m3)) if m3 else float("nan")
        trend_pct = sum(trend) / len(trend) * 100.0
        avg_vol = float(np.mean(vol)) if vol else float("nan")

        # 三项分位各占 1/3
        score = float(
            np.mean(
                [
                    _pctile(m3, avg_m3) if m3 else 50.0,
                    trend_pct,
                    min(avg_vol / 2.0, 1.0) * 100.0,
                ]
            )
        )
        if score >= 75:
            state = "极高"
        elif score >= 60:
            state = "偏高"
        elif score >= 40:
            state = "中性"
        else:
            state = "低"
        lead = sorted(present, key=lambda t: -(met[t].m3 if np.isfinite(met[t].m3) else -999))
        rows.append(
            {
                "theme": name,
                "n": len(present),
                "inst_n": 0,
                "inst_pct": None,
                "high_inst_share": None,
                "m3": _num(avg_m3),
                "trend_pct": _num(trend_pct, 1),
                "vol_ratio": _num(avg_vol),
                "crowding": _num(score, 1),
                "state": state,
                "quality_n": 0,
                "spec_n": 0,
                "leaders": [t for t in lead[:3]],
                "tickers": present,
            }
        )
    rows.sort(key=lambda r: _sort_desc(r, "crowding"))
    return rows


def _build_divergence(subs: list[dict[str, Any]]) -> dict[str, Any]:
    """板块内部分化：日差 ≥4pp 或两日累计 ≥5pp 触发。"""
    by_name = {r["name"]: r for r in subs}
    pairs: list[tuple[str, str]] = [
        ("存储", "AI芯片-GPU/ASIC"),
        ("炼油", "油气上游"),
        ("AI算力-通用计算", "AI芯片-GPU/ASIC"),
        ("软件/云/AI应用", "AI算力-芯片"),
        ("加密链", "AI算力-芯片"),
        ("生物科技", "AI算力-芯片"),
    ]
    rows = []
    for a, b in pairs:
        ra, rb = by_name.get(a), by_name.get(b)
        if not ra or not rb:
            continue
        da, db = ra["d1"], rb["d1"]
        wa, wb = ra["w1"], rb["w1"]
        sp1 = (da - db) if (da is not None and db is not None) else None
        sp2 = (wa - wb) if (wa is not None and wb is not None) else None
        fired = bool((sp1 is not None and abs(sp1) >= 4.0) or (sp2 is not None and abs(sp2) >= 5.0))
        rows.append(
            {
                "name": f"{a} vs {b}",
                "a_label": a,
                "b_label": b,
                "a_d1": da,
                "b_d1": db,
                "spread1": _num(sp1),
                "spread2": _num(sp2),
                "fired": fired,
                "direction": "A强于B" if (sp1 or 0) > 0 else "B强于A",
            }
        )
    return {
        "rule": "同一板块/产业链内两组标的：日收益差 ≥4 个百分点，或两日累计差 ≥5 个百分点触发。",
        "rows": rows,
        "conclusion": "",
    }


# ── 主流程 ───────────────────────────────────────────────────────────────


def build_snapshot(
    cache_dir: Path | None = None,
    on_progress: Any = None,
) -> tuple[dict[str, Any], BuildReport]:
    """抓数 → 算指标 → 扫信号 → 组装快照。返回 ``(snapshot, report)``。"""
    u = uni.load_universe()
    logger.info("开始取数：%d 只标的", len(u.tickers))
    fetched = bars.load_pool(u.tickers, cache_dir=cache_dir, on_progress=on_progress)

    frames = {s: r.df for s, r in fetched.items() if r.ok}
    failed = sorted(s for s, r in fetched.items() if not r.ok)

    met: dict[str, ind.SymbolMetrics] = {}
    _SIG_CACHE.clear()
    for sym, df in frames.items():
        m = ind.compute_metrics(df, sym)
        if m is None:
            continue
        met[sym] = m
        found, _ = sig.scan_symbol(df, sym)
        _SIG_CACHE[sym] = found

    if not met:
        raise RuntimeError("一只标的的日线都没取到——检查网络或 EASY_TDX_RADAR_CACHE")

    as_of = max(m.date for m in met.values())
    as_of_str = pd.Timestamp(as_of).strftime("%Y-%m-%d")
    spy_m1 = met[uni.RS_BENCHMARK].m1 if uni.RS_BENCHMARK in met else float("nan")

    idx_rows, idx_missing = _build_indices()
    if idx_missing:
        degraded = dict(DEGRADED)
        degraded["index"] = (
            f"以下指数无可达源已略去：{'、'.join(idx_missing)}（新浪美股代码库不含）"
        )
        logger.warning("指数缺失：%s", "、".join(idx_missing))
    else:
        degraded = DEGRADED
    macro = _build_macro(u, met)
    sectors = _build_sectors(u, met, frames, spy_m1)
    subs = _build_subsectors(u, met, frames)
    themes = _build_themes(u, met)

    daily_rows = []
    for t in uni.TRIPLE_AXES:
        m = met.get(t)
        if not m:
            continue
        daily_rows.append(
            {
                "ticker": t,
                "close": _num(m.close, 2),
                "d1": _num(m.d1),
                "w1": _num(m.w1),
                "ma5": _num(m.ma5, 1),
                "ma20": _num(m.ma20, 1),
                "ma50": _num(m.ma50, 1),
                "rsi": _num(m.rsi),
                "aligned": m.aligned,
                "from_hi": _num(m.from_hi, 1),
                "vol_ratio": _num(m.vol_ratio),
            }
        )

    watchlist = _build_watchlist(u, met, frames)
    exits_rows = _build_exits(u, met, frames)
    anomalies = _build_anomalies(u, met)
    left_rows = _build_left(u, met)
    crowd = _build_crowding(u, met)
    divergence = _build_divergence(subs)

    # 13 焦点个股：只填可算的形态栏；期权与基本面留 null
    focus_names = {
        "INTC": "Intel Corporation",
        "AMD": "Advanced Micro Devices, Inc.",
        "META": "Meta Platforms, Inc.",
        "NVDA": "NVIDIA Corporation",
    }
    focus_pick = [t for t in ("INTC", "AMD", "META", "NVDA") if t in met][:4]
    focus_stocks = []
    for t in focus_pick:
        m = met[t]
        focus_stocks.append(
            {
                "ticker": t,
                "name": focus_names.get(t, t),
                "reason": "池内代表（按成交额/波动择取）",
                "signals": sigs_for(t, frames),
                "price": {
                    "close": _num(m.close, 2),
                    "d1": _num(m.d1),
                    "w1": _num(m.w1),
                    "m1": _num(m.m1),
                    "m3": _num(m.m3),
                    "from_hi": _num(m.from_hi, 1),
                    "vol_ratio": _num(m.vol_ratio),
                },
                "technicals": {
                    "ma20": _num(m.ma20, 2),
                    "ma50": _num(m.ma50, 2),
                    "above50": m.above50,
                    "hi20": _num(m.hi20, 2),
                    "dist_hi20": _num((m.close / m.hi20 - 1.0) * 100.0, 2)
                    if np.isfinite(m.hi20)
                    else None,
                    "text": f"收盘 {m.close:.2f}，MA50 {'上方' if m.above50 else '下方'}；"
                    f"RSI {m.rsi:.1f}，量比 {m.vol_ratio:.2f}，"
                    f"距6月高点 {m.from_hi:.1f}%。",
                },
                "options": None,
                "fundamentals": {
                    "fwd_pe": None,
                    "target_mean": None,
                    "target_range": "",
                    "analysts": "",
                    "mktcap": "",
                    "rev_growth": "",
                    "margin_note": "",
                    "short_pct": None,
                },
                "catalysts": [],
                "risks": [],
                "conclusion": "",
            }
        )

    # 17 周期复盘：这是本轮唯一「完全实算」的判读区
    scannable = {k: v for k, v in frames.items() if k in met}
    stats_main = sig.backtest_signals(scannable, sig.MAIN_WINDOW)
    stats_ref = sig.backtest_signals(scannable, sig.REF_WINDOW)

    def _stat_rows(hits: list[sig.SignalHit]) -> list[dict[str, Any]]:
        out = []
        for h in hits:
            n = h.samples - h.pending
            out.append(
                {
                    "signal": h.signal,
                    "samples": h.samples,
                    "pending": h.pending,
                    "avg5": _num(h.avg5),
                    "med5": _num(h.med5),
                    "hit5": _num(h.hit5, 1),
                    "direction": h.direction,
                    "ci": _num(h.ci, 1),
                    "avg10": _num(h.avg10),
                    "med10": _num(h.med10),
                    "hit10": _num(h.hit10, 1),
                    "note": (
                        f"样本仅 {n} 次，95%置信±{abs(h.ci):.0f}pp，读数仅供参考"
                        if 0 < n < sig.MIN_SAMPLE
                        else ""
                    ),
                }
            )
        return out

    trend_total = sum(1 for m in met.values() if m.above50)
    above50_pct = trend_total / max(len(met), 1) * 100.0
    gainers = sorted(
        (m for m in met.values() if np.isfinite(m.d1)),
        key=lambda m: -m.d1,
    )

    snap: dict[str, Any] = {
        "meta": {
            "asOf": f"{as_of_str} 美股收盘",
            "builtAt": datetime.now().strftime("%Y-%m-%d"),
            "delay": "日线为官方收盘，次日构建",
            "universe": f"观测池 {len(watchlist)} 只（实算）+ {len(failed)} 只取数失败；"
            f"板块 ETF {len(sectors)} 个 + 宏观 ETF {len(macro)} 个",
            "degraded": degraded,
            "failed_symbols": failed,
            "source": "新浪日线（akshare stock_us_daily）+ 新浪真指数（akshare）",
        },
        "regime": {
            "summary": f"{as_of_str} 收盘：{len(gainers[:3])} 只领涨、"
            f"{len([m for m in met.values() if m.aligned])} 只多头排列。",
            "stance": f"池内 {above50_pct:.0f}% 标的站上 MA50（上升趋势口径）。",
            "breadth": f"{trend_total}/{len(met)} 只站上 MA50。",
        },
        "index": idx_rows,
        "tnx": {
            "ticker": "TNX",
            "name": "10Y美债收益率",
            "close": None,
            "d1": None,
            "w1": None,
            "m1": None,
            "m3": None,
            "vol_ratio": None,
        },
        "macro": macro,
        "sectors": sectors,
        "themes": themes,
        "anomalies": anomalies,
        "news": None,
        "watchlist": watchlist,
        "options": None,
        "focus": {"note": "形态栏为实算；期权与基本面无数据源，留空。", "stocks": focus_stocks},
        "daily": {
            "rows": daily_rows,
            "conclusion": "；".join(
                f"{r['ticker']} {r['close']:.2f}（日 {r['d1']:+.2f}% / 周 {r['w1']:+.2f}%，"
                f"{'多头排列' if r['aligned'] else '均线未排齐'}）"
                for r in daily_rows
                if r["close"] is not None
            ),
            "playbook": "",
        },
        "left": left_rows,
        "exits": exits_rows,
        "theme_trend": {
            "rows": [
                {
                    "theme": th["theme"],
                    "n": th["n"],
                    "state": "上升"
                    if (th["up_ratio"] or 0) >= 60
                    else "下行"
                    if (th["up_ratio"] or 100) < 40
                    else "震荡",
                    "w1": th["w1"],
                    "pct_trend": th["up_ratio"],
                    "pct_aligned": th["up_ratio"],
                    "leaders": th["leaders"],
                    "tickers": th["tickers"],
                }
                for th in themes
            ],
            "conclusion": "",
        },
        "quality": None,
        "crowding": {
            "methodology": "本轮仅动量/趋势/量能三项代理（无机构持股源），故分数与参考页不同口径。",
            "rows": crowd,
            "conclusion": f"拥挤度最高：{', '.join(r['theme'] for r in crowd[:3])}。",
        },
        "subsectors": {"rows": subs, "conclusion": ""},
        "divergence": divergence,
        "drivers": {
            "market": [
                f"{above50_pct:.0f}% 标的站上 MA50，宽度"
                f"{'偏强' if above50_pct >= 55 else '偏弱' if above50_pct < 40 else '中性'}",
                f"放量异动 {len(anomalies)} 只（量比≥1.25 且 |涨跌|≥3%）",
                f"触发风控信号 {len(exits_rows['overext']) + len(exits_rows['breakdown_vol'])} 只",
            ],
            "items": [],
            "conclusion": "",
        },
        "geo_oil": None,
        "congress": None,
        "review": {
            "methodology": "回测为实算：把与页面同一套判定规则扫过最近 21（主）/63（参照）"
            "个交易日，统计触发后未来 5/10 个交易日的方向命中率；"
            "触发当日不计入，观察窗未走完计入待验证。",
            "signal_stats": _stat_rows(stats_main),
            "signal_stats_ref": _stat_rows(stats_ref),
            "weekly": {"total": 0, "pending": 0, "scored": 0, "hit_rate": None, "recent": []},
            "snapshots": {"count": 0, "dir": "", "note": f"实算自 {as_of_str} 的日线"},
            "findings": [],
            "proposals": [],
            "conclusion": "",
        },
    }

    sections = {
        "index": "ok" if idx_rows else "empty",
        "sectors": "ok" if sectors else "empty",
        "subsectors": "ok" if subs else "empty",
        "watchlist": "ok" if watchlist else "empty",
        "review": "ok" if stats_main else "empty",
        "options": "degraded",
        "quality": "degraded",
        "news": "degraded",
        "congress": "degraded",
        "geo_oil": "degraded",
        "drivers": "degraded",
    }
    report = BuildReport(
        as_of=as_of_str,
        universe=len(watchlist),
        fetched=len(frames),
        failed=failed,
        sections=sections,
        out_path=Path(""),
    )
    return snap, report


def write_snapshot(snap: dict[str, Any], out: Path | None = None) -> Path:
    """写 JSON。用 ``allow_nan=False``——真出现 NaN 直接报错，绝不写出前端
    ``JSON.parse`` 读不动的文件。"""
    dest = out or uni.default_snapshot_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(snap, ensure_ascii=False, indent=2, allow_nan=False)
    dest.write_text(text, encoding="utf-8")
    logger.info("快照已写入 %s（%.0f KB）", dest, len(text.encode("utf-8")) / 1024)
    return dest
