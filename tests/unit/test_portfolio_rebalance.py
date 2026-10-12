"""Test RebalanceEngine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.portfolio.optimizer import EqualWeightOptimizer, FactorWeightedOptimizer
from easy_tdx.portfolio.rebalance import RebalanceEngine


def _make_market(n_stocks: int = 10, n_days: int = 120, seed: int = 42) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    data = {}
    for i in range(n_stocks):
        close = 10.0 + np.cumsum(rng.normal(0.01, 0.5, n_days))
        close = np.maximum(close, 1.0)
        data[f"{i:06d}"] = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-01", periods=n_days, freq="D"),
                "open": close,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "vol": rng.integers(1e5, 1e7, n_days).astype(float),
                "amount": close * 1e6,
            }
        )
    return data


class TestRebalanceEngine:
    def test_basic_run(self):
        engine = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            factor_name="momentum_20d",
            n_stocks=5,
            rebalance_freq="M",
            cash=1_000_000,
        )
        result = engine.run(_make_market(), start_date=20240101, end_date=20240430)
        assert len(result.states) > 0
        assert len(result.rebalance_dates) > 0
        assert len(result.equity_curve) > 0
        assert "total_return" in result.performance

    def test_with_factor_weighted(self):
        engine = RebalanceEngine(
            optimizer=FactorWeightedOptimizer(),
            factor_name="momentum_20d",
            n_stocks=5,
        )
        result = engine.run(_make_market(), start_date=20240101, end_date=20240430)
        assert len(result.states) > 0

    def test_empty_data(self):
        result = RebalanceEngine(optimizer=EqualWeightOptimizer()).run({})
        assert result.performance["total_return"] == 0.0

    def test_equity_curve_dates_sorted(self):
        result = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            rebalance_freq="M",
        ).run(_make_market(), start_date=20240101, end_date=20240430)
        dates = result.equity_curve["datetime"].tolist()
        assert dates == sorted(dates)

    def test_trades_recorded(self):
        engine = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            n_stocks=3,
            rebalance_freq="M",
        )
        result = engine.run(_make_market(), start_date=20240101, end_date=20240430)
        assert len(result.trades) > 0
        assert "BUY" in result.trades["direction"].values

    def test_total_trades_matches_trade_rows(self):
        """issue #25: performance['total_trades'] 应等于真实交易笔数，而非天数。"""
        engine = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            n_stocks=3,
            rebalance_freq="M",
        )
        result = engine.run(_make_market(), start_date=20240101, end_date=20240430)
        assert result.performance["total_trades"] == len(result.trades)
        # 修复前 total_trades == len(equity_curve)（天数），明显大于交易笔数
        assert result.performance["total_trades"] != len(result.equity_curve)

    def test_missing_price_does_not_collapse_equity(self):
        """issue #31：已持仓标的当日缺 K 线时，市值不应被记为 0 导致净值假崩塌。

        复现：一只标的在中段缺若干交易日数据，且被持有；修复前该标的缺数据
        的日子市值按 0 计，净值单日暴跌，max_drawdown 荒谬（如 -92%）。
        forward-fill 后用最近已知价估值，净值曲线平滑、max_drawdown 合理。
        """
        data = _make_market(n_stocks=3, n_days=120, seed=7)
        # 让第一只标的中段缺 5 天数据（模拟停牌/日历错位）
        target = "000000"
        df0 = data[target]
        keep_mask = ~df0["datetime"].isin(df0["datetime"].iloc[55:60])
        data[target] = df0[keep_mask].reset_index(drop=True)

        engine = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            n_stocks=3,
            rebalance_freq="M",
            cash=1_000_000,
        )
        result = engine.run(data, start_date=20240101, end_date=20240430)

        ec = result.equity_curve.sort_values("datetime").reset_index(drop=True)
        prev = ec["total"].shift(1)
        pct_chg = (ec["total"] - prev) / prev
        # 无单日 >50% 假崩塌（修复前会出现接近 -100% 的尖刺）
        assert pct_chg.min() > -0.5, f"单日跌幅 {pct_chg.min():.2%} 异常，疑似缺数据假崩塌"
        # 最大回撤合理（< 90%）且为正值
        md = result.performance["max_drawdown"]
        assert 0.0 <= md < 0.9, f"max_drawdown={md:.4f} 不合理"

    def test_max_drawdown_sign_positive(self):
        """issue #31 附带：max_drawdown 应为正值 [0,1]，与 BacktestEngine 约定一致。"""
        engine = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            n_stocks=3,
            rebalance_freq="M",
            cash=1_000_000,
        )
        result = engine.run(_make_market(), start_date=20240101, end_date=20240430)
        md = result.performance["max_drawdown"]
        assert 0.0 <= md <= 1.0, f"max_drawdown={md} 应落在 [0,1]"

    def test_transaction_costs_reduce_equity(self):
        """交易成本必须真的进入净值曲线。

        回归：此前 _rebalance 末尾用 ``cash = total_value - 新持仓市值`` 整行
        覆盖现金，把卖出净额与全部佣金/滑点一并抹除 —— 净值等价于"零成本交易"，
        而 trades_df 照常记录 cost。这里用同一份行情分别跑零成本与高成本，
        高成本版本的期末净值必须更低。
        """
        data = _make_market(n_stocks=5, n_days=120, seed=11)
        free = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            n_stocks=3,
            rebalance_freq="M",
            cash=1_000_000,
            commission=0.0,
            slippage=0.0,
        ).run(data, start_date=20240101, end_date=20240430)
        costly = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            n_stocks=3,
            rebalance_freq="M",
            cash=1_000_000,
            commission=0.01,
            slippage=0.01,
        ).run(data, start_date=20240101, end_date=20240430)

        free_end = float(free.equity_curve["total"].iloc[-1])
        costly_end = float(costly.equity_curve["total"].iloc[-1])
        assert costly_end < free_end, "高昂交易成本未反映到净值（成本被抹除）"

        # 成本同时须体现在 trades_df 的 cost 列
        if len(costly.trades) > 0:
            assert float(costly.trades["cost"].sum()) > 0

    def test_cash_never_negative(self):
        """全仓重置语义下现金不应转负（防止"卖出加、买入减"式重复计价回归）。"""
        engine = RebalanceEngine(
            optimizer=EqualWeightOptimizer(),
            n_stocks=3,
            rebalance_freq="M",
            cash=1_000_000,
        )
        result = engine.run(
            _make_market(n_stocks=4, n_days=120, seed=5),
            start_date=20240101,
            end_date=20240430,
        )
        for st in result.states:
            assert st.cash >= -1e-6, f"{st.date} 现金为负: {st.cash}"
