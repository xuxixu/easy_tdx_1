"""MFI 量价反转策略。

MFI < 20（资金流量超卖）买入；MFI > 80（资金流量超买）卖出。
MFI 是成交量的 RSI——把量价关系压缩成一个振荡器，比纯价格 RSI 多了量能维度。

超卖区代表资金大举流出后恐慌见底，超买区代表资金涌入后过热。
适合震荡市中的波段操作。

用法::

    easy-tdx backtest SZ 000001 --strategy-file strategies/mfi_volume.py --count 2000 --table
"""

from easy_tdx import ta
from easy_tdx.backtest import Strategy


class MFIVolumeStrategy(Strategy):
    """MFI 量价反转策略。"""

    def init(self) -> None:
        self.mfi = self.I(
            ta.MFI, self.data.close, self.data.high, self.data.low, self.data.vol,
        )

    def next(self) -> None:
        val = float(self.mfi[self._bar_index])

        # 超卖买入
        if val < 20:
            if self.position["size"] == 0:
                self.buy(size=0)

        # 超买卖出
        elif val > 80:
            if self.position["size"] > 0:
                self.sell(size=0)
