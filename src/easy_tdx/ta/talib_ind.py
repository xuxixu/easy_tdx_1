"""TA-Lib 指标引擎 — 原生指标适配层。

本模块的每个函数**函数名与入参顺序沿用旧 MyTT**（调用方
``backtest/strategies/builtin.py`` / ``factor`` / 用户策略无需改写调用方式），
**函数体改为 TA-Lib 原生实现**。数值口径以 TA-Lib 为准，与通达信/MTA 的差异
见下表；需要中式口径的指标在 :mod:`easy_tdx.ta.chinese` 自建。

与旧 MyTT 的口径差异（重要）
----------------------------
======================  =====================  ======================
指标                     旧 MyTT                 TA-Lib 原生
======================  =====================  ======================
``MACD`` 柱              ``(DIF-DEA) * 2``      ``DIF-DEA``（不乘 2）
``RSI`` 默认周期          24                     14（Wilder 平滑）
``WR`` 取值域            0~100（100=超卖）      -100~0（0=超买）取自 WILLR
``OBV`` 量纲             手写累计量 / 10000     原始累计成交量
``SUPERTREND`` 方向      1=多 / -1=空            -1=多 / 1=空（TA-Lib 约定）
``AROON`` 平滑           HHV/LLV 距今周期数     TA-Lib AROON 同口径
======================  =====================  ======================

TA-Lib 约定所有输出与输入等长、预热段为 ``NaN``，本模块不做截断。
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import talib

from .core import MA, as_f64

__all__ = [
    "MACD",
    "RSI",
    "BOLL",
    "KDJ",
    "ATR",
    "CCI",
    "MFI",
    "OBV",
    "WR",
    "DMI",
    "AROON",
    "SAR",
    "TRIX",
    "ROC",
    "MTM",
    "DPO",
    "AD",
    "CMF",
    "EFI",
    "TSI",
    "CMO",
    "HMA",
    "KAMA",
    "SUPERTREND",
    "TAQ",
    "BBW",
    "BBP",
    "EXPMA",
]

F64 = npt.NDArray[np.float64]
ArrayLike = npt.ArrayLike


def _nan(n: int) -> F64:
    return np.full(n, np.nan, dtype=np.float64)


# ── 趋势 / 动量 ───────────────────────────────────────────────────────────


def MACD(CLOSE: ArrayLike, SHORT: int = 12, LONG: int = 26, M: int = 9) -> tuple[F64, F64, F64]:
    """MACD 快慢均线差。返回 ``(DIF, DEA, MACD柱)``。

    TA-Lib 原生口径：柱 = ``DIF - DEA``（**不再乘 2**）。历史实现按通达信
    习惯放大一倍，数值与通达信软件相差 2 倍。

    .. note::
        通达信软件约定柱值为 ``(DIF - DEA) * 2``；本实现**有意保持**
        ``DIF - DEA`` 不乘 2，作为本项目的记录偏差。下游阈值（金叉/死叉、
        红柱绿柱分界等）必须对齐本口径——例如判定红柱（正柱）在通达信里
        可能是 ``> 0``，本实现下同样以 ``> 0`` 为准，但**绝对数值**较通达信
        小一半，切勿直接照搬通达信里的柱高阈值。
    """
    c = as_f64(CLOSE)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy(), e.copy()
    dif, dea, hist = talib.MACD(c, int(SHORT), int(LONG), int(M))
    return dif, dea, hist


def RSI(CLOSE: ArrayLike, N: int = 14) -> F64:
    """RSI 相对强弱指标（Wilder 平滑，TA-Lib 默认周期 14）。"""
    c = as_f64(CLOSE)
    return _nan(len(c)) if len(c) == 0 else talib.RSI(c, int(N))


def BOLL(CLOSE: ArrayLike, N: int = 20, P: float = 2) -> tuple[F64, F64, F64]:
    """布林带，返回 ``(上轨, 中轨, 下轨)``。"""
    c = as_f64(CLOSE)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy(), e.copy()
    upper, mid, lower = talib.BBANDS(c, int(N), float(P), float(P))
    return upper, mid, lower


def KDJ(
    CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 9, M1: int = 3, M2: int = 3
) -> tuple[F64, F64, F64]:
    """KDJ 随机指标，返回 ``(K, D, J)``。

    ``talib.KDJ`` 的默认平滑（``matype=13`` Wilder）恰好等价通达信的
    ``SMA(X, 3, 1)``（``alpha=1/3``），且原生输出 K/D/J 三线。
    """
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy(), e.copy()
    # TA-Lib 的 MA_Type.RMA(=13) 即 Wilder 平滑，恰好等价通达信的 SMA(X,3,1)
    rma = talib.MA_Type.RMA  # type: ignore[attr-defined]  # 运行时导出、存根未 re-export
    k, d, j = talib.KDJ(h, low, c, int(N), int(M1), rma, int(M2), rma)
    return k, d, j


def ATR(CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 20) -> F64:
    """平均真实波幅（Wilder 平滑）。"""
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    return _nan(len(c)) if len(c) == 0 else talib.ATR(h, low, c, int(N))


def CCI(CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 14) -> F64:
    """顺势指标 CCI。"""
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    return _nan(len(c)) if len(c) == 0 else talib.CCI(h, low, c, int(N))


def MFI(CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, VOL: ArrayLike, N: int = 14) -> F64:
    """资金流量指标（成交量的 RSI）。"""
    c, h, low, v = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW), as_f64(VOL)
    return _nan(len(c)) if len(c) == 0 else talib.MFI(h, low, c, v, int(N))


def OBV(CLOSE: ArrayLike, VOL: ArrayLike) -> F64:
    """能量潮 OBV（TA-Lib 原生：原始累计成交量，不再除以 10000）。"""
    c, v = as_f64(CLOSE), as_f64(VOL)
    return _nan(len(c)) if len(c) == 0 else talib.OBV(c, v)


def WR(
    CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 10, N1: int = 6
) -> tuple[F64, F64]:
    """威廉指标，返回 ``(WR, WR1)`` 两个周期。

    取值域 ``-100~0``（**0 = 超买，-100 = 超卖**，TA-Lib ``WILLR`` 口径）；
    旧实现是 ``0~100`` 且方向相反，阈值需相应改为负数区间。
    """
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy()
    return talib.WILLR(h, low, c, int(N)), talib.WILLR(h, low, c, int(N1))


def DMI(
    CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, M1: int = 14, M2: int = 6
) -> tuple[F64, F64, F64, F64]:
    """动向指标，返回 ``(PDI, MDI, ADX, ADXR)``。

    ADXR 采用通达信口径：``(ADX + MA(ADX, M2)) / 2``，``M2`` 为 ADX 的均线周期。
    默认 ``M2=6``；``M2`` 为 ``None`` 时退回 TA-Lib 原生的 ``talib.ADXR``（以
    ``M1`` 为周期，即自身周期的一半）。此前 ``M2`` 参数并未参与计算，属死参数。
    """
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy(), e.copy(), e.copy()
    period = int(M1)
    pdi = talib.PLUS_DI(h, low, c, period)
    mdi = talib.MINUS_DI(h, low, c, period)
    adx = talib.ADX(h, low, c, period)
    if M2 is None:
        adxr: F64 = talib.ADXR(h, low, c, period)
    else:
        # 通达信 ADXR = (ADX + MA(ADX, M2)) / 2
        adxr = (adx + MA(adx, int(M2))) / 2.0
    return pdi, mdi, adx, adxr


def AROON(HIGH: ArrayLike, LOW: ArrayLike, N: int = 25) -> tuple[F64, F64, F64]:
    """阿隆指标，返回 ``(AROON_UP, AROON_DOWN, OSC)``。

    注意 ``talib.AROON`` 的返回顺序是 ``(down, up)``，此处已转回 up/down。
    """
    h, low = as_f64(HIGH), as_f64(LOW)
    if len(h) == 0:
        e = _nan(0)
        return e, e.copy(), e.copy()
    down, up = talib.AROON(h, low, int(N))
    return up, down, up - down


def SAR(HIGH: ArrayLike, LOW: ArrayLike, AF_STEP: float = 0.02, AF_MAX: float = 0.2) -> F64:
    """抛物线转向 SAR（动态止损位）。"""
    h, low = as_f64(HIGH), as_f64(LOW)
    return _nan(len(h)) if len(h) == 0 else talib.SAR(h, low, float(AF_STEP), float(AF_MAX))


def TRIX(CLOSE: ArrayLike, M1: int = 12, M2: int = 20) -> tuple[F64, F64]:
    """三重指数平滑平均线，返回 ``(TRIX, TRIX_MA)``。TRIX 本身为百分数。"""
    c = as_f64(CLOSE)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy()
    trix = talib.TRIX(c, int(M1))
    return trix, MA(trix, int(M2))


def ROC(CLOSE: ArrayLike, N: int = 12, M: int = 6) -> tuple[F64, F64]:
    """变动率指标，返回 ``(ROC, ROC_MA)``。ROC 为百分数。"""
    c = as_f64(CLOSE)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy()
    roc = talib.ROC(c, int(N))
    return roc, MA(roc, int(M))


def MTM(CLOSE: ArrayLike, N: int = 12, M: int = 6) -> tuple[F64, F64]:
    """动量指标，返回 ``(MTM, MTM_MA)``。"""
    c = as_f64(CLOSE)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy()
    mtm = talib.MOM(c, int(N))
    return mtm, MA(mtm, int(M))


def DPO(CLOSE: ArrayLike, M1: int = 20, M2: int = 10, M3: int = 6) -> tuple[F64, F64]:
    """区间震荡线，返回 ``(DPO, DPO_MA)``。``M2`` 仅为接口兼容保留。"""
    c = as_f64(CLOSE)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy()
    dpo = talib.DPO(c, int(M1))
    return dpo, MA(dpo, int(M3))


def EXPMA(CLOSE: ArrayLike, N1: int = 12, N2: int = 50) -> tuple[F64, F64]:
    """双周期指数平均数，返回 ``(EMA(N1), EMA(N2))``。"""
    c = as_f64(CLOSE)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy()
    return talib.EMA(c, int(N1)), talib.EMA(c, int(N2))


# ── 量能 / 资金 ───────────────────────────────────────────────────────────


def AD(CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, VOL: ArrayLike) -> F64:
    """累积/派发线（Chaikin A/D Line）。"""
    c, h, low, v = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW), as_f64(VOL)
    return _nan(len(c)) if len(c) == 0 else talib.AD(h, low, c, v)


def CMF(CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, VOL: ArrayLike, N: int = 20) -> F64:
    """佳庆资金流量（Chaikin Money Flow）。"""
    c, h, low, v = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW), as_f64(VOL)
    return _nan(len(c)) if len(c) == 0 else talib.CMF(h, low, c, v, int(N))


def EFI(CLOSE: ArrayLike, VOL: ArrayLike, N: int = 13) -> F64:
    """艾尔德强力指数（EMA(ΔC × V)）。"""
    c, v = as_f64(CLOSE), as_f64(VOL)
    return _nan(len(c)) if len(c) == 0 else talib.EFI(c, v, int(N))


# ── 振荡 / 状态 ───────────────────────────────────────────────────────────


def CMO(CLOSE: ArrayLike, N: int = 14) -> F64:
    """钱德动量振荡器。"""
    c = as_f64(CLOSE)
    return _nan(len(c)) if len(c) == 0 else talib.CMO(c, int(N))


def TSI(CLOSE: ArrayLike, R: int = 25, S: int = 13, M: int = 13) -> tuple[F64, F64]:
    """真实强度指数，返回 ``(TSI, TSI_MA)``。"""
    c = as_f64(CLOSE)
    if len(c) == 0:
        e = _nan(0)
        return e, e.copy()
    tsi = talib.TSI(c, int(R), int(S))
    return tsi, talib.EMA(tsi, int(M))


# ── 均线 / 通道 / 趋势 ────────────────────────────────────────────────────


def HMA(CLOSE: ArrayLike, N: int = 16) -> F64:
    """赫尔均线 Hull MA（低滞后、不重绘）。"""
    c = as_f64(CLOSE)
    return _nan(len(c)) if len(c) == 0 else talib.HMA(c, int(N))


def KAMA(CLOSE: ArrayLike, N: int = 10, FAST: int = 2, SLOW: int = 30) -> F64:
    """考夫曼自适应均线。

    ``FAST``/``SLOW`` 为兼容旧签名保留——TA-Lib 的 KAMA 内置固定
    快慢常量 2/30，与默认值一致，传入其他值不生效。
    """
    c = as_f64(CLOSE)
    del FAST, SLOW  # TA-Lib 原生常量，不可配置
    return _nan(len(c)) if len(c) == 0 else talib.KAMA(c, int(N))


def SUPERTREND(
    CLOSE: ArrayLike, HIGH: ArrayLike, LOW: ArrayLike, N: int = 10, M: float = 3.0
) -> tuple[F64, F64]:
    """超级趋势，返回 ``(SUPERTREND, ST_DIR)``。

    ``ST_DIR`` 采用 TA-Lib 约定：``-1`` 多头 / ``1`` 空头（旧实现相反）。
    """
    c, h, low = as_f64(CLOSE), as_f64(HIGH), as_f64(LOW)
    if len(c) == 0:
        e = _nan(0)
        return e, _nan(0)
    line, direction = talib.SUPERTREND(h, low, c, int(N), float(M))
    return line, np.asarray(direction, dtype=np.float64)


def TAQ(HIGH: ArrayLike, LOW: ArrayLike, N: int = 20) -> tuple[F64, F64, F64]:
    """唐安奇通道（海龟突破通道），返回 ``(上轨, 中轨, 下轨)``。"""
    h, low = as_f64(HIGH), as_f64(LOW)
    if len(h) == 0:
        e = _nan(0)
        return e, e.copy(), e.copy()
    upper, mid, lower = talib.DONCHIAN(h, low, int(N))
    return upper, mid, lower


def BBW(CLOSE: ArrayLike, N: int = 20, P: float = 2) -> F64:
    """布林带宽：``(上轨-下轨)/中轨*100``（收窄 = 变盘预警）。"""
    upper, mid, lower = BOLL(CLOSE, N, P)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(mid != 0, (upper - lower) / mid * 100.0, np.nan)


def BBP(CLOSE: ArrayLike, N: int = 20, P: float = 2) -> F64:
    """布林位置 %B：收盘在带内的相对位置（0=下轨，100=上轨）。"""
    c = as_f64(CLOSE)
    upper, mid, lower = BOLL(c, N, P)
    width = upper - lower
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(width != 0, (c - lower) / width * 100.0, np.nan)
