"""MTM 动量策略。

MTM 上穿 0 买入（动量由负转正，下跌动能耗尽）；MTM 下穿 0 卖出（动量由正转负）。
MTM = 当前价 - N 日前价格，最纯粹的动量指标。

信号极其灵敏，适合捕捉趋势拐点。代价是震荡市假信号多——
可以配合其他趋势过滤器使用，这里先展示最简版本。

用法::

    easy-tdx backtest SZ 000001 --strategy-file strategies/mtm_momentum.py --count 2000 --table
"""

from easy_tdx import ta
from easy_tdx.backtest import Strategy, crossover


class MTMMomentumStrategy(Strategy):
    """MTM 动量策略。"""

    def init(self) -> None:
        # MTM 返回 2 个数组: MTM, MTMMA
        self.mtm, self.mtm_ma = self.I(ta.MTM, self.data.close)
        # 用 MTM 上穿 0 线作为买入信号，下穿 0 线作为卖出信号
        zeros = [0.0] * len(self.data.close)
        self.buy_signal = crossover(self.mtm, zeros)
        self.sell_signal = crossover(zeros, self.mtm)

    def next(self) -> None:
        if self.buy_signal[self._bar_index] and self.position["size"] == 0:
            self.buy(size=0)
        elif self.sell_signal[self._bar_index] and self.position["size"] > 0:
            self.sell(size=0)
