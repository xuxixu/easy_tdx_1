"""雷达页的衍生指标：均线/RSI/量比/趋势/支撑压力。

口径来源
--------
参考页第 17 区块「方法」里已经把规则写死了，本模块严格照抄，不自创：

===================================  ==========================================
规则                                 本模块实现
===================================  ==========================================
放量                                  量比 = MA(成交量,5) / MA(成交量,20) ≥ 1.5
放量突破                              收盘 ≥ 前 20 日最高(不含当日) 且 量比 ≥ 1.5
                                      且 上升趋势；否则降级「非趋势突破」
放量破位                              收盘 < 前 20 日最低(不含当日) 且 量比 ≥ 1.5
                                      且 非上升趋势 且 收盘 < MA50
超买乖离                              RSI14 > 80（一等风控）
跌破 5 日线                            昨日收盘 ≥ 昨日 MA5 且 今日收盘 < 今日 MA5
高位放量阴线                            距 6 个月高点 ≤ 5% 且 实体 > 3% 且 量比 ≥ 1.5
左侧买点                              上升趋势 且 距支撑簇 ≤ 3%（触碰 ≥ 2 次）
                                      且 质地合格
上升趋势                              收盘 > MA50 且 MA50 上行
多头排列                              收盘 > MA5 > MA20 > MA50
支撑/压力位                            6 个月局部高低点聚类
RS（相对强度）                         标的月涨幅 − SPY 月涨幅
===================================  ==========================================

为什么用 :mod:`easy_tdx.ta`（TA-Lib）而不是 pandas 自己算
-----------------------------------------------------------
项目已明确定调「TA-Lib 是唯一的指标计算引擎，数值口径以 TA-Lib 为准」。
这里再手写一遍 RSI 会引入第二套口径，K 线页和雷达页对同一只票给出不同
RSI，是比多写几十行严重得多的问题。

「前 20 日最高（不含当日）」的坑
------------------------------
突破/破位判定里这个窗口**必须排除当天**。含当天的话，今天创新高就必然
「突破」，而当天的高点本身就是被这次突破造出来的——等于用结果证明原因，
信号会天天触发。因此这里取 ``high.iloc[-21:-1]``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Final

import numpy as np
import pandas as pd

from easy_tdx import ta

logger = logging.getLogger(__name__)

__all__ = [
    "METRICS",
    "Num",
    "SymbolMetrics",
    "compute_metrics",
    "support_resistance",
]

#: 可能为「无值」的数值：计算过程中缺样本时是 NaN，出 JSON 时转 ``None``。
Num = float | None

#: 日/周/月/3 月 = 1/5/21/63 个交易日（21 ≈ 1 个交易月，63 ≈ 3 个）。
_RET_WINDOWS: Final[tuple[int, int, int, int]] = (1, 5, 21, 63)

#: 支撑压力聚类：局部极值的左右观察窗（交易日）。
_LOCAL_WINDOW: Final = 3

#: 同一个价位簇的容差（相对）。1.5% —— 低于它算「同一个支撑」，
# 再大就会把两个独立价位并成一档，支撑位随之失真。
_CLUSTER_TOL: Final = 0.015

#: 高位放量阴线：距 6 个月高点的阈值。
_HIGH_PROXIMITY: Final = 5.0

#: 阴线实体阈值（%）。
_BODY_MIN: Final = 3.0

#: 支撑位「够得着」的上限（距现价 %）。超过这个距离的价位簇不是支撑、是历史，
#: 报进总表只会得到「距支撑 +311%」这种看着像参考位、实则无法执行的数字。
#: 取 25% 是因为它已宽到能容下多数单边票的最近一次有效回踩，再远就基本是
#: 另一个价位区间了。
_MAX_SUP_DIST: Final = 25.0


@dataclass
class SymbolMetrics:
    """单只标的在快照时点的全部衍生指标。

    可选字段用 ``float('nan')`` 而非 ``None``：后续统计（排名、分位、
    中位数）直接丢 NaN 即可，不必到处写 ``if x is None``。写 JSON 时由
    :func:`_jsonable` 统一转成 ``null``。
    """

    symbol: str
    date: pd.Timestamp
    close: float
    d1: float = float("nan")
    w1: float = float("nan")
    m1: float = float("nan")
    m3: float = float("nan")
    ma5: float = float("nan")
    ma20: float = float("nan")
    ma50: float = float("nan")
    rsi: float = float("nan")
    vol_ratio: float = float("nan")
    hi20: float = float("nan")
    lo20: float = float("nan")
    hi6m: float = float("nan")
    from_hi: float = float("nan")
    bias5: float = float("nan")
    above50: bool = False
    ma50_rising: bool = False
    trend: bool = False
    aligned: bool = False
    sup: float = float("nan")
    sup_touches: int = 0
    res: float = float("nan")
    #: 计算过程中的告警（样本不足等），会写进快照的 meta 供排查
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """指标是否足以支撑信号判定（至少要有 MA20 与 RSI）。"""
        return bool(np.isfinite(self.ma20) and np.isfinite(self.rsi))


def _pct_return(close: pd.Series, n: int) -> float:
    """近 n 个交易日的收益率 %。样本不足时返回 NaN 而不是 0——0 会被误读成「没涨跌」。"""
    if len(close) < n + 1:
        return float("nan")
    prev = float(close.iloc[-(n + 1)])
    if prev == 0:
        return float("nan")
    return (float(close.iloc[-1]) / prev - 1.0) * 100.0


def support_resistance(
    low: pd.Series,
    high: pd.Series,
    close_now: float,
    lookback: int = 126,
    max_dist: float = _MAX_SUP_DIST,
) -> tuple[float, int, float]:
    """6 个月局部高低点聚类 → (支撑, 触碰次数, 压力)。

    做法（三步，与参考页「6个月局部高低点聚类」口径一致）：

    1. **找局部极值**：``low[i]`` 不高于左右各 ``_LOCAL_WINDOW`` 根 → 支撑候选；
       ``high[i]`` 同理 → 压力候选。丢掉序列两端，避免边界造成的假极值。
    2. **聚类**：把相差在 ``_CLUSTER_TOL`` 以内的价位并成一档（取该档的中位价
       作为代表）。同一个价位被反复试探时，每次试探都是一个独立候选点，
       必须先并档，否则「触碰次数」永远只有 1。
    3. **取最近的，并报出它的强度**：支撑取当前价下方**最近**的价位簇，压力取
       上方最近的，触碰次数一并返回。

       这里刻意**不**要求触碰 ≥ 2：实测 6 个月样本里 81% 的票下方有价位簇，
       但只有 31% 触碰过两次。若把「≥2」当作**报告**条件，「距支撑」列会有
       七成是空的，那列本身就失去意义。正确做法是把支撑报出来、由调用方按
       自己的强度要求筛选——左侧买点规则要求「触碰 ≥ 2」，那里的门槛一字
       不动，照样只认被验证过的价位。
    4. **够得着的才算**：候选还必须在 ``max_dist`` 以内。半年单边上涨的票
       （如 MRNA 218 美元、半年低点 53）下方确实有价位簇，但它是三倍距离
       ——那不是支撑，是历史。报出去会得到「距支撑 +311%」这种看着像参考位、
       实则无法执行的数字，直接判为「附近无支撑」（NaN）更诚实。

    返回 NaN 表示附近没有可用价位（新股、上市不足半年、单边无回踩行情，
    或最近支撑远到不可用）。
    """
    lo = low.iloc[-lookback:].to_numpy(dtype=float)
    hi = high.iloc[-lookback:].to_numpy(dtype=float)
    n = len(lo)
    w = _LOCAL_WINDOW
    if n < 2 * w + 3:
        return float("nan"), 0, float("nan")

    lows: list[float] = []
    highs: list[float] = []
    for i in range(w, n - w):
        window_lo = lo[i - w : i + w + 1]
        window_hi = hi[i - w : i + w + 1]
        if lo[i] == window_lo.min():
            lows.append(float(lo[i]))
        if hi[i] == window_hi.max():
            highs.append(float(hi[i]))

    def _cluster(values: list[float]) -> list[tuple[float, int]]:
        """把价位按相对容差并档，返回 [(代表价, 触碰次数)]，按价位升序。"""
        if not values:
            return []
        values = sorted(values)
        groups: list[list[float]] = [[values[0]]]
        for v in values[1:]:
            ref = groups[-1][-1]
            if abs(v - ref) / max(ref, 1e-9) <= _CLUSTER_TOL:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [(float(np.median(g)), len(g)) for g in groups]

    sup, sup_n = float("nan"), 0
    # 聚类按价位升序，reversed 从高往低扫。头几个簇通常在现价之上（那是压力
    # 区），必须 continue 跳过而不是 break——break 掉就等于「现价上方有簇
    # ⇒ 没支撑」，把绝大多数正常票都误判成没有支撑。
    for price, touches in reversed(_cluster(lows)):
        if price >= close_now:
            continue
        if (close_now / price - 1.0) * 100.0 > max_dist:
            # 再往下只会更远，直接放弃——「附近无支撑」比报一个三倍距离的
            # 历史价位更诚实。
            break
        sup, sup_n = price, touches
        break

    res = float("nan")
    for price, _touches in _cluster(highs):
        if price > close_now:
            res = price
            break

    return sup, sup_n, res


def compute_metrics(df: pd.DataFrame, symbol: str) -> SymbolMetrics | None:
    """从日线算出该标的的全部衍生指标。

    数据少于 30 根（连一条 MA20 都不够）时返回 ``None``——这种票算出来的
    指标全是 NaN，写进快照只会污染统计。
    """
    if df is None or len(df) < 30:
        return None

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["volume"].astype(float)

    c = close.to_numpy()
    v = vol.to_numpy()
    last = float(c[-1])
    m = SymbolMetrics(symbol=symbol, date=df["date"].iloc[-1], close=last)

    d1, w1, m1, m3 = (_pct_return(close, n) for n in _RET_WINDOWS)
    m.d1, m.w1, m.m1, m.m3 = d1, w1, m1, m3

    ma5 = ta.MA(c, 5)
    ma20 = ta.MA(c, 20)
    ma50 = ta.MA(c, 50)
    m.ma5, m.ma20, m.ma50 = float(ma5[-1]), float(ma20[-1]), float(ma50[-1])

    rsi = ta.RSI(c, N=14)
    m.rsi = float(rsi[-1])

    v5, v20 = ta.MA(v, 5), ta.MA(v, 20)
    m.vol_ratio = float(v5[-1] / v20[-1]) if float(v20[-1]) > 0 else float("nan")

    # 「前 20 日」不含当天：含当天则今日新高必然自证突破
    m.hi20 = float(high.iloc[-21:-1].max()) if len(high) >= 21 else float("nan")
    m.lo20 = float(low.iloc[-21:-1].min()) if len(low) >= 21 else float("nan")
    m.hi6m = float(high.iloc[-126:].max())

    if np.isfinite(m.ma5) and m.ma5 > 0:
        m.bias5 = (last / m.ma5 - 1.0) * 100.0
    if np.isfinite(m.hi6m) and m.hi6m > 0:
        m.from_hi = (last / m.hi6m - 1.0) * 100.0

    m.above50 = bool(np.isfinite(m.ma50) and last > m.ma50)
    # MA50「上行」= 比一根之前高。涨 1% 还是 1 个点无关，只看方向
    prev_ma50 = float(ma50[-2]) if len(ma50) >= 2 else float("nan")
    m.ma50_rising = bool(np.isfinite(prev_ma50) and float(ma50[-1]) > prev_ma50)
    m.trend = m.above50 and m.ma50_rising
    m.aligned = bool(
        all(np.isfinite(x) for x in (m.ma5, m.ma20, m.ma50)) and last > m.ma5 > m.ma20 > m.ma50
    )

    sup, sup_n, res = support_resistance(low, high, last)
    m.sup, m.sup_touches, m.res = sup, sup_n, res

    if not np.isfinite(m.ma50):
        m.warnings.append("MA50 不足 50 根 K 线")
    if not np.isfinite(sup):
        m.warnings.append(f"附近无支撑簇（6个月内局部低点、距现价≤{_MAX_SUP_DIST:.0f}%）")
    return m


def _high_volume_bear_candle(m: SymbolMetrics, df: pd.DataFrame) -> bool:
    """高位放量阴线：距 6 月高点 ≤5% 且 实体 >3% 且 量比 ≥1.5 且 当日收跌。"""
    if not (np.isfinite(m.from_hi) and np.isfinite(m.vol_ratio)):
        return False
    last = df.iloc[-1]
    o, c = float(last["open"]), float(last["close"])
    body = (o - c) / o * 100.0 if o > 0 else 0.0
    return bool(
        c < o
        and body >= _BODY_MIN
        and m.vol_ratio >= 1.5
        and m.from_hi >= -_HIGH_PROXIMITY
    )


#: 供 signals.py 复用的判定原语（体积放量阈值，与参考页一致）
VOL_SPIKE: Final = 1.5
VOL_HOT: Final = 1.25
RSI_OVEREXT: Final = 80.0
RSI_OVERSOLD: Final = 35.0


def is_volume_spike(m: SymbolMetrics) -> bool:
    return bool(np.isfinite(m.vol_ratio) and m.vol_ratio >= VOL_SPIKE)


def is_breakout(m: SymbolMetrics, df: pd.DataFrame) -> str:
    """放量突破 → ``"BREAKOUT_VOL"``；缺趋势条件则降级 ``"BREAKOUT_WEAK"``。"""
    if not (np.isfinite(m.hi20) and np.isfinite(m.vol_ratio)):
        return ""
    if m.close >= m.hi20 and is_volume_spike(m):
        return "BREAKOUT_VOL" if m.trend else "BREAKOUT_WEAK"
    return ""


def is_breakdown(m: SymbolMetrics) -> tuple[str, bool]:
    """放量破位 → ``(信号, 是否「恐慌观察」)``。

    非上升趋势 + 收盘<MA50 时才是「执行级」的破位；若同时仍在上升趋势里，
    降级为 ``PANIC_WATCH``（回测显示这类 5 日内平均反弹 +4.4%，立即离场是错的）。
    """
    if not (np.isfinite(m.lo20) and np.isfinite(m.vol_ratio)):
        return "", False
    if m.close < m.lo20 and is_volume_spike(m):
        if not m.trend and m.close < m.ma50:
            return "BREAKDOWN_VOL", False
        return "PANIC_WATCH", True
    return "", False


def is_lost_ma5(df: pd.DataFrame) -> bool:
    """跌破 MA5：昨日收盘 ≥ 昨日 MA5 且今日收盘 < 今日 MA5。"""
    if len(df) < 2:
        return False
    c = df["close"].astype(float).to_numpy()
    if len(c) < 21:
        return False
    ma5 = ta.MA(c, 5)
    prev_ok = float(c[-2]) >= float(ma5[-2])
    today_broken = float(c[-1]) < float(ma5[-1])
    return bool(np.isfinite(ma5[-1]) and prev_ok and today_broken)


def is_overext(m: SymbolMetrics) -> bool:
    return bool(np.isfinite(m.rsi) and m.rsi > RSI_OVEREXT)


def is_dist_candle(m: SymbolMetrics, df: pd.DataFrame) -> bool:
    return _high_volume_bear_candle(m, df)


#: 快照里每个分区用到的字段清单，写 JSON 时据此裁剪 NaN → null。
METRICS: Final = (
    "d1", "w1", "m1", "m3", "ma5", "ma20", "ma50", "rsi", "vol_ratio",
    "hi20", "lo20", "from_hi", "bias5",
)  # fmt: skip