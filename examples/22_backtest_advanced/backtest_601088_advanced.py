"""601088（中国神华）高级回测演示。

对比三档执行精度：
  1. 无摩擦（baseline）
  2. 固定百分比滑点 + 即时成交
  3. 方根市场冲击滑点 + TWAP 拆单执行（高级回测）

并对最高精度档做成本归因分析。

用法: python backtest_601088_demo.py
"""
from __future__ import annotations

import sys

# Windows GBK 终端中文输出兜底
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd  # noqa: E402

from easy_tdx import KlineCategory, Market, TdxClient  # noqa: E402
from easy_tdx.ta import MA  # noqa: E402
from easy_tdx.backtest import BacktestEngine, Strategy  # noqa: E402
from easy_tdx.backtest.attribution import AttributionAnalyzer  # noqa: E402
from easy_tdx.backtest.execution import TWAPExecution  # noqa: E402
from easy_tdx.backtest.slippage import PercentSlippage, SquareRootSlippage  # noqa: E402

CODE = "601088"
MARKET = Market.SH
CASH = 1_000_000.0


# ── 策略：MA10/MA30 双均线 + 8% 止损 / 18% 止盈 ──────────────────────────────────
class DualMAStrategy(Strategy):
    def init(self) -> None:
        self.ma10 = self.I(MA, self.data.close, 10)
        self.ma30 = self.I(MA, self.data.close, 30)

    def next(self) -> None:
        if self._bar_index < 30:
            return
        i = self._bar_index
        price = self.data.close[0]
        holding = self.position["size"] > 0

        golden = self.ma10[i] > self.ma30[i] and self.ma10[i - 1] <= self.ma30[i - 1]
        death = self.ma10[i] < self.ma30[i] and self.ma10[i - 1] >= self.ma30[i - 1]

        if golden and not holding:
            # 金叉开多，带止损止盈
            self.buy(size=0, stop_loss=price * 0.92, take_profit=price * 1.18)
        elif death and holding:
            self.sell(size=0)


def fmt_perf(label: str, perf: dict) -> str:
    return (
        f"  {label:<20}"
        f"总收益 {perf['total_return']:>8.2%}  "
        f"年化 {perf['annual_return']:>8.2%}  "
        f"最大回撤 {perf['max_drawdown']:>8.2%}  "
        f"夏普 {perf['sharpe']:>6.3f}"
    )


def main() -> None:
    # ── 1. 数据 ───────────────────────────────────────────────────────────────
    client = TdxClient()
    try:
        df = client.get_security_bars(MARKET, CODE, KlineCategory.DAY, 0, 800)
    finally:
        client.close()

    if len(df) < 60:
        print(f"数据不足: 仅 {len(df)} 根 K 线，需要网络连接通达信服务器")
        return

    df = df.dropna(subset=["close"]).reset_index(drop=True)
    dt_col = "datetime" if "datetime" in df.columns else "date"
    span = f"{df[dt_col].iloc[0]} ~ {df[dt_col].iloc[-1]}"
    print(f"=== {CODE} 高级回测 ===")
    print(f"K 线区间: {span}  共 {len(df)} 根  初始资金: {CASH:,.0f}\n")

    # ── 2. 三档回测对比 ─────────────────────────────────────────────────────────
    runs: list[tuple[str, dict]] = []

    # (a) 无摩擦基线
    r_a = BacktestEngine(DualMAStrategy, cash=CASH).run(df)
    runs.append(("无摩擦基线", r_a.performance))

    # (b) 固定百分比滑点 + 即时成交
    r_b = BacktestEngine(
        DualMAStrategy, cash=CASH, slippage_model=PercentSlippage(rate=0.001)
    ).run(df)
    runs.append(("固定0.1%滑点", r_b.performance))

    # (c) 高级：方根市场冲击 + TWAP 拆单
    r_c = BacktestEngine(
        DualMAStrategy,
        cash=CASH,
        slippage_model=SquareRootSlippage(impact_coeff=0.1),
        execution_model=TWAPExecution(n_bars=3),
    ).run(df)
    runs.append(("方根滑点+TWAP", r_c.performance))

    print("── 性能对比 ──")
    for label, perf in runs:
        print(fmt_perf(label, perf))

    # ── 3. 摩擦成本（基线 vs 高级）──────────────────────────────────────────────
    print("\n── 摩擦成本影响 ──")
    drag = r_a.performance["total_return"] - r_c.performance["total_return"]
    print(f"  高级档相对无摩擦基线收益折损: {drag:.2%}")
    print(f"  高级档交易笔数: {len(r_c.trades)}  (含被拒单 {r_c.trades['rejected'].sum()})")

    # ── 4. 高级档成本归因 ───────────────────────────────────────────────────────
    print("\n── 高级档成本归因 ──")
    att = AttributionAnalyzer(r_c.trades, r_c.equity_curve)
    cost = att.cost_attribution()
    print(f"  区间总收益:           {cost.total_return:>10.2%}")
    print(f"  总交易成本:           {cost.total_trade_cost:>10.0f} 元")
    print(f"    佣金:               {cost.commission_cost:>10.0f} 元")
    print(f"    滑点:               {cost.slippage_cost:>10.0f} 元")
    print(f"    印花税:             {cost.stamp_tax_cost:>10.0f} 元")

    # ── 5. 交易明细（前 8 笔）──────────────────────────────────────────────────
    print("\n── 高级档交易明细（前 8 笔）──")
    cols = ["datetime", "direction", "size", "price", "commission", "slippage"]
    print(r_c.trades[cols].head(8).to_string(index=False))

    # ── 6. 权益曲线尾段 ─────────────────────────────────────────────────────────
    print("\n── 高级档权益曲线（尾 5 日）──")
    print(r_c.equity_curve.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
