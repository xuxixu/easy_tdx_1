"""叠加 K 线（自定义指标 candle_cols）测试：计算拼装 + option 组装。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.kline_option import (
    ChartItemSpec,
    build_kline_option,
    compute_item_lines,
)


def _df(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(9)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, n))
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=n, freq="B"),
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "vol": rng.uniform(1e6, 5e6, n),
        }
    )


HA_FORMULA = """\
XOPEN := (REF(O,1)+REF(C,1))/2;
XCLOSE := C;
XHIGH := MAX(H,XOPEN);
XLOW := MIN(L,XOPEN);
KO: XOPEN;
KC: XCLOSE;
KH: XHIGH;
KL: XLOW;
UP: MA(C,5);
"""


def test_candle_built_and_skipped_as_lines():
    df = _df()
    item = ChartItemSpec(
        id="c1", formula=HA_FORMULA, pane="main", candle_cols=["KO", "KH", "KL", "KC"]
    )
    mains, subs, candles = compute_item_lines(df, [item])
    assert len(candles) == 1
    assert subs == []
    # K 线四列不再画线，只剩 UP
    assert [m.name for m in mains] == ["UP"]
    rows = candles[0].rows
    assert len(rows) == len(df)
    assert all(r is None or len(r) == 4 for r in rows)
    finite = [r for r in rows if r is not None]
    assert len(finite) > len(df) - 10
    o, c, lo, h = finite[-1]
    assert lo <= min(o, c) and h >= max(o, c)


def test_candle_missing_col_fails_fast():
    df = _df()
    item = ChartItemSpec(id="c1", formula="A: C;", pane="main", candle_cols=["A", "B", "C", "D"])
    with pytest.raises(ValueError, match="缺失数值输出"):
        compute_item_lines(df, [item])


def test_candle_rejects_bad_shape_and_sub_pane():
    df = _df()
    with pytest.raises(ValueError, match="4 列"):
        compute_item_lines(
            df, [ChartItemSpec(id="c1", formula="A: C;", pane="main", candle_cols=["A", "B"])]
        )
    with pytest.raises(ValueError, match="只支持主图"):
        compute_item_lines(
            df,
            [ChartItemSpec(id="c1", formula="A: C;", pane="sub", candle_cols=["A", "B", "C", "D"])],
        )


def test_option_contains_overlay_candlestick():
    df = _df()
    item = ChartItemSpec(
        id="平均K线", formula=HA_FORMULA, pane="main", candle_cols=["KO", "KH", "KL", "KC"]
    )
    mains, subs, candles = compute_item_lines(df, [item])
    n = len(df)
    dates = [str(d.date()) for d in df["datetime"]]
    ohlc = df[["open", "close", "low", "high"]].values.tolist()
    option = build_kline_option(
        dates,
        ohlc,
        df["vol"].tolist(),
        [True] * n,
        mains,
        subs,
        axis_color="#2a2e3a",
        up_color="#ef4146",
        down_color="#18a058",
        candles=candles,
    )
    sticks = [s for s in option["series"] if s.get("type") == "candlestick"]
    assert len(sticks) == 2  # 主 K 线 + 叠加 K 线
    assert option["legend"]["data"][0] == "K线"
    assert "平均K线" in option["legend"]["data"]
    overlay = next(s for s in sticks if s.get("name") == "平均K线")
    assert overlay["xAxisIndex"] == 0
    assert len(overlay["data"]) == n
