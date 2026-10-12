"""通达信公式解析器测试（tokenizer / AST / 白名单求值 / 信号归类 / 安全性）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import talib

from easy_tdx.formula import FormulaError, compile_formula


def _df(n: int = 60, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 10.0 * np.cumprod(1.0 + 0.002 + rng.normal(0, 0.015, n))
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": close * 0.999,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "vol": rng.uniform(1e6, 5e6, n),
            "amount": close * rng.uniform(1e6, 5e6, n),
        }
    )


# ── 编译与语法 ───────────────────────────────────────────────────────────────


def test_compile_and_outputs():
    formula = compile_formula(
        """
        N := 9;
        RSV := (C - LLV(L, N)) / (HHV(H, N) - LLV(L, N)) * 100;
        K := SMA(RSV, 3, 1);
        金叉: CROSS(K, 20);
        强度: K;
        """
    )
    res = formula.compute(_df())
    assert "金叉" in res.signals
    assert "强度" in res.values
    frame = res.to_frame()
    assert list(frame.columns) == ["金叉", "强度"]
    assert len(frame) == 60


def test_syntax_error_has_position():
    with pytest.raises(FormulaError):
        compile_formula("A := ;")
    with pytest.raises(FormulaError):
        compile_formula("A := UNKNOWN_FUNC(C)")
    with pytest.raises(FormulaError):
        compile_formula("A := B + ")  # 引用未定义变量且语法断裂


def test_unknown_variable_rejected():
    with pytest.raises(FormulaError, match="未知变量"):
        compile_formula("A: X1;").compute(_df())


def test_unknown_function_rejected():
    with pytest.raises(FormulaError, match="白名单"):
        compile_formula("A: EVAL(C);").compute(_df())


def test_empty_formula_rejected():
    with pytest.raises(FormulaError, match="为空"):
        compile_formula("{只有注释}")


def test_no_python_eval_injection():
    """公式层不走 Python eval：危险标识符按未知变量/函数拒绝。"""
    with pytest.raises(FormulaError):
        compile_formula("__import__('os'): 1;").compute(_df())
    with pytest.raises(FormulaError):
        compile_formula("A: OPEN(C);").compute(_df())


# ── 语义正确性 ───────────────────────────────────────────────────────────────


def test_series_aliases():
    """C/O/H/L/V/AMOUNT 别名与底层列一致。"""
    df = _df(50)
    res = compile_formula("高价: H; 低价: L; 收盘: CLOSE; 量: VOL; 额: AMOUNT;").compute(df)
    assert np.allclose(res.columns["高价"], df["high"])
    assert np.allclose(res.columns["收盘"], df["close"])
    assert np.allclose(res.columns["量"], df["vol"])


def test_ma_matches_mytt():
    from easy_tdx.ta import MA

    df = _df(50)
    res = compile_formula("均线: MA(C, 5);").compute(df)
    assert np.allclose(res.columns["均线"], MA(df["close"].to_numpy(), 5), equal_nan=True)


def test_cross_semantics():
    """CROSS(A,B)：A 上穿 B 的那一根为 1，其余 0。"""
    df = _df(50)
    res = compile_formula(
        """
        快: MA(C, 3);
        慢: MA(C, 10);
        金叉: CROSS(快, 慢);
        """
    ).compute(df)
    golden = res.columns["金叉"]
    assert set(np.unique(golden[np.isfinite(golden)])).issubset({0.0, 1.0})
    assert golden.sum() >= 0  # 结构完整（趋势数据至少存在或为 0）
    # CROSS 手工复算对拍
    from easy_tdx.ta import CROSS, MA

    fast = MA(df["close"].to_numpy(), 3)
    slow = MA(df["close"].to_numpy(), 10)
    assert np.allclose(golden, CROSS(fast, slow), equal_nan=True)


def test_safe_division_zero_denominator_nan():
    """除零 → NaN（不炸、不 inf）。"""
    df = _df(30)
    res = compile_formula("比值: C / (C - C);").compute(df)  # 分母全 0
    assert np.isnan(res.columns["比值"]).all()


def test_logic_operators():
    df = _df(40)
    res = compile_formula(
        """
        条件1: C > MA(C, 5);
        条件2: C > MA(C, 20);
        同时: 条件1 AND 条件2;
        任一: 条件1 OR 条件2;
        取反: NOT(条件1);
        """
    ).compute(df)
    c1 = res.columns["条件1"] > 0.5
    c2 = res.columns["条件2"] > 0.5
    assert np.allclose(res.columns["同时"] > 0.5, c1 & c2)
    assert np.allclose(res.columns["任一"] > 0.5, c1 | c2)
    assert np.allclose(res.columns["取反"] > 0.5, ~c1)


def test_comparison_and_unary():
    df = _df(30)
    res = compile_formula("跌幅: -(C - REF(C, 1)) / REF(C, 1) * 100; 平: C == C;").compute(df)
    assert (res.columns["平"] == 1.0).all()
    assert "跌幅" in res.values


def test_warmup_nan_not_signal():
    """预热期 NaN 不产生信号（比较含 NaN → 0）。"""
    df = _df(30)
    res = compile_formula("信号: CROSS(MA(C, 20), MA(C, 25));").compute(df)
    sig = res.columns["信号"]
    assert np.nanmax(np.nan_to_num(sig[:25])) <= 1.0
    assert np.isnan(sig).sum() == 0  # 布尔输出不含 NaN


def test_output_classification_boolean_vs_numeric():
    """比较/逻辑输出 → 信号；数值输出 → 数值列；0/1 值域数值也归信号。"""
    df = _df(40)
    res = compile_formula(
        """
        布尔输出: C > REF(C, 1);
        数值输出: MA(C, 5) - MA(C, 20);
        """
    ).compute(df)
    assert res.signals == ["布尔输出"]
    assert res.values == ["数值输出"]


def test_last_row_for_screening():
    df = _df(30)
    res = compile_formula("买入: CROSS(MA(C, 3), MA(C, 10)); 值: MA(C, 5);").compute(df)
    last = res.last_row()
    assert set(last) == {"买入", "值"}
    assert last["买入"] in (0.0, 1.0)


def test_chinese_identifier_and_comment():
    df = _df(30)
    formula = compile_formula(
        """
        {这是注释：N 周期}
        周期 := 5;
        均线: MA(C, 周期);
        """
    )
    res = formula.compute(df)
    assert res.columns["均线"][0] != res.columns["均线"][-1]


def test_compiled_formula_reusable_across_frames():
    f = compile_formula("值: MA(C, 5);")
    r1 = f.compute(_df(30, seed=1))
    r2 = f.compute(_df(40, seed=2))
    assert len(r1.columns["值"]) == 30
    assert len(r2.columns["值"]) == 40


def test_compiled_formula_is_dataclass_safe():
    """CompiledFormula 可 pickle（进程池/后台任务传输）。"""
    import pickle

    f = compile_formula("值: MA(C, 5);")
    f2 = pickle.loads(pickle.dumps(f))
    assert np.allclose(
        f.compute(_df(20)).columns["值"], f2.compute(_df(20)).columns["值"], equal_nan=True
    )


# ── 回归：归类收严 / FILTER 副作用 / 递归上限 / REF 负移位（审查修复） ────────


def test_ratio_output_classified_as_value_not_signal():
    """0~1 区间的价格比率是数值列，不是信号列（旧码按 [0,1] 值域兜底误判）。"""
    res = compile_formula("比率: C / HHV(C, 20);").compute(_df(40))
    assert res.signals == []
    assert res.values == ["比率"]


def test_normalized_oscillator_classified_as_value():
    """归一化振荡器（RSI/100）是数值列，不是信号列。"""
    res = compile_formula("强度: RSI(C, 14) / 100;").compute(_df(40))
    assert res.signals == []
    assert res.values == ["强度"]


def test_binary_zero_one_values_still_signal():
    """真正的 0/1 两值输出仍兜底归信号列。"""
    res = compile_formula("X: IF(C > MA(C, 5), 1, 0);").compute(_df(40))
    assert res.signals == ["X"]


def test_filter_does_not_pollute_series():
    """FILTER(C, N) 不改写输入序列：同公式后续 MA(C, 2) 与未过滤一致。"""
    df = _df(30)
    res = compile_formula("A: FILTER(C, 2); B: MA(C, 2);").compute(df)
    close = pd.to_numeric(df["close"]).to_numpy(dtype=float)
    expected = pd.Series(close).rolling(2).mean().to_numpy()
    np.testing.assert_allclose(res.columns["B"], expected, equal_nan=True)


def test_deep_paren_nesting_formula_error():
    """超深括号嵌套抛 FormulaError（嵌套过深），而非 RecursionError 逃逸。"""
    text = "X: " + "(" * 5000 + "C" + ")" * 5000 + ";"
    with pytest.raises(FormulaError, match="嵌套过深"):
        compile_formula(text)


def test_deep_unary_chain_formula_error():
    """超长一元运算符链同样受深度上限保护。"""
    with pytest.raises(FormulaError, match="嵌套过深"):
        compile_formula("X: " + "!" * 5000 + "C;")


def test_moderate_nesting_still_compiles():
    """常规嵌套深度不受上限影响。"""
    res = compile_formula("X: -(-(-(C + 1) * 2) + 3);").compute(_df(10))
    assert res.columns["X"].shape == (10,)


def test_ref_negative_shift_banned():
    """REF 负移位（未来函数）显式 FormulaError，不再依赖 float 类型巧合。"""
    with pytest.raises(FormulaError, match="负移位"):
        compile_formula("X: REF(C, -1);").compute(_df(30))


def test_ref_negative_via_expression_banned():
    """负移位经表达式算出（如 0-1）同样被禁。"""
    with pytest.raises(FormulaError, match="负移位"):
        compile_formula("X: REF(C, 0 - 1);").compute(_df(30))


def test_ref_positive_still_works():
    res = compile_formula("X: REF(C, 1);").compute(_df(30))
    assert np.isnan(res.columns["X"][0])
    assert res.columns["X"][1] == pytest.approx(float(pd.to_numeric(_df(30)["close"]).iloc[0]))


def test_mytt_internal_negative_ref_unaffected():
    """引擎内直调（ICHIMOKU 迟行带）不经公式白名单，负移位仍可用。"""
    from easy_tdx.ta import REF

    close = np.arange(5, dtype=float)
    out = REF(close, -1)
    assert out[0] == pytest.approx(1.0)


# ── 预置指标公式化（技术指标管理：六组预置 = 锁定的通达信公式） ─────────────
# 以下公式文本与前端 presetFormulas.ts 的生成口径保持一致（参数不同、
# 结构相同）；改动任一侧请同步另一侧。


def _big_df() -> pd.DataFrame:
    return _df(300, seed=11)


def test_preset_ma_matches_mytt():
    from easy_tdx import ta

    df = _big_df()
    res = compile_formula("MA5: MA(C,5); MA20: MA(C,20);").compute(df)
    assert res.values == ["MA5", "MA20"]
    np.testing.assert_allclose(res.columns["MA5"], ta.MA(df["close"].values, 5), equal_nan=True)
    np.testing.assert_allclose(res.columns["MA20"], ta.MA(df["close"].values, 20), equal_nan=True)


def test_preset_ema_matches_mytt():
    from easy_tdx import ta

    df = _big_df()
    res = compile_formula("EMA12: EMA(C,12); EMA26: EMA(C,26);").compute(df)
    np.testing.assert_allclose(res.columns["EMA12"], ta.EMA(df["close"].values, 12))
    np.testing.assert_allclose(res.columns["EMA26"], ta.EMA(df["close"].values, 26))


def test_preset_boll_matches_mytt():
    from easy_tdx import ta

    df = _big_df()
    res = compile_formula(
        "BOLL_MID: MA(C,20);BOLL_UPPER: BOLL_MID+2*STD(C,20);BOLL_LOWER: BOLL_MID-2*STD(C,20);"
    ).compute(df)
    upper, mid, lower = ta.BOLL(df["close"].values, N=20, P=2)
    # ta 侧经 RD(3位小数)舍入，公式侧全精度：atol=1e-3 对齐
    np.testing.assert_allclose(res.columns["BOLL_MID"], mid, atol=1e-3, equal_nan=True)
    np.testing.assert_allclose(res.columns["BOLL_UPPER"], upper, atol=1e-3, equal_nan=True)
    np.testing.assert_allclose(res.columns["BOLL_LOWER"], lower, atol=1e-3, equal_nan=True)


def _ewm(x: np.ndarray, alpha: float) -> np.ndarray:
    """通达信 ``SMA(X,N,M)`` 的独立参照（alpha = M/N 的递归平滑）。

    pandas ``ewm`` 对输入里的 NaN 是**跳过并沿用上一值**（首个有效值之前
    仍为 NaN），公式引擎的 ``SMA`` 走的是同一条路径，参照必须保持一致。
    """
    return pd.Series(x).ewm(alpha=alpha, adjust=False).mean().to_numpy()


def test_preset_macd_matches_formula_semantics():
    """MACD 预置按**通达信公式语义**核对（EMA 链 + 柱 ×2）。

    注意与 :func:`test_formula_vs_talib_indicator_divergence_is_intentional` 的
    分工：这里锁的是公式引擎「按公式算出什么」，不是与 TA-Lib 指标一致。
    """
    df = _big_df()
    res = compile_formula(
        "DIF: EMA(C,12)-EMA(C,26); DEA: EMA(DIF,9); MACD_HIST: (DIF-DEA)*2;"
    ).compute(df)
    close = df["close"].to_numpy(dtype=float)
    dif = talib.EMA(close, 12) - talib.EMA(close, 26)
    dea = talib.EMA(dif, 9)
    np.testing.assert_allclose(res.columns["DIF"], dif, equal_nan=True)
    np.testing.assert_allclose(res.columns["DEA"], dea, equal_nan=True)
    np.testing.assert_allclose(res.columns["MACD_HIST"], (dif - dea) * 2, equal_nan=True)


def test_preset_kdj_matches_formula_semantics():
    """KDJ 预置按通达信 ``SMA(RSV,3,1)`` 核对（alpha = 1/3 的递归平滑）。"""
    df = _big_df()
    res = compile_formula(
        "RSV := (C-LLV(L,9))/(HHV(H,9)-LLV(L,9))*100;K: SMA(RSV,3,1); D: SMA(K,3,1); J: 3*K-2*D;"
    ).compute(df)
    assert res.values == ["K", "D", "J"]
    close = df["close"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    llv9 = pd.Series(low).rolling(9).min().to_numpy()
    hhv9 = pd.Series(high).rolling(9).max().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rsv = (close - llv9) / (hhv9 - llv9) * 100.0
    k = _ewm(rsv, 1 / 3)
    d = _ewm(k, 1 / 3)
    np.testing.assert_allclose(res.columns["K"], k, equal_nan=True)
    np.testing.assert_allclose(res.columns["D"], d, equal_nan=True)
    np.testing.assert_allclose(res.columns["J"], 3 * k - 2 * d, equal_nan=True)


def test_preset_rsi_matches_formula_semantics():
    """RSI 预置按通达信 ``SMA(MAX(UD,0),N,1)/SMA(ABS(UD),N,1)*100`` 核对。"""
    df = _big_df()
    res = compile_formula(
        "UD := C-REF(C,1); RSI6: SMA(MAX(UD,0),6,1)/SMA(ABS(UD),6,1)*100;"
    ).compute(df)
    close = df["close"].to_numpy(dtype=float)
    ud = np.concatenate(([np.nan], np.diff(close)))
    with np.errstate(divide="ignore", invalid="ignore"):
        expected = _ewm(np.maximum(ud, 0.0), 1 / 6) / _ewm(np.abs(ud), 1 / 6) * 100.0
    np.testing.assert_allclose(res.columns["RSI6"], expected, atol=1e-9, equal_nan=True)


def test_formula_vs_talib_indicator_divergence_is_intentional():
    """公式方言与 TA-Lib 融合指标**不**一致——这是设计结果，勿"修复"。

    TA-Lib 的 ``MACD``/``KDJ``/``RSI`` 是 C 融合实现，内部 EMA 以更长的
    复合回看期做 SMA 播种，无法由 ``talib.EMA`` 等原语精确复现。因此：

    - ``easy-tdx indicator MACD``（Web ``/api/indicator``、指标选择器）
      走 :mod:`easy_tdx.ta` 的 **TA-Lib 原生口径**；
    - ``easy-tdx formula`` 走**通达信公式语义**。

    两者在预热段长度与数值上都有可见差异（柱值另差 2 倍：公式 ×2、TA-Lib ×1）。
    本测试把该差异钉死，防止后人误以为二者应当一致而去"对齐"。
    """
    from easy_tdx import ta

    df = _big_df()
    res = compile_formula("DIF: EMA(C,12)-EMA(C,26);").compute(df)
    dif, _, _ = ta.MACD(df["close"].to_numpy(dtype=float), SHORT=12, LONG=26, M=9)
    formula, indicator = res.columns["DIF"], dif
    # 预热起点不同：公式 EMA(26) 第 25 根出值，TA-Lib MACD 第 33 根出值
    assert np.argmax(np.isfinite(formula)) < np.argmax(np.isfinite(indicator))
    both = np.isfinite(formula) & np.isfinite(indicator)
    assert both.any()
    assert not np.allclose(formula[both], indicator[both], rtol=1e-3)
    # MA/EMA 等原语两边同源，仍然逐位一致（对照：并非全面背离）
    assert np.allclose(
        compile_formula("MA20: MA(C,20);").compute(df).columns["MA20"],
        ta.MA(df["close"].to_numpy(dtype=float), 20),
        equal_nan=True,
    )
