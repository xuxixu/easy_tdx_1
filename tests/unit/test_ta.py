"""ta.py 新增指标函数（SAR/VWAP/AROON/FK + V4.3 十六个无未来函数指标）的数值正确性与边界测试。

这些测试针对 ta.py 里函数本身，不经过 indicator.py 注册层。
注册层的端到端覆盖在 test_indicator.py::TestComputeIndicators::test_all_registered_indicators_run。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx import ta


def _ohlcv(n: int = 200, seed: int = 42) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.standard_normal(n) * 0.5)
    high = close + np.abs(rng.standard_normal(n))
    low = close - np.abs(rng.standard_normal(n))
    open_ = low + (high - low) * rng.random(n)
    vol = (rng.random(n) * 1e6 + 1.0).astype(float)  # +1 避免全零
    return open_, high, low, close, vol


class TestSAR:
    """SAR 抛物线转向指标。"""

    def test_returns_same_length(self):
        _, high, low, _, _ = _ohlcv()
        sar = ta.SAR(high, low)
        assert len(sar) == len(high)

    def test_first_bar_is_undefined(self):
        # TA-Lib SAR 首根无前序极值点可依（需先建立初始趋势），输出 NaN；
        # 自第二根起转为实值。旧实现首根直接取 low[0]。
        _, high, low, _, _ = _ohlcv()
        sar = ta.SAR(high, low)
        assert np.isnan(sar[0])
        assert np.isfinite(sar[1:]).all()

    def test_empty_input(self):
        sar = ta.SAR(np.array([]), np.array([]))
        assert len(sar) == 0

    def test_flat_market_no_crash(self):
        # 一字板/停牌：高低价完全相同，不应崩溃或产生 inf
        flat = np.full(50, 10.0)
        sar = ta.SAR(flat, flat)
        assert len(sar) == 50
        assert np.isfinite(sar[1:]).all(), "SAR 不应产生 inf/nan（首值外）"

    def test_rising_market_sar_below_price(self):
        # 持续上涨时 SAR 应在价格下方（上涨止损位）
        high = np.arange(50, dtype=float) + 1
        low = np.arange(50, dtype=float)
        sar = ta.SAR(high, low)
        # 前 5 根建立趋势后，SAR 应低于对应低点
        assert (sar[5:] <= low[5:] + 1e-6).all()

    def test_falling_market_sar_above_price(self):
        # 持续下跌时 SAR 应在价格上方（下跌止损位）
        low = np.array([100 - i for i in range(50)], dtype=float)
        high = low + 1
        sar = ta.SAR(high, low)
        # 确认在某处发生反转（趋势从上涨初判切换）
        # 不强求全程在上方（初判是上涨），但尾部下跌段 SAR 应高于 low
        assert sar[-1] > low[-1]

    def test_reversal_resets_af(self):
        # V 型反转：TA-Lib 在**反转当根**输出 NaN（新极值点尚未确立），
        # 反转后恢复实值且切到下跌止损位（高于后续低点）。
        rise_h = np.arange(25, dtype=float) + 1
        fall_h = np.array([25 - i + 1 for i in range(1, 25)])
        high = np.concatenate([rise_h, fall_h])
        rise_l = np.arange(25, dtype=float)
        fall_l = np.array([25 - i for i in range(1, 25)])
        low = np.concatenate([rise_l, fall_l])
        sar = ta.SAR(high, low)
        assert np.isfinite(sar[1:-1]).all(), "仅反转当根允许 NaN"
        assert sar[-1] > low[-1], "反转后应转为下跌止损位（高于价格）"

    def test_acceleration_factor_capped(self):
        # 长期单边上涨，AF 不应超过 AF_MAX（通过 SAR 增量间接验证不发散）
        high = np.cumsum(np.ones(100)) + 1  # 每根 +1
        low = np.cumsum(np.ones(100))
        sar = ta.SAR(high, low, AF_STEP=0.02, AF_MAX=0.2)
        assert np.isfinite(sar[1:]).all()
        # SAR 全程应在 low 之下（持续上涨不反转）
        valid = sar[2:]
        assert (valid <= low[2:] + 1e-6).all()


class TestVWAP:
    """VWAP 成交量加权均价。"""

    def test_returns_same_length(self):
        _, high, low, close, vol = _ohlcv()
        vwap = ta.VWAP(close, high, low, vol, N=20)
        assert len(vwap) == len(close)

    def test_leading_nan(self):
        # 前 N-1 根应为 nan（rolling 窗口未填满）
        _, high, low, close, vol = _ohlcv()
        vwap = ta.VWAP(close, high, low, vol, N=20)
        assert np.isnan(vwap[:19]).all()
        assert not np.isnan(vwap[19])

    def test_constant_price(self):
        # 价格、量都恒定时，VWAP 应等于典型价格
        n = 50
        close = np.full(n, 10.0)
        high = np.full(n, 11.0)
        low = np.full(n, 9.0)
        vol = np.full(n, 1000.0)
        vwap = ta.VWAP(close, high, low, vol, N=20)
        expected_tp = (11 + 9 + 10) / 3.0  # =10.0
        assert np.allclose(vwap[19:], expected_tp, equal_nan=True)

    def test_uniform_volume_equals_typical_price_mean(self):
        # 等量时 VWAP = 典型价格的 N 日均值
        n = 100
        rng = np.random.default_rng(1)
        close = 100 + rng.standard_normal(n)
        high = close + 1
        low = close - 1
        vol = np.full(n, 500.0)
        tp = (high + low + close) / 3.0
        vwap = ta.VWAP(close, high, low, vol, N=10)
        tp_ma = pd.Series(tp).rolling(10).mean().values
        assert np.allclose(vwap, tp_ma, equal_nan=True)

    def test_zero_volume_returns_nan(self):
        # 全零成交量时，VWAP 应为 nan（除零保护）
        n = 30
        close = np.full(n, 10.0)
        high = np.full(n, 11.0)
        low = np.full(n, 9.0)
        vol = np.zeros(n)
        vwap = ta.VWAP(close, high, low, vol, N=20)
        assert np.isnan(vwap[19:]).all()


class TestAROON:
    """Aroon 阿隆指标。"""

    def test_returns_three_arrays(self):
        _, high, low, _, _ = _ohlcv()
        up, down, osc = ta.AROON(high, low, N=25)
        assert len(up) == len(high)
        assert len(down) == len(high)
        assert len(osc) == len(high)

    def test_range_zero_to_hundred(self):
        # AROON_UP/DOWN 应在 [0, 100] 区间
        _, high, low, _, _ = _ohlcv()
        up, down, _ = ta.AROON(high, low, N=25)
        # TA-Lib AROON 需要 N 个完整周期才出值（前 N-1 根为 NaN）
        valid_up = up[25:]
        valid_down = down[25:]
        assert (valid_up >= 0).all() and (valid_up <= 100).all()
        assert (valid_down >= 0).all() and (valid_down <= 100).all()

    def test_new_high_gives_full_up(self):
        # 在窗口末端创新高时，AROON_UP 应 = 100
        n = 50
        high = np.linspace(1, 30, n)  # 单调上升，末根创新高
        low = high - 0.5
        up, down, _ = ta.AROON(high, low, N=25)
        assert up[-1] == pytest.approx(100.0)

    def test_new_low_gives_full_down(self):
        # 在窗口末端创新低时，AROON_DOWN 应 = 100
        n = 50
        low = np.linspace(30, 1, n)  # 单调下降
        high = low + 0.5
        _, down, _ = ta.AROON(high, low, N=25)
        assert down[-1] == pytest.approx(100.0)

    def test_osc_is_difference(self):
        # OSC = UP - DOWN
        _, high, low, _, _ = _ohlcv()
        up, down, osc = ta.AROON(high, low, N=25)
        assert np.allclose(osc[24:], (up - down)[24:], equal_nan=True)

    def test_leading_nan(self):
        _, high, low, _, _ = _ohlcv()
        up, down, _ = ta.AROON(high, low, N=25)
        # HHVBARS/LLVBARS 在 N-1 根前为 nan
        assert np.isnan(up[:24]).all()


class TestFK:
    """FK 趋势指标（0/1 数值输出，1 = 快线突破趋势外推线）。

    ``slow = EMA(SLOPE(C,21)*20 + C, 42)`` 中的 ``*20`` 恰好抵消 EMA(42) 的
    滞后量（约 20.5 根），因此当 21 周期斜率平稳时 ``slow ≈ C``、``fast ≈ C``，
    两条线**数值上恒等**。FK 真正度量的是「近期实际斜率 vs 21 周期平均斜率」
    的背离，属动量/反转检测，不是趋势方向判断。

    两个易踩的坑（测试已固化）：
    1. **平稳趋势是退化用例**：完美线性序列下 fast ≡ slow，FK 恒为 0
       （旧实现在此处的 True 只是浮点误差的巧合）。
    2. 慢线是 EMA(42)，叠加 SLOPE 的 21 根预热，需 60 根以上才有实值。
    """

    def test_returns_zero_one_array(self):
        close = _ohlcv()[3]
        fk = ta.FK(close)
        assert len(fk) == len(close)
        assert fk.dtype == np.float64
        finite = fk[np.isfinite(fk)]
        assert set(np.unique(finite).tolist()) <= {0.0, 1.0}

    def test_smooth_trend_is_degenerate_tie(self):
        # 完美线性趋势：快慢线恒等 → 恒为 0（退化但不应崩溃/出 NaN）
        close = np.cumsum(np.ones(300))
        fk = ta.FK(close)
        assert np.isfinite(fk).all()
        assert np.all(fk == 0.0)

    def test_noisy_series_produces_both_states(self):
        # 有波动时短期斜率与 21 周期平均斜率背离 → 0/1 交替给出真实信号
        rng = np.random.default_rng(6)
        close = np.array([500.0]) + np.cumsum(-np.ones(300) + rng.normal(0, 0.5, 300))
        fk = ta.FK(close)
        assert {0.0, 1.0} == set(np.unique(fk).tolist())


# ═══════════════════════════════════════════════════════════════════════════
# V4.3 新增：16 个无未来函数指标
# ═══════════════════════════════════════════════════════════════════════════

#: 新指标的构造器：统一接收 (open, high, low, close, vol) 五元组，返回输出元组。
#: 用于「无未来函数」前缀一致性回归（见 TestNoLookahead）。
_V43_INDICATORS = {
    "HMA": lambda o, h, lo, c, v: (ta.HMA(c, 16),),
    "KAMA": lambda o, h, lo, c, v: (ta.KAMA(c),),
    "SUPERTREND": lambda o, h, lo, c, v: ta.SUPERTREND(c, h, lo),
    "CHANDELIER": lambda o, h, lo, c, v: ta.CHANDELIER(c, h, lo),
    "ICHIMOKU": lambda o, h, lo, c, v: ta.ICHIMOKU(h, lo, c),
    "UOS": lambda o, h, lo, c, v: ta.UOS(c, h, lo),
    "CMO": lambda o, h, lo, c, v: (ta.CMO(c),),
    "TSI": lambda o, h, lo, c, v: ta.TSI(c),
    "FISHER": lambda o, h, lo, c, v: ta.FISHER(h, lo),
    "SQUEEZE": lambda o, h, lo, c, v: ta.SQUEEZE(c, h, lo),
    "CHOP": lambda o, h, lo, c, v: (ta.CHOP(h, lo, c),),
    "AD": lambda o, h, lo, c, v: (ta.AD(c, h, lo, v),),
    "CMF": lambda o, h, lo, c, v: (ta.CMF(c, h, lo, v),),
    "EFI": lambda o, h, lo, c, v: (ta.EFI(c, v),),
    "BBP": lambda o, h, lo, c, v: (ta.BBP(c),),
    "BBW": lambda o, h, lo, c, v: (ta.BBW(c),),
}


class TestNoLookahead:
    """无未来函数回归：指标在全序列上前缀段输出 == 仅用前缀数据计算的输出。

    未来函数（如 ZIG）的致命特征是：后到的数据会改写历史输出。本测试
    把 200 根 K 线截断到前 120 根，两组输出在重叠段必须逐位一致——
    任何引用了 t+1 及之后数据的实现都会当场爆红。
    """

    PREFIX = 120

    @pytest.mark.parametrize("name", sorted(_V43_INDICATORS))
    def test_prefix_stability(self, name):
        ohlcv = _ohlcv(200)
        full = _V43_INDICATORS[name](*ohlcv)
        part = _V43_INDICATORS[name](*[x[: self.PREFIX] for x in ohlcv])
        for j, (f, p) in enumerate(zip(full, part)):
            # ICHIMOKU 迟行带引用未来数据画图（文档已声明仅作图示），
            # 它是唯一允许前缀不一致的输出，单独跳过（见 TestICHIMOKU）。
            if name == "ICHIMOKU" and j == 4:
                continue
            assert np.allclose(f[: self.PREFIX], p, equal_nan=True), (
                f"{name} 输出#{j} 前缀不一致：疑似引用了未来数据"
            )


class TestHMA:
    def test_warmup_and_length(self):
        close = _ohlcv()[3]
        hma = ta.HMA(close, 16)
        assert len(hma) == len(close)
        assert np.isnan(hma[:14]).all()  # 最内层 WMA(16) 窗口预热
        assert not np.isnan(hma[19])

    def test_rising_market_follows_price(self):
        close = np.arange(100, dtype=float) * 0.5 + 10
        hma = ta.HMA(close, 16)
        # 单边上涨中低滞后均线应贴在价格下方且不发散
        assert (hma[20:] <= close[20:] + 1e-6).all()
        assert hma[-1] > close[-2]  # 跟随上涨


class TestKAMA:
    def test_warmup_starts_at_n(self):
        close = _ohlcv()[3]
        kama = ta.KAMA(close, N=10)
        assert np.isnan(kama[:10]).all()
        assert not np.isnan(kama[10])

    def test_strong_trend_hugs_price(self):
        # 单边强趋势：效率比≈1，KAMA 平滑系数取快速极值，稳态滞后 ≈ (1-sc)/sc ≈ 1.25 根
        close = np.cumsum(np.ones(100))  # 每根 +1 的完美趋势
        kama = ta.KAMA(close, N=10)
        assert np.abs(kama[-1] - close[-1]) < 2.0

    def test_flat_market_flat_kama(self):
        kama = ta.KAMA(np.full(60, 10.0), N=10)
        assert np.allclose(kama[10:], 10.0)


class TestSUPERTREND:
    def test_direction_values(self):
        _, high, low, close, _ = _ohlcv()
        st, direction = ta.SUPERTREND(close, high, low)
        # TA-Lib 约定：-1 多头 / +1 空头，预热未确立趋势时为 0
        assert set(np.unique(direction).tolist()) <= {-1.0, 0.0, 1.0}
        assert {1.0, -1.0} <= set(np.unique(direction).tolist()), "样本内应出现双向翻转"
        # TA-Lib 需 N 个周期回看才给出趋势线，前 N-1 根为 NaN
        assert np.isnan(st[:10]).all()
        assert np.isfinite(st[10:]).all()

    def test_rising_market_st_below_price(self):
        # 持续上涨：趋势为多，ST（下轨）应持续低于最低价
        high = np.arange(80, dtype=float) + 1
        low = np.arange(80, dtype=float)
        close = high.copy()
        st, direction = ta.SUPERTREND(close, high, low, N=10, M=3.0)
        assert direction[-1] == 1
        assert (st[10:] <= low[10:] + 1e-6).all()

    def test_reversal_flips_direction(self):
        # V 型反转：方向必须从 1 翻到 -1
        half = np.arange(40, dtype=float)
        close = np.concatenate([half + 1, 40 - half])
        high = close + 0.5
        low = close - 0.5
        _, direction = ta.SUPERTREND(close, high, low)
        assert direction[0] != direction[-1]

    def test_empty_input(self):
        st, direction = ta.SUPERTREND(np.array([]), np.array([]), np.array([]))
        assert len(st) == 0 and len(direction) == 0


class TestCHANDELIER:
    def test_stops_bracket_price(self):
        _, high, low, close, _ = _ohlcv()
        long_stop, short_stop = ta.CHANDELIER(close, high, low, N=22, M=22, K=3.0)
        # 吊灯止损锚定通道极值：多头止损在 N 日最高价下方、空头止损在 N 日最低价上方
        # （下跌段中 long_stop 可以高于当根 high——这正是吊灯线滞后等待离场的行为）
        valid = slice(22, None)  # TR[0] 为 NaN（REF 前收盘缺失）→ ATR 自 22 起有效
        assert (long_stop[valid] < ta.HHV(high, 22)[valid]).all()
        assert (short_stop[valid] > ta.LLV(low, 22)[valid]).all()

    def test_matches_manual_formula(self):
        _, high, low, close, _ = _ohlcv()
        long_stop, _ = ta.CHANDELIER(close, high, low, N=22, M=22, K=2.0)
        expected = ta.HHV(high, 22) - ta.ATR(close, high, low, 22) * 2.0
        assert np.allclose(long_stop, expected, equal_nan=True)


class TestICHIMOKU:
    def test_five_outputs_lengths(self):
        _, high, low, close, _ = _ohlcv()
        outs = ta.ICHIMOKU(high, low, close)
        assert len(outs) == 5
        for arr in outs:
            assert len(arr) == len(close)

    def test_tenkan_formula(self):
        _, high, low, close, _ = _ohlcv()
        tenkan, _, _, _, _ = ta.ICHIMOKU(high, low, close, P1=9, P2=26, P3=52)
        expected = (ta.HHV(high, 9) + ta.LLV(low, 9)) / 2
        assert np.allclose(tenkan, expected, equal_nan=True)

    def test_span_is_shifted_past(self):
        # 先行带 = 26 期前的 (转换线+基准线)/2：i 处的值来自 i-26（过去）
        _, high, low, close, _ = _ohlcv()
        _, _, span_a, _, _ = ta.ICHIMOKU(high, low, close, P1=9, P2=26, P3=52, SHIFT=26)
        tenkan = (ta.HHV(high, 9) + ta.LLV(low, 9)) / 2
        kijun = (ta.HHV(high, 26) + ta.LLV(low, 26)) / 2
        raw = (tenkan + kijun) / 2
        assert np.allclose(span_a[26:], raw[:-26], equal_nan=True)

    def test_chikou_tail_nan(self):
        # 迟行带 = 当前收盘画回 26 期前：末尾 26 个槽位无对应未来数据 → NaN
        _, high, low, close, _ = _ohlcv()
        *_, chikou = ta.ICHIMOKU(high, low, close)
        assert np.isnan(chikou[-26:]).all()
        assert not np.isnan(chikou[:-26]).any()


class TestUOS:
    def test_range_zero_to_hundred(self):
        _, high, low, close, _ = _ohlcv()
        uos, uos_ma = ta.UOS(close, high, low)
        valid = uos[28:]  # bp[0] 为 NaN（REF 前收盘缺失）→ P3=28 窗口自 28 起有效
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_new_low_oversold(self):
        # 持续创新低 → UOS 应处于超卖区（<50）
        low = np.linspace(50, 1, 60)
        close = low.copy()
        high = low + 0.5
        uos, _ = ta.UOS(close, high, low)
        assert uos[-1] < 50

    def test_flat_market_neutral(self):
        flat = np.full(60, 10.0)
        uos, _ = ta.UOS(flat, flat, flat)
        assert np.allclose(uos[28:], 50.0, equal_nan=True)  # 除零保护取中性


class TestCMO:
    def test_symmetric_range(self):
        close = _ohlcv()[3]
        cmo = ta.CMO(close, N=14)
        valid = cmo[14:]
        assert (valid >= -100).all() and (valid <= 100).all()

    def test_rising_positive_falling_negative(self):
        rise = np.cumsum(np.ones(100))
        assert ta.CMO(rise, N=14)[-1] > 0  # 纯上涨 → +100 极值
        fall = 100 - np.cumsum(np.ones(100))
        assert ta.CMO(fall, N=14)[-1] < 0  # 纯下跌 → -100 极值


class TestTSI:
    def test_signal_line_follows(self):
        close = _ohlcv()[3]
        tsi, signal = ta.TSI(close)
        assert len(tsi) == len(signal) == len(close)
        valid = ~np.isnan(tsi) & ~np.isnan(signal)
        assert valid.any()

    def test_strong_rise_positive(self):
        close = np.cumsum(np.ones(100))
        tsi, _ = ta.TSI(close)
        assert tsi[-1] > 0


class TestFISHER:
    def test_trigger_is_prev_value(self):
        _, high, low, _, _ = _ohlcv()
        fisher, trigger = ta.FISHER(high, low, N=9)
        assert np.allclose(trigger[1:], fisher[:-1], equal_nan=True)

    def test_strong_rise_positive_sharply(self):
        high = np.linspace(1, 50, 100)
        low = high - 0.5
        fisher, _ = ta.FISHER(high, low, N=9)
        assert fisher[-1] > 1.0  # 顶部区域输出尖峰
        assert np.isfinite(fisher[8:]).all()  # 钳制保证无 inf

    def test_bounded_input_clamp(self):
        # 归一化值被钳制在 ±0.999 → 输出有限
        _, high, low, _, _ = _ohlcv()
        fisher, _ = ta.FISHER(high, low, N=3)
        assert np.isfinite(fisher[2:]).all()


class TestSQUEEZE:
    def test_zero_one_flag_and_mom_length(self):
        _, high, low, close, _ = _ohlcv()
        sqz, mom = ta.SQUEEZE(close, high, low)
        assert len(sqz) == len(mom) == len(close)
        finite = sqz[np.isfinite(sqz)]
        assert set(np.unique(finite).tolist()) <= {0.0, 1.0}, "挤压标志以 0/1 数值输出"

    def test_flat_market_mom_zero(self):
        flat = np.full(60, 10.0)
        _, mom = ta.SQUEEZE(flat, flat, flat)
        # 双层 N=20 窗口（带宽层 + 回归层）→ 有效值自 2N-1 起
        assert np.allclose(mom[39:], 0.0, atol=1e-9)


class TestCHOP:
    def test_range_and_warmup(self):
        _, high, low, close, _ = _ohlcv()
        chop = ta.CHOP(high, low, close, N=14)
        # TR[0] 取 H-L（自洽的首根定义），故 N=14 的滚动和自第 13 根起有效
        assert np.isnan(chop[:13]).all()
        valid = chop[13:]
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_strong_trend_low_chop(self):
        # 完美趋势：ΣTR ≈ 区间 → chop 趋近低值
        high = np.arange(1, 81, dtype=float)
        low = high - 1
        close = high.copy()
        chop = ta.CHOP(high, low, close, N=14)
        assert chop[-1] < 30

    def test_oscillation_high_chop(self):
        # 剧烈往返震荡（窗口跨 2 个以上完整周期）：路径远大于区间 → chop 高
        t = np.arange(200)
        close = 10 + 5 * np.sin(2 * np.pi * t / 6)
        high = close + 0.5
        low = close - 0.5
        chop = ta.CHOP(high, low, close, N=14)
        assert chop[14:].max() > 55


class TestADandCMF:
    def test_ad_manual_clv(self):
        # 单根：CLV=((C-L)-(H-C))/(H-L)，AD=CLV×VOL 累计；C=11.5 → CLV=(1.5-0.5)/2=0.5
        close = np.array([11.5, 11.5])
        high = np.array([12.0, 12.0])
        low = np.array([10.0, 10.0])
        vol = np.array([100.0, 100.0])
        ad = ta.AD(close, high, low, vol)
        assert ad[0] == pytest.approx(0.5 * 100)
        assert ad[1] == pytest.approx(100.0)

    def test_cmf_range_and_warmup(self):
        _, high, low, close, vol = _ohlcv()
        cmf = ta.CMF(close, high, low, vol, N=20)
        assert np.isnan(cmf[:19]).all()
        valid = cmf[19:]
        assert (valid >= -1).all() and (valid <= 1).all()

    def test_cmf_sign_matches_close_position(self):
        # 收盘持续靠近最高价（吸筹）→ CMF 为正
        n = 60
        close = np.linspace(10, 20, n)
        high = close + 0.1
        low = close - 1.0  # 收盘贴近最高
        vol = np.full(n, 1000.0)
        cmf = ta.CMF(close, high, low, vol, N=20)
        assert cmf[-1] > 0


class TestEFI:
    def test_rising_with_volume_positive(self):
        n = 100
        close = np.cumsum(np.ones(n))
        vol = np.full(n, 1000.0)
        efi = ta.EFI(close, vol, N=13)
        assert efi[-1] > 0

    def test_length_and_warmup(self):
        close = _ohlcv()[3]
        vol = _ohlcv()[4]
        efi = ta.EFI(close, vol, N=13)
        assert len(efi) == len(close)
        assert np.isnan(efi[0])  # DIFF 首位 NaN


class TestBBPandBBW:
    def test_bbp_position_semantics(self):
        # N=3 手工窗口 [10, 14, x]：mid=12、std=sqrt(8/3)；close=mid → %B 恰为 50
        c_mid = np.array([10.0, 14.0, 12.0])
        assert ta.BBP(c_mid, N=3, P=2)[-1] == pytest.approx(50.0, abs=1e-6)
        # 位置单调：同一窗口形态下，收盘越高 %B 越大
        lo = ta.BBP(np.array([10.0, 14.0, 11.0]), N=3, P=2)[-1]
        hi = ta.BBP(np.array([10.0, 14.0, 13.0]), N=3, P=2)[-1]
        assert lo < 50.0 < hi
        # 公式口径：直接用 numpy 独立重算 (C-(mid-2sd))/(4sd)*100（RD 三位小数舍入）
        window = np.array([10.0, 14.0, 13.0])
        mid, sd = window.mean(), window.std()
        expected = (13.0 - (mid - 2 * sd)) / (4 * sd) * 100
        assert ta.BBP(window, N=3, P=2)[-1] == pytest.approx(expected, abs=1e-3)

    def test_bbw_zero_when_flat(self):
        bbw = ta.BBW(np.full(60, 10.0), N=20, P=2)
        assert np.allclose(bbw[19:], 0.0)

    def test_bbw_grows_with_volatility(self):
        rng = np.random.default_rng(7)
        quiet = 100 + rng.standard_normal(60) * 0.1
        wild = 100 + rng.standard_normal(60) * 5.0
        assert ta.BBW(wild)[-1] > ta.BBW(quiet)[-1]


class TestFilter:
    """FILTER 无副作用（审查修复：曾原地改写输入序列）。"""

    def test_filter_does_not_mutate_input(self):
        x = np.array([1.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0])
        snapshot = x.copy()
        out = ta.FILTER(x, 2)
        np.testing.assert_array_equal(x, snapshot)  # 旧码把 x 原地置零，失败
        # x[0]=1 触发 → 后 2 根置零；x[3]=1 触发 → 后 2 根置零；x[6]=1
        np.testing.assert_array_equal(out, [1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0])

    def test_filter_accepts_bool_input(self):
        s = np.array([True, False, True, True])
        out = ta.FILTER(s, 1)
        np.testing.assert_array_equal(s, [True, False, True, True])
        # 引擎统一以 float64 输出（布尔序列提升为 1.0/0.0）
        assert out.dtype == np.float64
        # s[0]=True 触发 → s[1] 置零；s[2]=True 触发 → s[3] 置零（s[2] 本身保留）
        np.testing.assert_array_equal(out, [1.0, 0.0, 1.0, 0.0])

    def test_filter_formula_series_not_polluted(self):
        """公式场景：FILTER(C, N) 后 C 仍是原收盘序列。"""
        from easy_tdx.formula import compile_formula

        n = 30
        close = 10.0 * np.linspace(1.0, 2.0, n)
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-01", periods=n),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "vol": np.ones(n),
            }
        )
        res = compile_formula("A: FILTER(C, 2); B: MA(C, 2);").compute(df)
        np.testing.assert_allclose(
            res.columns["B"], pd.Series(close).rolling(2).mean().to_numpy(), equal_nan=True
        )
