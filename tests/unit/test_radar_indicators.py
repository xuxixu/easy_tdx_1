"""雷达指标与信号判定单测：纯合成 K 线，不出网、不依赖 akshare。

重点覆盖三处容易「看起来对、其实是错」的地方：

1. **支撑/压力的方向扫描**：聚类按价位升序，反向扫描时现价之上的簇必须
   ``continue`` 跳过而不是 ``break`` 退出。写成 break 时，82% 的正常票会被
   误判成「附近无支撑」——数据看着只是少了一列，不会报错，所以极难发现。
2. **前 20 日高低点不含当天**：含当天则今日新高必然自证「突破」。
3. **突破/破位的趋势门槛**：同样的形态，在上升趋势里和趋势外是完全相反的
   操作结论，不能只按形态触发。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.radar import indicators as ind


def _bars(closes: list[float]) -> pd.DataFrame:
    """用收盘序列造日线；最低/最高围绕收盘各留 1% 缺口。"""
    n = len(closes)
    c = np.asarray(closes, dtype=float)
    lo = c * 0.99
    hi = c * 1.01
    v = np.full(n, 1_000_000.0)
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=n, freq="D"),
            "open": c,
            "high": hi,
            "low": lo,
            "close": c,
            "volume": v,
        }
    )



# ── 支撑/压力 ────────────────────────────────────────────────────────────


def test_support_skips_clusters_above_price() -> None:
    """现价上方的价位簇要被跳过，继续往下找支撑。

    这条曾经写成 break：聚类升序 + reversed 反扫，第一个簇往往在现价之上，
    于是直接退出、支撑恒为 NaN，整列「距支撑」全空（实测 291 只里 252 只
    被误判成「附近无支撑」）。

    行情取锯齿：价位在 100~109 之间反复回踩，末根收在 105。因此上方有簇、
    下方 5% 处也有簇——正好逼出「跳过上方、继续下扫」这条路径。
    """
    closes = [100.0 + 9.0 * ((i % 10) / 10.0) for i in range(126)]
    df = _bars(closes)
    low, high = df["low"], df["high"]
    last = float(df["close"].iloc[-1])
    assert last == pytest.approx(104.5)

    sup, _n, res = ind.support_resistance(low, high, last)

    assert np.isfinite(sup), "上方有价位簇不应导致支撑判为空"
    assert sup < last, "支撑必须低于现价"
    assert np.isfinite(res) and res > last, "压力必须高于现价"


def test_support_absent_when_never_pulls_back() -> None:
    """半年单边上涨、从不回踩的票，下方没有价位簇 → 支撑为空。"""
    df = _bars([100.0 + i for i in range(126)])
    sup, n, _res = ind.support_resistance(df["low"], df["high"], float(df["close"].iloc[-1]))
    assert not np.isfinite(sup)
    assert n == 0


def test_support_beyond_max_dist_is_rejected() -> None:
    """三倍距离的「历史价位」不该报成支撑。

    前半段在 45~54 反复回踩（半年前的价位区），后半段一路拉到 150+。
    按老规则那簇 44.5 会被报成「距支撑 +237%」——看着像参考位，实则无法执行。
    """
    closes = [45.0 + 9.0 * ((i % 10) / 10.0) for i in range(63)]
    closes += [215.0 - i for i in range(63)]
    df = _bars(closes)
    last = float(df["close"].iloc[-1])
    assert last > 150.0

    sup, _n, _res = ind.support_resistance(df["low"], df["high"], last)
    assert not np.isfinite(sup), "距现价远超 25% 的价位簇不应作为支撑报出"


def test_support_reports_touch_count() -> None:
    """触碰次数要如实报出——调用方（左侧买点）靠它筛强度。"""
    closes = [100.0, 99.0, 98.0, 97.0, 98.0, 99.0, 100.0] * 12 + [100.0] * 50
    df = _bars(closes)
    last = float(df["close"].iloc[-1])
    sup, touches, _res = ind.support_resistance(df["low"], df["high"], last)
    assert np.isfinite(sup)
    assert touches >= 2, "反复回踩同一区间的序列，支撑触碰次数应 ≥2"


# ── 前 N 日高低点不含当天 ─────────────────────────────────────────────────


def test_hi20_excludes_today() -> None:
    """今天创新高时，hi20 必须还是「不含今天」的前 20 日最高。"""
    closes = [100.0] * 30 + [200.0]
    df = _bars(closes)
    m = ind.compute_metrics(df, "X")
    assert m is not None
    assert m.hi20 == pytest.approx(101.0), "hi20 混入了当天的 202"
    assert m.close > m.hi20, "今天的收盘高于前 20 日最高 → 满足突破的价格条件"


# ── 趋势门槛 ─────────────────────────────────────────────────────────────


def test_trend_requires_rising_ma50() -> None:
    """价在 MA50 上方但 MA50 下行 → 不算上升趋势。"""
    rising = _bars([100.0 + i * 2 for i in range(80)])
    m_up = ind.compute_metrics(rising, "X")
    assert m_up is not None
    assert m_up.above50 and m_up.ma50_rising and m_up.trend

    falling = _bars([300.0 - i * 2 for i in range(80)])
    m_dn = ind.compute_metrics(falling, "X")
    assert m_dn is not None
    assert m_dn.above50 is False
    assert m_dn.ma50_rising is False
    assert m_dn.trend is False


def test_aligned_requires_strict_order() -> None:
    """多头排列 = close > MA5 > MA20 > MA50，顺序不能乱也不能取等。"""
    df = _bars([100.0 + i for i in range(80)])
    m = ind.compute_metrics(df, "X")
    assert m is not None
    assert m.ma5 > m.ma20 > m.ma50
    assert m.aligned is True


def test_metrics_none_when_history_too_short() -> None:
    """不足 30 根 K 线算不出 MA20，返回 None 而不是一串 NaN。"""
    assert ind.compute_metrics(_bars([100.0] * 10), "X") is None


def test_overext_threshold_is_strict() -> None:
    """RSI 恰好等于 80 不算超买（参考页写的是 >80）。"""
    m = ind.SymbolMetrics(symbol="X", date=pd.Timestamp("2026-01-01"), close=100.0)
    m.rsi = 80.0
    assert ind.is_overext(m) is False
    m.rsi = 80.1
    assert ind.is_overext(m) is True


def test_volume_spike_threshold_is_inclusive() -> None:
    """量比恰好 1.5 算放量（参考页写的是 ≥1.5）。"""
    m = ind.SymbolMetrics(symbol="X", date=pd.Timestamp("2026-01-01"), close=100.0)
    m.vol_ratio = 1.49
    assert ind.is_volume_spike(m) is False
    m.vol_ratio = 1.5
    assert ind.is_volume_spike(m) is True
