"""DMI 趋势跟踪策略。

PDI > MDI（多头方向力强）且 ADX > 25（趋势强度足够）时买入。
PDI < MDI 或 ADX < 20 时卖出——方向反转或趋势消失即离场。

DMI 是唯一直接衡量趋势强度的指标：ADX 区分"有趋势可跟"和"震荡别碰"。
适合单边趋势行情，震荡市自动过滤。

用法::

    easy-tdx backtest SZ 000001 --strategy-file strategies/dmi_trend.py --count 2000 --table
"""

from easy_tdx import ta
from easy_tdx.backtest import Strategy


class DMITrendStrategy(Strategy):
    """DMI 趋势跟踪策略。"""

    def init(self) -> None:
        # DMI 返回 4 个数组: PDI, MDI, ADX, ADXR
        self.pdi, self.mdi, self.adx, _ = self.I(
            ta.DMI, self.data.close, self.data.high, self.data.low,
        )

    def next(self) -> None:
        pdi = float(self.pdi[self._bar_index])
        mdi = float(self.mdi[self._bar_index])
        adx = float(self.adx[self._bar_index])

        # 入场：多头方向力强 + 趋势强度足够
        if pdi > mdi and adx > 25:
            if self.position["size"] == 0:
                self.buy(size=0)

        # 出场：方向反转 或 趋势消失
        elif pdi < mdi or adx < 20:
            if self.position["size"] > 0:
                self.sell(size=0)
