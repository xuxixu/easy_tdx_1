"""OBV 能量潮趋势策略。

OBV 超过 MAOBV（30 日均线）一定缓冲带后确认多头，MAOBV 自身趋势向上时买入。
OBV 跌破 MAOBV 时卖出——资金流向转空即离场。

OBV 是累计成交量指标：价涨加量、价跌减量，反映资金进出方向。
MAOBV 平滑后的趋势比原始 OBV 更稳定，适合过滤噪声。
入场要求 OBV 领先 MAOBV 达到缓冲带幅度，过滤交叉区域的假突破噪声。

用法::

    easy-tdx backtest SZ 000001 --strategy-file strategies/obv_trend.py --count 500 --table
"""

from easy_tdx import ta
from easy_tdx.backtest import Strategy


class OBVTrendStrategy(Strategy):
    """OBV 能量潮趋势策略。"""

    maobv_period: int = 30     # MAOBV 均线周期
    maobv_lookback: int = 20   # MAOBV 趋势判定回溯根数
    obv_buffer: float = 0.02   # OBV 入场缓冲带（2%）

    def init(self) -> None:
        self.obv = self.I(ta.OBV, self.data.close, self.data.vol)
        self.maobv = self.I(ta.MA, self.obv, self.maobv_period)

    def next(self) -> None:
        idx = self._bar_index
        obv = float(self.obv[idx])
        maobv = float(self.maobv[idx])

        # MAOBV 趋势向上：当前值 > N 根前的值
        lookback_idx = max(0, idx - self.maobv_lookback)
        maobv_prev = float(self.maobv[lookback_idx])
        maobv_rising = maobv > maobv_prev

        # 入场：OBV 超过 MAOBV 达缓冲带幅度 且 MAOBV 趋势向上
        if obv > maobv * (1 + self.obv_buffer) and maobv_rising:
            if self.position["size"] == 0:
                self.buy(size=0)

        # 出场：OBV < MAOBV（空头信号）
        elif obv < maobv:
            if self.position["size"] > 0:
                self.sell(size=0)
