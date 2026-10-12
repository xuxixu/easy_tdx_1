"""大智慧指标包锁定测试 + 公式引擎扩展能力测试。

- 指标包（``web-ui/public/dzh-custom-indicators.json``，由
  ``scripts/convert_dzh_indicators.py`` 生成）：逐条编译 + 合成 K 线试算，
  保证「自定义指标」页一键导入的每一条都可识别、可计算。
- 引擎扩展（为本次批量转换补齐的方言能力）：匿名表达式输出、``!=``、
  ATAN/STDP/REVERSE、纯量输出广播、白名单新函数。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from easy_tdx.formula import FormulaError, compile_formula

PACK_PATH = Path(__file__).resolve().parents[2] / "web-ui" / "public" / "dzh-custom-indicators.json"
EXPECTED_COUNT = 52


def _df(n: int = 600, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, n))
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2023-01-01", periods=n, freq="B"),
            "open": close * (1 + rng.normal(0, 0.002, n)),
            "high": close * (1 + rng.uniform(0, 0.015, n)),
            "low": close * (1 - rng.uniform(0, 0.015, n)),
            "close": close,
            "vol": rng.uniform(1e6, 8e6, n),
        }
    )


def _load_pack() -> dict:
    assert PACK_PATH.is_file(), f"指标包缺失：{PACK_PATH}（先跑 scripts/convert_dzh_indicators.py）"
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def test_pack_schema():
    pack = _load_pack()
    assert pack["version"] == 1
    assert pack["count"] == len(pack["indicators"]) == EXPECTED_COUNT
    names = [it["name"] for it in pack["indicators"]]
    assert len(set(names)) == len(names), "显示名重复"
    for it in pack["indicators"]:
        assert it["kind"] in ("overlay", "sub"), it["name"]
        assert 0 < len(it["formula"]) <= 8000, it["name"]
        assert it["source_file"].endswith(".txt"), it["name"]
        assert isinstance(it.get("candle", []), list), it["name"]


def test_pack_all_computable():
    pack = _load_pack()
    df = _df()
    failures = []
    for it in pack["indicators"]:
        try:
            res = compile_formula(it["formula"]).compute(df)
            frame = res.to_frame()
            assert len(frame.columns) > 0
            tail = frame.iloc[-100:]
            assert any(
                int(np.isfinite(tail[c].to_numpy(dtype=float)).sum()) >= 5 for c in frame.columns
            ), "无有限输出"
        except (FormulaError, ValueError, RuntimeError, AssertionError) as exc:
            failures.append(f"{it['name']}: {exc}")
    assert not failures, "指标包中有不可计算条目：\n" + "\n".join(failures)


def test_pack_spot_values():
    """抽查两条核心指标的输出列名（防转换脚本回归改列）。"""
    pack = _load_pack()
    by_name = {it["name"]: it for it in pack["indicators"]}
    assert set(by_name["BBIANDMA60"]["outputs"]) >= {"BBI", "MA60"}
    assert set(by_name["DTR"]["signals"]) >= {"FHC", "FLC"}
    assert by_name["RVC001"]["candle"] == ["KO", "KH", "KL", "KC"]
    assert by_name["RVC001"]["kind"] == "overlay"


# ── 引擎扩展能力 ──────────────────────────────────────────────────────────


def test_anonymous_expression_outputs():
    """匿名数值/括号表达式输出（参考线 `0;`、包络 `(H-L);`）。"""
    res = compile_formula("MA5: MA(C,5);\n0;\n-50;\n(HHV(H,50)-C);").compute(_df())
    frame = res.to_frame()
    assert list(frame.columns) == ["MA5", "OUTPUT_1", "OUTPUT_2", "OUTPUT_3"]
    assert float(frame["OUTPUT_1"].iloc[-1]) == 0.0
    assert float(frame["OUTPUT_2"].iloc[-1]) == -50.0
    assert np.isfinite(float(frame["OUTPUT_3"].iloc[-1]))


def test_not_equal_operator():
    res = compile_formula("D := C - REF(C,1);\nNE: D != 0;\nEQ: D = 0;").compute(_df())
    assert "NE" in res.signals
    frame = res.to_frame()
    assert set(frame["NE"].dropna().unique()) <= {0.0, 1.0}


def test_extended_math_funcs():
    df = _df()
    res = compile_formula(
        "A: ATAN(C/REF(C,1)-1);\nS: STDP(C,20);\nR: REVERSE(C-EMA(C,60));"
    ).compute(df)
    frame = res.to_frame()
    for col in ("A", "S", "R"):
        assert int(np.isfinite(frame[col].to_numpy(dtype=float)).sum()) > 500 - 60
    # REVERSE 取负：R + (C-EMA) ≈ 0
    raw = compile_formula("D: C-EMA(C,60);").compute(df).to_frame()["D"].to_numpy(dtype=float)
    assert np.nanmax(np.abs(frame["R"].to_numpy(dtype=float) + raw)) < 1e-9


def test_extended_sequence_funcs():
    df = _df()
    res = compile_formula(
        "H: HHVBARS(H,20);\nL: LLVBARS(L,20);\nW: VALUEWHEN(CROSS(C,MA(C,10)),H);"
    ).compute(df)
    assert set(res.columns) == {"H", "L", "W"}
    assert int(res.to_frame()["W"].notna().sum()) > 0


def test_scalar_output_broadcast():
    """纯量输出广播为全长常量列（to_frame 不抛错）。"""
    frame = compile_formula("50;").compute(_df(60)).to_frame()
    assert len(frame) == 60
    assert (frame["OUTPUT_1"] == 50.0).all()


def test_ref_negative_still_rejected():
    with pytest.raises(FormulaError):
        compile_formula("A := REF(C,-1);").compute(_df())
