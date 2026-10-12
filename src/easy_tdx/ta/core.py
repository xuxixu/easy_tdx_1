"""TA-Lib 指标引擎 — 0/1 级公式原语（替代 MyTT）。

本模块提供通达信/麦语言公式的**基础词汇**：序列算子（MA/EMA/SMA/REF/…）
与条件算子（CROSS/BARSLAST/FILTER/…）。它们是 :mod:`easy_tdx.formula`
公式引擎的函数白名单来源，也是中式指标层的构件。

语义基准
--------
原语遵循**通达信方言**（不是 TA-Lib 方言）——公式引擎的目标是让用户在
通达信软件里写惯的公式能原样搬过来。TA-Lib 没有 ``REF``/``HHV``/``CROSS``
这类序列算子，也没有通达信意义下的中国式 ``SMA(X, N, M)``，因此这些只能
自建；而在**数值口径完全等价**的地方（简单均线、加权均线、标准差、平均
偏差）则直接委托 TA-Lib 的 C 实现，既省去 pandas 的滚动窗口开销，又保证
与主流看盘软件逐位一致。

委托 TA-Lib 的原语： :func:`MA` :func:`WMA` :func:`STD` :func:`AVEDEV` :func:`EMA`
自建（TA-Lib 无对应）： :func:`SMA` :func:`DMA` :func:`REF` :func:`HHV` …

与旧 MyTT 的口径差异（``EMA``）
--------------------------------
TA-Lib 的 ``EMA`` 以首 N 根的 SMA 作种子、前 N-1 根输出 ``NaN``；旧 MyTT
用 ``ewm(adjust=False)`` 从首根起算、首根即有值。本项目采用 TA-Lib 原生口径
（更长的预热 ``NaN`` 反而能避免未收敛的均线参与信号判断），需要通达信
首根即出值的场合请用 :func:`core_sma` 配合 ``alpha=2/(N+1)`` 自建。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import talib

__all__ = [
    # 序列算子
    "RD",
    "RET",
    "ABS",
    "LN",
    "POW",
    "SQRT",
    "SIN",
    "COS",
    "TAN",
    "MAX",
    "MIN",
    "IF",
    "REF",
    "DIFF",
    "STD",
    "SUM",
    "CONST",
    "HHV",
    "LLV",
    "HHVBARS",
    "LLVBARS",
    "MA",
    "EMA",
    "SMA",
    "WMA",
    "DMA",
    "AVEDEV",
    "SLOPE",
    "FORCAST",
    "LAST",
    # 条件算子
    "COUNT",
    "EVERY",
    "EXIST",
    "FILTER",
    "BARSLAST",
    "BARSLASTCOUNT",
    "BARSSINCEN",
    "CROSS",
    "LONGCROSS",
    "VALUEWHEN",
    "BETWEEN",
    "TOPRANGE",
    "LOWRANGE",
    # 工具
    "as_f64",
]

F64 = npt.NDArray[np.float64]
ArrayLike = npt.ArrayLike


# ── 内部工具 ──────────────────────────────────────────────────────────────


def as_f64(x: Any) -> F64:
    """转成 TA-Lib 要求的 float64 **连续**数组（不复制已有合格数组）。"""
    arr = np.asarray(x, dtype=np.float64)
    return arr if arr.flags["C_CONTIGUOUS"] else np.ascontiguousarray(arr)


def _f64(x: Any) -> F64:
    """把 pandas ``.to_numpy()`` 等 ``Any`` 返回值收敛成 float64 数组。"""
    return np.asarray(x, dtype=np.float64)


def _tl_empty(n: int) -> F64:
    return np.full(n, np.nan, dtype=np.float64)


def _as_int(n: Any, name: str) -> int:
    """周期参数归一为 int（公式里字面量可能是 float，MyTT 时代的老坑）。"""
    try:
        return int(n)
    except (TypeError, ValueError) as exc:  # pragma: no cover - 防御
        raise ValueError(f"{name} 的周期参数必须是整数，得到 {n!r}") from exc


# ── 逐元素算子 ────────────────────────────────────────────────────────────


def RD(N: ArrayLike, D: int = 3) -> F64:
    """四舍五入取 D 位小数。"""
    return np.round(as_f64(N), D)


def RET(S: ArrayLike, N: int = 1) -> F64:
    """返回序列倒数第 N 个值（默认最后一个），广播为与输入等长的序列。"""
    arr = as_f64(S)
    if len(arr) == 0:
        return _tl_empty(0)
    return np.full(len(arr), arr[-_as_int(N, "RET")], dtype=np.float64)


def ABS(S: ArrayLike) -> F64:
    return np.abs(as_f64(S))


def LN(S: ArrayLike) -> F64:
    return np.log(as_f64(S))


def POW(S: ArrayLike, N: ArrayLike) -> F64:
    return np.power(as_f64(S), as_f64(N))


def SQRT(S: ArrayLike) -> F64:
    return np.sqrt(as_f64(S))


def SIN(S: ArrayLike) -> F64:
    return np.sin(as_f64(S))


def COS(S: ArrayLike) -> F64:
    return np.cos(as_f64(S))


def TAN(S: ArrayLike) -> F64:
    return np.tan(as_f64(S))


def MAX(S1: ArrayLike, S2: ArrayLike) -> F64:
    """逐元素 max（**非** TA-Lib 的滚动窗口 MAX）。"""
    return np.maximum(as_f64(S1), as_f64(S2))


def MIN(S1: ArrayLike, S2: ArrayLike) -> F64:
    """逐元素 min（**非** TA-Lib 的滚动窗口 MIN）。"""
    return np.minimum(as_f64(S1), as_f64(S2))


def IF(S: ArrayLike, A: ArrayLike, B: ArrayLike) -> F64:
    """``IF(S, A, B)``：S 为真取 A，否则取 B。"""
    return np.where(as_f64(S), as_f64(A), as_f64(B))


# ── 序列算子 ──────────────────────────────────────────────────────────────


def REF(S: ArrayLike, N: int = 1) -> F64:
    """序列整体下移 N（返回前 N 个为 NaN）。``N<0`` 引用未来数据。"""
    return _f64(pd.Series(as_f64(S)).shift(_as_int(N, "REF")).to_numpy())


def DIFF(S: ArrayLike, N: int = 1) -> F64:
    """``S - REF(S, N)``，首 N 个为 NaN（不像 ``np.diff`` 那样少一行）。"""
    return _f64(pd.Series(as_f64(S)).diff(_as_int(N, "DIFF")).to_numpy())


def STD(S: ArrayLike, N: int) -> F64:
    """N 日标准差（总体口径 ddof=0，委托 ``talib.STDDEV``）。"""
    arr = as_f64(S)
    n = _as_int(N, "STD")
    return _tl_empty(len(arr)) if len(arr) == 0 else talib.STDDEV(arr, n)


def SUM(S: ArrayLike, N: int) -> F64:
    """N 日滚动求和；``N=0`` 为全序列累计和。"""
    s = pd.Series(as_f64(S))
    n = _as_int(N, "SUM")
    return _f64((s.rolling(n).sum() if n > 0 else s.cumsum()).to_numpy())


def CONST(S: ArrayLike) -> F64:
    """把序列最后一个值广播成常量序列。"""
    arr = as_f64(S)
    return np.full(len(arr), arr[-1], dtype=np.float64)


def HHV(S: ArrayLike, N: int) -> F64:
    """最近 N 根的最高值。"""
    return _f64(pd.Series(as_f64(S)).rolling(_as_int(N, "HHV")).max().to_numpy())


def LLV(S: ArrayLike, N: int) -> F64:
    """最近 N 根的最低值。"""
    return _f64(pd.Series(as_f64(S)).rolling(_as_int(N, "LLV")).min().to_numpy())


def HHVBARS(S: ArrayLike, N: int) -> F64:
    """N 周期内最高值距今的周期数（0 = 当前即最高）。"""
    return _f64(
        pd.Series(as_f64(S))
        .rolling(_as_int(N, "HHVBARS"))
        .apply(lambda x: float(np.argmax(x[::-1])), raw=True)
        .to_numpy()
    )


def LLVBARS(S: ArrayLike, N: int) -> F64:
    """N 周期内最低值距今的周期数。"""
    return _f64(
        pd.Series(as_f64(S))
        .rolling(_as_int(N, "LLVBARS"))
        .apply(lambda x: float(np.argmin(x[::-1])), raw=True)
        .to_numpy()
    )


def MA(S: ArrayLike, N: int) -> F64:
    """N 日简单移动平均（委托 ``talib.SMA``，前 N-1 根为 NaN）。"""
    arr = as_f64(S)
    return _tl_empty(len(arr)) if len(arr) == 0 else talib.SMA(arr, _as_int(N, "MA"))


def EMA(S: ArrayLike, N: int) -> F64:
    """指数移动平均 ``alpha=2/(N+1)``（委托 ``talib.EMA``）。

    TA-Lib 原生口径：以首 N 根 SMA 为种子，前 N-1 根输出 NaN。
    """
    arr = as_f64(S)
    return _tl_empty(len(arr)) if len(arr) == 0 else talib.EMA(arr, _as_int(N, "EMA"))


def SMA(S: ArrayLike, N: int, M: int = 1) -> F64:
    """**中国式** SMA：``alpha = M / N`` 的递归平滑（TA-Lib 无对应实现）。

    通达信 ``SMA(X, N, M)`` 是「加权移动平均」而非简单均线，``M`` 越大越贴
    近原值。注意这与 :func:`MA`（= ``talib.SMA`` 简单均线）语义完全不同。
    """
    n = _as_int(N, "SMA")
    m = _as_int(M, "SMA")
    if n <= 0:
        raise ValueError(f"SMA 的周期 N 必须为正整数，得到 {N!r}")
    return _f64(pd.Series(as_f64(S)).ewm(alpha=m / n, adjust=False).mean().to_numpy())


def WMA(S: ArrayLike, N: int) -> F64:
    """N 日加权移动平均，权重 1..N 线性递增（委托 ``talib.WMA``）。"""
    arr = as_f64(S)
    return _tl_empty(len(arr)) if len(arr) == 0 else talib.WMA(arr, _as_int(N, "WMA"))


def DMA(S: ArrayLike, A: ArrayLike) -> F64:
    """动态移动平均，``A`` 为平滑因子（标量或序列）。"""
    s = as_f64(S)
    if np.isscalar(A) or np.asarray(A).ndim == 0:
        return _f64(pd.Series(s).ewm(alpha=float(np.asarray(A)), adjust=False).mean().to_numpy())
    a = np.array(as_f64(A), copy=True)
    a[np.isnan(a)] = 1.0
    out = np.zeros(len(s), dtype=np.float64)
    if len(s) == 0:
        return out
    out[0] = s[0]
    for i in range(1, len(s)):
        # a[i]>=1 表示完全跟随原值，此时必须跳过 ``(1-a)*prev``：
        # IEEE 下 ``0 * NaN`` 仍是 NaN，会把上游 EMA 的预热 NaN 永久带进
        # 整条序列（FSL 的平滑因子恒为 1，正是这条路径）。
        carry = out[i - 1] if a[i] < 1.0 and np.isfinite(out[i - 1]) else 0.0
        out[i] = a[i] * s[i] + (1.0 - a[i]) * carry
    return out


def AVEDEV(S: ArrayLike, N: int) -> F64:
    """N 日平均绝对偏差（委托 ``talib.AVGDEV``）。"""
    arr = as_f64(S)
    return _tl_empty(len(arr)) if len(arr) == 0 else talib.AVGDEV(arr, _as_int(N, "AVEDEV"))


def SLOPE(S: ArrayLike, N: int) -> F64:
    """N 周期线性回归斜率（等价 ``talib.LINEARREG_SLOPE``）。"""
    arr = as_f64(S)
    return _tl_empty(len(arr)) if len(arr) == 0 else talib.LINEARREG_SLOPE(arr, _as_int(N, "SLOPE"))


def FORCAST(S: ArrayLike, N: int) -> F64:
    """N 周期线性回归对当前位置的拟合值（等价 ``talib.LINEARREG``）。"""
    arr = as_f64(S)
    return _tl_empty(len(arr)) if len(arr) == 0 else talib.LINEARREG(arr, _as_int(N, "FORCAST"))


def LAST(S: ArrayLike, A: int, B: int) -> F64:
    """从第 A 期回溯到第 B 期是否一直为真（要求 A>B 且 A>0）。"""
    a = _as_int(A, "LAST")
    b = _as_int(B, "LAST")
    return np.asarray(
        pd.Series(as_f64(S)).rolling(a + 1).apply(lambda x: np.all(x[::-1][b:]), raw=True),
        dtype=bool,
    )


# ── 条件算子 ──────────────────────────────────────────────────────────────


def COUNT(S: ArrayLike, N: int) -> F64:
    """最近 N 根中条件成立的根数。"""
    return SUM(S, N)


def EVERY(S: ArrayLike, N: int) -> F64:
    """最近 N 根是否全部成立。"""
    return np.asarray(SUM(S, N) == _as_int(N, "EVERY"))


def EXIST(S: ArrayLike, N: int) -> F64:
    """最近 N 根中是否存在一根成立。"""
    return np.asarray(SUM(S, N) > 0)


def FILTER(S: ArrayLike, N: int) -> F64:
    """条件成立后，把其后 N 根的信号置 0（去重复信号）。"""
    out = np.array(as_f64(S), copy=True)
    step = _as_int(N, "FILTER")
    for i in range(len(out)):
        if out[i]:
            out[i + 1 : i + 1 + step] = 0
    return out


def BARSLAST(S: ArrayLike) -> F64:
    """上一次条件成立到当前的周期数（无则累加）。"""
    m = np.concatenate(([0], np.where(as_f64(S), 1, 0))).astype(np.float64)
    for i in range(1, len(m)):
        m[i] = 0 if m[i] else m[i - 1] + 1
    return m[1:]


def BARSLASTCOUNT(S: ArrayLike) -> F64:
    """连续满足条件的周期数。"""
    flags = as_f64(S)
    rt = np.zeros(len(flags) + 1, dtype=np.float64)
    for i in range(len(flags)):
        rt[i + 1] = rt[i] + 1 if flags[i] else rt[i + 1]
    return rt[1:]


def BARSSINCEN(S: ArrayLike, N: int) -> F64:
    """N 周期内第一次条件成立到当前的周期数。"""
    n = _as_int(N, "BARSSINCEN")
    return _f64(
        pd.Series(as_f64(S))
        .rolling(n)
        .apply(lambda x: n - 1 - np.argmax(x) if np.argmax(x) or x[0] else 0, raw=True)
        .fillna(0)
        .to_numpy()
        .astype(int)
    )


def CROSS(S1: ArrayLike, S2: ArrayLike) -> F64:
    """向上金叉：``S1`` 本期上穿 ``S2``（首根恒为 False）。"""
    a, b = as_f64(S1), as_f64(S2)
    return np.concatenate(([False], np.logical_not((a > b)[:-1]) & (a > b)[1:]))


def LONGCROSS(S1: ArrayLike, S2: ArrayLike, N: int) -> F64:
    """两条线维持 N 周期后交叉（S1 在 N 周期内均小于 S2，本期上穿）。"""
    a, b = as_f64(S1), as_f64(S2)
    return _f64(np.logical_and(LAST(a < b, N, 1), a > b))


def VALUEWHEN(S: ArrayLike, X: ArrayLike) -> F64:
    """条件成立时取 X 的值，否则沿用上一次成立时的值。"""
    return _f64(pd.Series(np.where(as_f64(S), as_f64(X), np.nan)).ffill().to_numpy())


def BETWEEN(S: ArrayLike, A: ArrayLike, B: ArrayLike) -> F64:
    """S 处于 A 与 B 之间（含双向）。"""
    s, a, b = as_f64(S), as_f64(A), as_f64(B)
    return _f64(((a < s) & (s < b)) | ((a > s) & (s > b)))


def TOPRANGE(S: ArrayLike) -> F64:
    """当前值是近多少周期内的最高值（0 = 当前即最高）。"""
    s = as_f64(S)
    rt = np.zeros(len(s), dtype=np.float64)
    for i in range(1, len(s)):
        rt[i] = np.argmin(np.flipud(s[:i] < s[i]))
    return rt


def LOWRANGE(S: ArrayLike) -> F64:
    """当前值是近多少周期内的最低值。"""
    s = as_f64(S)
    rt = np.zeros(len(s), dtype=np.float64)
    for i in range(1, len(s)):
        rt[i] = np.argmin(np.flipud(s[:i] > s[i]))
    return rt
