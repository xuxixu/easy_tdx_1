"""信号扫描与历史回测：把日线变成「今天有哪些信号」和「这些信号历史上准不准」。

两块内容的关系
--------------
:func:`scan_symbol` 在最新一根 K 线上判定信号 → 喂给页面的 11/12/15 区块；
:func:`backtest_signals` 把同一套判定规则**扫过最近 N 根历史 K 线**，统计
未来 5/10 个交易日的方向命中率 → 喂给第 17 区块。

第二块是这一整包的价值所在：参考页那一版的命中率是写死在快照里的断言值，
无法验证也随行情失效；这里是从真实日线算出来的，改了判定规则数字就会变，
规则有没有效随时可查。

回测口径（与参考页一致，避免两边不可比）
----------------------------------------
* 主窗口 = 近 1 个月（约 21 个交易日内触发的信号）
* 参照窗口 = 滚动 3 个月（约 63 个交易日）
* 触发的当天**不计入**（要用 T+1 起的收益，避免用到当日收盘价自证）
* 观察窗未走完（未来 5/10 日还没有）计入 ``pending``，不算命中率
* 样本 < 5 次的命中率标「样本不足」，读数仅供参考
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from easy_tdx import ta

from . import indicators as ind

logger = logging.getLogger(__name__)

__all__ = [
    "SignalHit",
    "backtest_signals",
    "scan_symbol",
]

#: 主窗口 / 参照窗口长度（交易日）。
MAIN_WINDOW: Final = 21
REF_WINDOW: Final = 63

#: 未来收益观察窗。
FWD_SHORT: Final = 5
FWD_LONG: Final = 10

#: 样本量低于此值，命中率只作参考。
MIN_SAMPLE: Final = 5

#: 命中率分档阈值（10 日优先，缺失则退回 5 日）。
_HIT_GOOD: Final = 55.0
_HIT_FLAT: Final = 50.0
_HIT_BAD: Final = 45.0


@dataclass
class SignalHit:
    """一个信号的回测汇总。"""

    signal: str
    samples: int = 0
    pending: int = 0
    avg5: float = float("nan")
    med5: float = float("nan")
    hit5: float = float("nan")
    avg10: float = float("nan")
    med10: float = float("nan")
    hit10: float = float("nan")
    ci: float = float("nan")

    @property
    def direction(self) -> str:
        """该信号是看多还是看空——命中率必须按方向折算，否则「看空信号跌了」
        会被算成「没命中」。"""
        return _DIRECTION.get(self.signal, "看多")


_DIRECTION: Final[dict[str, str]] = {
    "LEFT_BUY": "看多",
    "BREAKOUT_VOL": "看多",
    "BREAKOUT_WEAK": "看多",
    "LOST_MA5": "看空",
    "DIST_CANDLE": "看空",
    "BREAKDOWN_VOL": "看空",
    "PANIC_WATCH": "看空",
    "OVEREXT": "看空",
}


def _fwd_returns(c: np.ndarray, idx: int, n: int) -> float | None:
    """``idx`` 之后第 ``n`` 根的收益率 %。观察窗没走完返回 None。"""
    j = idx + n
    if j >= len(c):
        return None
    base = c[idx]
    if base <= 0:
        return None
    return float((c[j] / base - 1.0) * 100.0)


def _classify_at(
    c: np.ndarray,
    h: np.ndarray,
    low: np.ndarray,
    v: np.ndarray,
    ma5: np.ndarray,
    ma20: np.ndarray,
    ma50: np.ndarray,
    i: int,
) -> list[str]:
    """在第 ``i`` 根 K 线上判定触发了哪些信号。

    这里**不复用** :func:`easy_tdx.radar.indicators.compute_metrics`——它是为
    「最新一根」设计的整体视图；回测要逐根重算滚动状态，直接复用会把未来
    信息（用全序列算出的 MA/RSI）泄漏进历史判定里。逐根只用 ``[:i+1]`` 切片。
    """
    out: list[str] = []
    if i < 50:
        return out

    close = float(c[i])
    op = float(c[i - 1])
    prev_ma5 = float(ma5[i - 1])
    ma5i, ma20i, ma50i = float(ma5[i]), float(ma20[i]), float(ma50[i])
    ma50_prev = float(ma50[i - 1])
    if not all(np.isfinite(x) for x in (ma5i, ma20i, ma50i, ma50_prev, prev_ma5)):
        return out

    vol5 = float(np.mean(v[i - 4 : i + 1]))
    vol20 = float(np.mean(v[i - 19 : i + 1]))
    vol_ratio = vol5 / vol20 if vol20 > 0 else float("nan")

    trend = close > ma50i and ma50i > ma50_prev
    hi20 = float(np.max(h[i - 20 : i]))
    lo20 = float(np.min(low[i - 20 : i]))
    hi6m = float(np.max(h[max(0, i - 125) : i + 1]))

    # 放量突破 / 非趋势突破
    if np.isfinite(vol_ratio) and vol_ratio >= ind.VOL_SPIKE and close >= hi20:
        out.append("BREAKOUT_VOL" if trend else "BREAKOUT_WEAK")
    # 放量破位 / 恐慌观察
    if np.isfinite(vol_ratio) and vol_ratio >= ind.VOL_SPIKE and close < lo20:
        if (not trend) and close < ma50i:
            out.append("BREAKDOWN_VOL")
        else:
            out.append("PANIC_WATCH")
    # 超买乖离（RSI 取 i 处的滚动值）
    rsi_slice = ta.RSI(c[: i + 1], N=14)
    if len(rsi_slice) and np.isfinite(rsi_slice[-1]) and float(rsi_slice[-1]) > ind.RSI_OVEREXT:
        out.append("OVEREXT")
    # 跌破 MA5
    if op >= prev_ma5 and close < ma5i:
        out.append("LOST_MA5")
    # 高位放量阴线
    body = (op - close) / op * 100.0 if op > 0 else 0.0
    if (
        np.isfinite(vol_ratio)
        and vol_ratio >= ind.VOL_SPIKE
        and close < op
        and body >= ind._BODY_MIN
        and np.isfinite(hi6m)
        and hi6m > 0
        and (close / hi6m - 1.0) * 100.0 >= -ind._HIGH_PROXIMITY
    ):
        out.append("DIST_CANDLE")

    return out


def scan_symbol(df: pd.DataFrame, symbol: str) -> tuple[list[str], ind.SymbolMetrics | None]:
    """在最新一根 K 线上扫描信号，返回 ``(信号列表, 指标)``。"""
    m = ind.compute_metrics(df, symbol)
    if m is None or not m.ready:
        return [], m
    sigs: list[str] = []
    s = ind.is_breakout(m, df)
    if s:
        sigs.append(s)
    sig, _ = ind.is_breakdown(m)
    if sig:
        sigs.append(sig)
    if ind.is_lost_ma5(df):
        sigs.append("LOST_MA5")
    if ind.is_overext(m):
        sigs.append("OVEREXT")
    if ind.is_dist_candle(m, df):
        sigs.append("DIST_CANDLE")
    return sigs, m


def backtest_signals(
    pool: dict[str, pd.DataFrame],
    window: int = MAIN_WINDOW,
) -> list[SignalHit]:
    """把信号规则扫过最近 ``window`` 根 K 线，统计方向命中率。

    只保留「观察窗已走完」的样本参与命中率；未走完的累加到 ``pending``——
    把它们当成没命中会系统性低估胜率（越近的信号越吃亏）。
    """
    rets5: dict[str, list[float]] = {}
    rets10: dict[str, list[float]] = {}
    pending: dict[str, int] = {}
    totals: dict[str, int] = {}

    for _sym, df in pool.items():
        if df is None or len(df) < 80:
            continue
        c = df["close"].astype(float).to_numpy()
        h = df["high"].astype(float).to_numpy()
        low = df["low"].astype(float).to_numpy()
        v = df["volume"].astype(float).fillna(0.0).to_numpy()
        ma5 = ta.MA(c, 5)
        ma20 = ta.MA(c, 20)
        ma50 = ta.MA(c, 50)

        start = max(50, len(c) - window)
        # 最后 FWD_LONG 根留作观察窗，不参与统计（否则全是 pending）
        end = len(c) - FWD_LONG
        for i in range(start, end):
            sigs = _classify_at(c, h, low, v, ma5, ma20, ma50, i)
            if not sigs:
                continue
            r5 = _fwd_returns(c, i, FWD_SHORT)
            r10 = _fwd_returns(c, i, FWD_LONG)
            for s in sigs:
                totals[s] = totals.get(s, 0) + 1
                bull = _DIRECTION.get(s, "看多") == "看多"
                if r5 is None or r10 is None:
                    pending[s] = pending.get(s, 0) + 1
                    continue
                # 方向折算：看多信号要涨、看空信号要跌，才算命中
                rets5.setdefault(s, []).append(r5 if bull else -r5)
                rets10.setdefault(s, []).append(r10 if bull else -r10)

    out: list[SignalHit] = []
    for sig, total in totals.items():
        a5 = np.array(rets5.get(sig, []), dtype=float)
        a10 = np.array(rets10.get(sig, []), dtype=float)
        hit = SignalHit(signal=sig, samples=total, pending=pending.get(sig, 0))
        if a5.size:
            hit.avg5, hit.med5 = float(a5.mean()), float(np.median(a5))
            hit.hit5 = float((a5 > 0).mean() * 100.0)
        if a10.size:
            hit.avg10, hit.med10 = float(a10.mean()), float(np.median(a10))
            hit.hit10 = float((a10 > 0).mean() * 100.0)
        # 95% 置信区间半宽（正态近似）：样本越少越宽，读数越该打折扣
        base = a10 if a10.size else a5
        if base.size >= 2:
            hit.ci = float(1.96 * base.std(ddof=1) / np.sqrt(base.size))
        out.append(hit)

    out.sort(key=lambda x: -(x.hit10 if np.isfinite(x.hit10) else -1))
    return out