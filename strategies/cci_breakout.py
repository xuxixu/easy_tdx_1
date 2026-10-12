"""CCI 区间突破策略。

CCI 上穿 +100 时买入（进入强势区间）；下穿 -100 时卖出（进入弱势区间）。
CCI 衡量价格偏离统计平均的程度：|CCI| > 100 代表偏离显著。

和 RSI 超买超卖不同，CCI 突破是顺势策略——突破 +100 追多，不是超买反转。
适合从震荡转入趋势的启动阶段。

用法::

    easy-tdx backtest SZ 000001 --strategy-file strategies/cci_breakout.py --count 2000 --table
"""

from easy_tdx import ta
from easy_tdx.backtest import Strategy


class CCIBreakoutStrategy(Strategy):
    """CCI 区间突破策略。"""

    def init(self) -> None:
        self.cci = self.I(
            ta.CCI, self.data.close, self.data.high, self.data.low,
        )

    def next(self) -> None:
        val = float(self.cci[self._bar_index])

        # 入场：CCI 进入强势区间
        if val > 100:
            if self.position["size"] == 0:
                self.buy(size=0)

        # 出场：CCI 跌入弱势区间
        elif val < -100:
            if self.position["size"] > 0:
                self.sell(size=0)
