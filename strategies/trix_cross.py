"""TRIX 三重平滑趋势策略。

TRIX 上穿信号线（TRIX_MA）买入；下穿卖出。
TRIX 对收盘价做三次 EMA 平滑再算变化率，比 MACD 多一层过滤，
能有效屏蔽短期噪音，减少震荡市的假信号。

适合中长线趋势跟踪，信号比 MACD 更少但更干净。

用法::

    easy-tdx backtest SZ 000001 --strategy-file strategies/trix_cross.py --count 2000 --table
"""

from easy_tdx import ta
from easy_tdx.backtest import Strategy, crossover


class TRIXCrossStrategy(Strategy):
    """TRIX 三重平滑趋势策略。"""

    def init(self) -> None:
        # TRIX 返回 2 个数组: TRIX, TRMA（信号线）
        self.trix, self.trma = self.I(ta.TRIX, self.data.close)
        self.golden = crossover(self.trix, self.trma)
        self.death = crossover(self.trma, self.trix)

    def next(self) -> None:
        if self.golden[self._bar_index] and self.position["size"] == 0:
            self.buy(size=0)
        elif self.death[self._bar_index] and self.position["size"] > 0:
            self.sell(size=0)
