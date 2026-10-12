"""TA-Lib 指标引擎 — 自建中式指标层。

TA-Lib 只覆盖西方技术分析指标，A股/通达信体系里一大批常用指标没有对应
实现（乖离率、薛斯通道、唐安奇之外的肯特纳/梅斯线、捉妖大师 …）。这一层
把它们用 :mod:`easy_tdx.ta.core` 的原语重新实现——公式定义完全遵循通达信
写法，因此这些指标的**语义不随引擎更换而改变**（与
:mod:`easy_tdx.ta.talib_ind` 中改用 TA-Lib 原生口径的指标形成对照）。

新增/保留的都是只引用当期及历史数据的**无未来函数**实现。
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .core import (
    ABS,
    DMA,
    EMA,
    FORCAST,
    HHV,
    LLV,
    MA,
    MAX,
    MIN,
    REF,
    SLOPE,
    STD,
    SUM,
    as_f64,
)

__all__ = [
    "BIAS",
    "PSY",
    "CR",
    "EMV",
    "BRAR",
    "XSII",
    "VR",
    "BBI",
    "DFMA",
    "MASS",
    "ASI",
    "KTN",
    "FSL",
    "ZHUOYAO",
    "BIAS_SIGNAL",
    "FK",
    "VWAP",
    "CHANDELIER",
    "ICHIMOKU",
    "UOS",
    "FISHER",
    "SQUEEZE",
    "CHOP",
    "OUTPERFORM_20D",
]

F64 = npt.NDArray[np.float64]
ArrayLike = npt.ArrayLike


def _nan(n: int) -> F64:
    return np.full(n, np.nan, dtype=np.float64)


def _true_range(HIGH: ArrayLike, LOW: ArrayLike, CLOSE: ArrayLike) -> F64:
    """真实波幅 TR = max(H-L, |H-prevC|, |L-prevC|)。"""
    h, low, c = as_f64(HIGH), as_f64(LOW), as_f64(CLOSE)
    prev_c = np.concatenate(([c[0]] if len(c) else [], c[:-1]))
    return MAX(MAX(h - low, ABS(h - prev_c)), ABS(low - prev_c))


# ── 乖离率 / 情绪 ─────────────────────────────────────────────────────────


def BIAS(CLOSE: ArrayLike, L1: int = 6, L2: int = 12, L3: int = 24) -> tuple[F64, F64, F64]:
    """乖离率，返回三周期 ``(BIAS1, BIAS2, BIAS3)``（%）。"""
    c = as_f64(CLOSE)

    def _bias(n: int) -> F64:
        m = MA(c, n)
        # MA(c,n) may be 0 or NaN in warmup -> NaN guard, consistent with CR/VR
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(m > 0, (c - m) / m * 100.0, np.nan)

    return _bias(int(L1)), _bias(int(L2)), _bias(int(L3))


def PSY(CLOSE: ArrayLike, N: int = 12, M: int = 6) -> tuple[F64, F64]:
    """心理线，返回 ``(PSY, PSY_MA)``。"""
    c = as_f64(CLOSE)
    n = int(N)
    psy = SUM(c > REF(c, 1), n) / n * 100.0
    return psy, MA(psy, int(M))


def CR(CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 20) -> F64:
    """价格动量指标 CR（中间价对比的累积多空力量）。"""
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    mid = REF(h + low + c, 1) / 3.0
    num = SUM(MAX(0.0, h - mid), int(N))
    den = SUM(MAX(0.0, mid - low), int(N))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, num / den * 100.0, 100.0)


def VR(CLOSE: ArrayLike, VOL: ArrayLike, M1: int = 26) -> F64:
    """容量比率 VR：上涨日成交量 / 下跌日成交量 × 100。

    分母（下跌日累计量）为 0 时取 ``NaN`` 而非 ``inf``——一整段单边上涨里
    ``inf`` 会直接污染下游排名与阈值比较。
    """
    c, v = as_f64(CLOSE), as_f64(VOL)
    lc = REF(c, 1)
    up = SUM(np.where(c > lc, v, 0.0), int(M1))
    down = SUM(np.where(c <= lc, v, 0.0), int(M1))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(down > 0, up / down * 100.0, np.nan)


def EMV(
    HIGH: ArrayLike, LOW: ArrayLike, VOL: ArrayLike, N: int = 14, M: int = 9
) -> tuple[F64, F64]:
    """简易波动指标，返回 ``(EMV, EMV_MA)``。"""
    h, low, v = as_f64(HIGH), as_f64(LOW), as_f64(VOL)
    n = int(N)
    with np.errstate(divide="ignore", invalid="ignore"):
        volume = MA(v, n) / v
    hs = h + low
    mid = 100.0 * (hs - REF(hs, 1)) / hs
    emv = MA(mid * volume * (h - low) / MA(h - low, n), n)
    return emv, MA(emv, int(M))


def BRAR(
    OPEN: ArrayLike, CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, M1: int = 26
) -> tuple[F64, F64]:
    """BRAR 情绪指标，返回 ``(AR, BR)``。"""
    o, c, h, low = as_f64(OPEN), as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    m = int(M1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ar = SUM(h - o, m) / SUM(o - low, m) * 100.0
        br = SUM(MAX(0.0, h - REF(c, 1)), m) / SUM(MAX(0.0, REF(c, 1) - low), m) * 100.0
    return ar, br


def XSII(
    CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 102, M: int = 7
) -> tuple[F64, F64, F64, F64]:
    """薛斯通道 II，返回 ``(TD1, TD2, TD3, TD4)``。"""
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    n = int(N)
    m = int(M)
    aa = MA((2.0 * c + h + low) / 4.0, 5)
    ma20 = MA(c, 20)
    with np.errstate(divide="ignore", invalid="ignore"):
        cc = np.abs((2.0 * c + h + low) / 4.0 - ma20) / ma20
    dd = DMA(c, cc)
    return aa * n / 100.0, aa * (200 - n) / 100.0, (1 + m / 100.0) * dd, (1 - m / 100.0) * dd


def ASI(
    OPEN: ArrayLike,
    CLOSE: ArrayLike,
    HIGH: ArrayLike,
    LOW: ArrayLike,
    M1: int = 26,
    M2: int = 10,
) -> tuple[F64, F64]:
    """振动升降指标，返回 ``(ASI, ASI_MA)``。

    以「昨收」为基准比较当日真实波幅的相对强弱并累积，``SI`` 反映的是
    ``AA/BB/CC`` 三段波幅中占优的那一段。
    """
    o, c, h, low = as_f64(OPEN), as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    lc = REF(c, 1)
    aa = ABS(h - lc)
    bb = ABS(low - lc)
    cc = ABS(h - REF(low, 1))
    dd = ABS(lc - REF(o, 1))
    r = np.where(
        (aa > bb) & (aa > cc),
        aa + bb / 2.0 + dd / 4.0,
        np.where((bb > cc) & (bb > aa), bb + aa / 2.0 + dd / 4.0, cc + dd / 4.0),
    )
    x = c - lc + (c - o) / 2.0 + lc - REF(o, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        si = 16.0 * x / r * MAX(aa, bb)
    asi = SUM(si, int(M1))
    return asi, MA(asi, int(M2))


# ── 均线 / 通道 ───────────────────────────────────────────────────────────


def BBI(CLOSE: ArrayLike, M1: int = 3, M2: int = 6, M3: int = 12, M4: int = 20) -> F64:
    """多空指标：四条均线的等权合成。"""
    c = as_f64(CLOSE)
    return (MA(c, int(M1)) + MA(c, int(M2)) + MA(c, int(M3)) + MA(c, int(M4))) / 4.0


def DFMA(CLOSE: ArrayLike, N1: int = 10, N2: int = 50, M: int = 10) -> tuple[F64, F64]:
    """平行线差指标，返回 ``(DIFF, DIFFMA)``。"""
    c = as_f64(CLOSE)
    diff = MA(c, int(N1)) - MA(c, int(N2))
    return diff, MA(diff, int(M))


def KTN(
    CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 20, M: int = 10
) -> tuple[F64, F64, F64]:
    """肯特纳交易通道，返回 ``(上轨, 中轨, 下轨)``：EMA(HLC/3, N) ± 2×ATR(M)。"""
    from .talib_ind import ATR  # 局部导入避免与 core 形成导入环

    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    mid = EMA((h + low + c) / 3.0, int(N))
    atr = ATR(c, h, low, int(M))
    return mid + 2.0 * atr, mid, mid - 2.0 * atr


def MASS(HIGH: ArrayLike, LOW: ArrayLike, N1: int = 9, N2: int = 25, M: int = 6) -> tuple[F64, F64]:
    """梅斯线（高低差与其均线的比值累积），返回 ``(MASS, MASS_MA)``。"""
    h, low = as_f64(HIGH), as_f64(LOW)
    hl_ma = MA(h - low, int(N1))
    with np.errstate(divide="ignore", invalid="ignore"):
        mass = SUM(hl_ma / MA(hl_ma, int(N1)), int(N2))
    return mass, MA(mass, int(M))


def CHANDELIER(
    CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 22, M: int = 22, K: float = 3.0
) -> tuple[F64, F64]:
    """吊灯止损，返回 ``(多头止损位, 空头止损位)``。"""
    from .talib_ind import ATR

    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    atr = ATR(c, h, low, int(M))
    return HHV(h, int(N)) - atr * float(K), LLV(low, int(N)) + atr * float(K)


def VWAP(CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, VOL: ArrayLike, N: int = 20) -> F64:
    """N 日滚动成交量加权均价（机构基准成本线）。

    与 ``talib.VWAP`` 不同：TA-Lib 的 VWAP 以「当日/会话」为锚点逐日重置，
    这里按 N 日滚动窗口计算，是 A 股常用的机构成本口径。
    """
    c, h, low, v = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW), as_f64(VOL)
    n = int(N)
    tp = (h + low + c) / 3.0
    import pandas as pd

    num = pd.Series(tp * v).rolling(n).sum().to_numpy()
    den = pd.Series(v).rolling(n).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.asarray(np.where(den > 0, num / den, np.nan), dtype=np.float64)


# ── 趋势 / 结构 ───────────────────────────────────────────────────────────


def ICHIMOKU(
    HIGH: ArrayLike,
    LOW: ArrayLike,
    CLOSE: ArrayLike,
    P1: int = 9,
    P2: int = 26,
    P3: int = 52,
    SHIFT: int = 26,
) -> tuple[F64, F64, F64, F64, F64]:
    """一目均衡表，返回 ``(转换线, 基准线, 先行A, 先行B, 迟行带)``。

    迟行带把当前收盘画回 SHIFT 期前，**仅供图示**——当期信号请用转换线/
    基准线与先行带，否则构成未来函数。
    """
    h, low, c = as_f64(HIGH), as_f64(LOW), as_f64(CLOSE)
    p1, p2, p3, shift = int(P1), int(P2), int(P3), int(SHIFT)
    tenkan = (HHV(h, p1) + LLV(low, p1)) / 2.0
    kijun = (HHV(h, p2) + LLV(low, p2)) / 2.0
    return (
        tenkan,
        kijun,
        REF((tenkan + kijun) / 2.0, shift),
        REF((HHV(h, p3) + LLV(low, p3)) / 2.0, shift),
        REF(c, -shift),
    )


def ZHUOYAO(
    CLOSE: ArrayLike, N1: int = 120, N2: int = 60, N3: int = 20, M: int = 10
) -> tuple[F64, F64, F64, F64]:
    """捉妖大师：中长短线涨幅共振。

    返回 ``(长线EXPMA, 中线涨幅, 短线涨幅, 趋势EXPMA)``——长线与趋势线是
    中长线涨幅的指数均线，中/短线是原始涨幅百分比。
    """
    c = as_f64(CLOSE)
    mid = (c / REF(c, int(N2)) - 1.0) * 100.0
    long1 = (c / REF(c, int(N1)) - 1.0) * 100.0
    short = (c / REF(c, int(N3)) - 1.0) * 100.0
    return EMA(long1, int(M)), mid, short, EMA(mid, int(M))


def BIAS_SIGNAL(CLOSE: ArrayLike, P: int = 10, M: int = 30) -> tuple[F64, F64, F64]:
    """乖离率信号线，返回 ``(乖离率X, 短信号线, 长信号线)``。"""
    c = as_f64(CLOSE)
    ma_m = MA(c, int(M))
    with np.errstate(divide="ignore", invalid="ignore"):
        x = (c - ma_m) / ma_m * 100.0
    return x, MA(x, int(P)), MA(x, int(M))


def FK(CLOSE: ArrayLike) -> F64:
    """FK 趋势指标：快线 EMA(2) 是否在斜率外推慢线 EMA(42) 之上（布尔）。"""
    c = as_f64(CLOSE)
    fast = EMA(c, 2)
    # 慢线：把 21 周期回归斜率放大 20 倍外推，叠加收盘价后再取 42 期 EMA
    slow = EMA(SLOPE(c, 21) * 20.0 + c, 42)
    return np.asarray(fast > slow, dtype=np.float64)


def FSL(CLOSE: ArrayLike, VOL: ArrayLike, CAPITAL: float) -> tuple[F64, F64]:
    """分水岭指标：多空趋势强弱分界，返回 ``(SWL, SWS)``。"""
    c, v = as_f64(CLOSE), as_f64(VOL)
    swl = (EMA(c, 5) * 7.0 + EMA(c, 10) * 3.0) / 10.0
    a = MAX(1.0, 100.0 * (SUM(v, 5) / (3.0 * float(CAPITAL))))
    a = MIN(a, 1.0)  # 钳制平滑因子，避免极端换手率下发散
    return swl, DMA(EMA(c, 12), a)


def OUTPERFORM_20D(CLOSE: ArrayLike, INDEX_CLOSE: ArrayLike) -> F64:
    """20 日相对强度：个股涨幅跑赢大盘返回 1。"""
    c, idx = as_f64(CLOSE), as_f64(INDEX_CLOSE)
    stock_ret = (c - REF(c, 20)) / REF(c, 20)
    index_ret = (idx - REF(idx, 20)) / REF(idx, 20)
    return np.asarray(stock_ret > index_ret, dtype=np.float64)


# ── 动量 / 波动状态 ───────────────────────────────────────────────────────


def UOS(
    CLOSE: ArrayLike,
    HIGH: ArrayLike,
    LOW: ArrayLike,
    P1: int = 7,
    P2: int = 14,
    P3: int = 28,
    M: int = 6,
) -> tuple[F64, F64]:
    """终极指标：7/14/28 三周期买压/真波幅加权动量，返回 ``(UOS, UOS_MA)``。"""
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    th = MAX(h, REF(c, 1))
    tl = MIN(low, REF(c, 1))
    bp = c - tl
    tr = th - tl

    def _avg(p: int) -> F64:
        num, den = MA(bp, p), MA(tr, p)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(den > 0, num / den, 0.5)
        return np.where(np.isnan(num) | np.isnan(den), np.nan, ratio)

    uos = 100.0 * (4 * _avg(int(P1)) + 2 * _avg(int(P2)) + _avg(int(P3))) / 7.0
    return uos, MA(uos, int(M))


def FISHER(HIGH: ArrayLike, LOW: ArrayLike, N: int = 9) -> tuple[F64, F64]:
    """费雪变换（John Ehlers）：把区间位置正态化，返回 ``(FISHER, 触发线)``。"""
    h, low = as_f64(HIGH), as_f64(LOW)
    n = int(N)
    price = (h + low) / 2.0
    rng = HHV(price, n) - LLV(price, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.where(rng > 0, 2.0 * (price - LLV(price, n)) / rng - 1.0, 0.0)
    norm = np.where(np.isnan(rng), np.nan, raw)
    size = len(price)
    value = np.full(size, np.nan)
    fisher = np.full(size, np.nan)
    for i in range(size):
        if np.isnan(norm[i]):
            continue
        prev_v = 0.0 if np.isnan(value[i - 1]) else value[i - 1]
        prev_f = 0.0 if np.isnan(fisher[i - 1]) else fisher[i - 1]
        v = max(-0.999, min(0.999, 0.33 * norm[i] + 0.67 * prev_v))
        value[i] = v
        fisher[i] = 0.5 * np.log((1 + v) / (1 - v)) + 0.5 * prev_f
    return fisher, REF(fisher, 1)


def SQUEEZE(
    CLOSE: ArrayLike,
    HIGH: ArrayLike,
    LOW: ArrayLike,
    N: int = 20,
    BB: float = 2.0,
    KC: float = 1.5,
) -> tuple[F64, F64]:
    """TTM 挤压动量，返回 ``(是否挤压, 动量)``。

    布林带整体收进肯特纳通道内即判定为挤压态。
    """
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    n = int(N)
    mid = MA(c, n)
    dev = STD(c, n) * float(BB)
    range_ma = MA(_true_range(h, low, c), n)
    sqz_on = dev < float(KC) * range_ma
    delta = c - ((HHV(h, n) + LLV(low, n)) / 2.0 + mid) / 2.0
    return np.asarray(sqz_on, dtype=np.float64), np.asarray(FORCAST(delta, n), dtype=np.float64)


def CHOP(HIGH: ArrayLike, LOW: ArrayLike, CLOSE: ArrayLike, N: int = 14) -> F64:
    """盘整指数：>61.8 震荡 / <38.2 趋势。"""
    h, low, c = as_f64(HIGH), as_f64(LOW), as_f64(CLOSE)
    n = int(N)
    tr_sum = SUM(_true_range(h, low, c), n)
    rng = HHV(h, n) - LLV(low, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where((tr_sum > 0) & (rng > 0), tr_sum / rng, np.nan)
    return np.asarray(100.0 * np.log10(ratio) / np.log10(n), dtype=np.float64)
