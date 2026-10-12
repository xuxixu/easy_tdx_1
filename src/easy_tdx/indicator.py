"""技术指标计算模块 — 基于 TA-Lib 的纯计算层（无 IO）。

指标定义与数值口径由 :mod:`easy_tdx.ta` 提供：TA-Lib 覆盖不到的指标走本项目
自建的中式实现（:mod:`easy_tdx.ta.chinese`），其余直接使用 TA-Lib 原生定义。

与早期版本（MyTT/pandas 实现）的口径差异见
:mod:`easy_tdx.ta.talib_ind` 的模块文档：MACD 柱不再乘 2、RSI 默认周期 14、
``WR`` 改用 ``WILLR`` 的 -100~0 刻度、``OBV`` 为原始成交量量纲。
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from . import ta


@dataclass(frozen=True)
class IndicatorSpec:
    """单个技术指标的元数据。"""

    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    func: Callable[..., object]
    default_params: dict[str, int | float]
    description: str


_REGISTRY: dict[str, IndicatorSpec] = {}


def _reg(
    name: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    func: Callable[..., object],
    defaults: dict[str, int | float],
    desc: str,
) -> None:
    _REGISTRY[name.upper()] = IndicatorSpec(
        name=name.upper(),
        inputs=inputs,
        outputs=outputs,
        func=func,
        default_params=defaults,
        description=desc,
    )


# ── 仅需 close ──────────────────────────────────────────────────────────
_reg(
    "MACD",
    ("close",),
    ("MACD_DIF", "MACD_DEA", "MACD_HIST"),
    ta.MACD,
    {"SHORT": 12, "LONG": 26, "M": 9},
    "MACD 指数平滑异同移动平均线（TA-Lib 口径：柱 = DIF - DEA，不乘 2）",
)
_reg("RSI", ("close",), ("RSI",), ta.RSI, {"N": 14}, "RSI 相对强弱指标（Wilder 平滑，默认 14）")
_reg(
    "BOLL",
    ("close",),
    ("BOLL_UPPER", "BOLL_MID", "BOLL_LOWER"),
    ta.BOLL,
    {"N": 20, "P": 2},
    "BOLL 布林带",
)
_reg(
    "BIAS",
    ("close",),
    ("BIAS1", "BIAS2", "BIAS3"),
    ta.BIAS,
    {"L1": 6, "L2": 12, "L3": 24},
    "BIAS 乖离率",
)
_reg("PSY", ("close",), ("PSY", "PSY_MA"), ta.PSY, {"N": 12, "M": 6}, "PSY 心理线")
_reg(
    "TRIX",
    ("close",),
    ("TRIX", "TRIX_MA"),
    ta.TRIX,
    {"M1": 12, "M2": 20},
    "TRIX 三重指数平滑平均线",
)
_reg("DPO", ("close",), ("DPO", "DPO_MA"), ta.DPO, {"M1": 20, "M2": 10, "M3": 6}, "DPO 区间震荡线")
_reg("MTM", ("close",), ("MTM", "MTM_MA"), ta.MTM, {"N": 12, "M": 6}, "MTM 动量指标")
_reg("ROC", ("close",), ("ROC", "ROC_MA"), ta.ROC, {"N": 12, "M": 6}, "ROC 变动率指标")
_reg(
    "EXPMA",
    ("close",),
    ("EXPMA_12", "EXPMA_50"),
    ta.EXPMA,
    {"N1": 12, "N2": 50},
    "EXPMA 指数平均数指标",
)
_reg("BBI", ("close",), ("BBI",), ta.BBI, {"M1": 3, "M2": 6, "M3": 12, "M4": 20}, "BBI 多空指标")
_reg(
    "DFMA",
    ("close",),
    ("DFMA_DIF", "DFMA_DMA"),
    ta.DFMA,
    {"N1": 10, "N2": 50, "M": 10},
    "DFMA 平行线差指标",
)

# ── 需要 close + high + low ─────────────────────────────────────────────
_reg(
    "KDJ",
    ("close", "high", "low"),
    ("KDJ_K", "KDJ_D", "KDJ_J"),
    ta.KDJ,
    {"N": 9, "M1": 3, "M2": 3},
    "KDJ 随机指标",
)
_reg(
    "DMI",
    ("close", "high", "low"),
    ("DMI_PDI", "DMI_MDI", "DMI_ADX", "DMI_ADXR"),
    ta.DMI,
    {"M1": 14, "M2": 6},
    "DMI 动向指标",
)
_reg("ATR", ("close", "high", "low"), ("ATR",), ta.ATR, {"N": 20}, "ATR 真实波幅均值")
_reg(
    "WR",
    ("close", "high", "low"),
    ("WR1", "WR2"),
    ta.WR,
    {"N": 10, "N1": 6},
    "WR 威廉指标（TA-Lib WILLR 刻度 -100~0：0=超买，-100=超卖）",
)
_reg("CCI", ("close", "high", "low"), ("CCI",), ta.CCI, {"N": 14}, "CCI 顺势指标")
_reg("CR", ("close", "high", "low"), ("CR",), ta.CR, {"N": 20}, "CR 价格动量指标")
_reg(
    "KTN",
    ("close", "high", "low"),
    ("KTN_UPPER", "KTN_MID", "KTN_LOWER"),
    ta.KTN,
    {"N": 20, "M": 10},
    "KTN 肯特纳通道",
)
_reg(
    "XSII",
    ("close", "high", "low"),
    ("XSII_TD1", "XSII_TD2", "XSII_TD3", "XSII_TD4"),
    ta.XSII,
    {"N": 102, "M": 7},
    "XSII 薛斯通道II",
)

# ── 需要 close + vol ────────────────────────────────────────────────────
_reg("OBV", ("close", "vol"), ("OBV",), ta.OBV, {}, "OBV 能量潮指标（TA-Lib 原始成交量量纲）")
_reg("VR", ("close", "vol"), ("VR",), ta.VR, {"M1": 26}, "VR 容量比率")

# ── 需要 high + low + vol ───────────────────────────────────────────────
_reg(
    "EMV",
    ("high", "low", "vol"),
    ("EMV", "EMV_MA"),
    ta.EMV,
    {"N": 14, "M": 9},
    "EMV 简易波动指标",
)
_reg(
    "MASS",
    ("high", "low"),
    ("MASS", "MASS_MA"),
    ta.MASS,
    {"N1": 9, "N2": 25, "M": 6},
    "MASS 梅斯线",
)

# ── 需要 close + high + low + vol ──────────────────────────────────────
_reg("MFI", ("close", "high", "low", "vol"), ("MFI",), ta.MFI, {"N": 14}, "MFI 资金流量指标")

# ── 需要 open + close + high + low ─────────────────────────────────────
_reg("BRAR", ("open", "close", "high", "low"), ("AR", "BR"), ta.BRAR, {"M1": 26}, "BRAR 情绪指标")
_reg(
    "ASI",
    ("open", "close", "high", "low"),
    ("ASI", "ASI_MA"),
    ta.ASI,
    {"M1": 26, "M2": 10},
    "ASI 振动升降指标",
)

# ── 捉妖大师（仅需 close）─────────────────────────────────────────────
_reg(
    "ZHUOYAO",
    ("close",),
    ("ZY_LONG", "ZY_MID", "ZY_SHORT", "ZY_TREND"),
    ta.ZHUOYAO,
    {"N1": 120, "N2": 60, "N3": 20, "M": 10},
    "ZHUOYAO 捉妖大师 多周期涨幅共振",
)
_reg(
    "BIAS_SIGNAL",
    ("close",),
    ("BS_X", "BS_SMA", "BS_LMA"),
    ta.BIAS_SIGNAL,
    {"P": 10, "M": 30},
    "BIAS_SIGNAL 30日乖离率信号（乖离率+短/长信号线）",
)

# ── 仅需 high + low ────────────────────────────────────────────────────
_reg("TAQ", ("high", "low"), ("TAQ_UP", "TAQ_MID", "TAQ_DOWN"), ta.TAQ, {"N": 20}, "TAQ 唐安奇通道")

# ── SAR 抛物线转向（仅需 high + low）─────────────────────────────────
_reg(
    "SAR",
    ("high", "low"),
    ("SAR",),
    ta.SAR,
    {"AF_STEP": 0.02, "AF_MAX": 0.2},
    "SAR 抛物线转向（动态止损位）",
)

# ── VWAP 成交量加权均价（close + high + low + vol）────────────────────
_reg(
    "VWAP",
    ("close", "high", "low", "vol"),
    ("VWAP",),
    ta.VWAP,
    {"N": 20},
    "VWAP 成交量加权均价（N日滚动机构基准成本）",
)

# ── Aroon 阿隆指标（仅需 high + low）────────────────────────────────
_reg(
    "AROON",
    ("high", "low"),
    ("AROON_UP", "AROON_DOWN", "AROON_OSC"),
    ta.AROON,
    {"N": 25},
    "AROON 阿隆指标（趋势启动时机）",
)

# ── FK 趋势快线慢线（仅需 close，清理孤儿函数）──────────────────────
_reg(
    "FK",
    ("close",),
    ("FK",),
    ta.FK,
    {},
    "FK 趋势指标（EMA(2) 突破斜率外推 EMA(42)，动量偏离检测）",
)

# ── V4.3 无未来函数指标（全部只引用当期及历史数据，信号不漂移） ──────────

# 趋势/止损类
_reg(
    "SUPERTREND",
    ("close", "high", "low"),
    ("SUPERTREND", "ST_DIR"),
    ta.SUPERTREND,
    {"N": 10, "M": 3.0},
    "SUPERTREND 超级趋势（ATR 通道趋势跟踪，兼移动止损；TA-Lib 口径 ST_DIR=-1多/1空）",
)
_reg(
    "CHANDELIER",
    ("close", "high", "low"),
    ("CHDL_LONG", "CHDL_SHORT"),
    ta.CHANDELIER,
    {"N": 22, "M": 22, "K": 3.0},
    "CHANDELIER 吊灯止损（多头/空头 ATR 跟踪止损位）",
)
_reg("HMA", ("close",), ("HMA",), ta.HMA, {"N": 16}, "HMA 赫尔均线（低滞后不重绘）")
_reg(
    "KAMA",
    ("close",),
    ("KAMA",),
    ta.KAMA,
    {"N": 10},
    "KAMA 考夫曼自适应均线（TA-Lib 原生：快/慢常量固定 2/30，不可配）",
)
_reg(
    "ICHIMOKU",
    ("high", "low", "close"),
    ("IC_TENKAN", "IC_KIJUN", "IC_SPAN_A", "IC_SPAN_B", "IC_CHIKOU"),
    ta.ICHIMOKU,
    {"P1": 9, "P2": 26, "P3": 52, "SHIFT": 26},
    "ICHIMOKU 一目均衡表（迟行带 IC_CHIKOU 仅作图示，当期信号请用转换/基准线与先行带）",
)

# 动量/振荡类
_reg(
    "UOS",
    ("close", "high", "low"),
    ("UOS", "UOS_MA"),
    ta.UOS,
    {"P1": 7, "P2": 14, "P3": 28, "M": 6},
    "UOS 终极指标（7/14/28 三周期加权动量）",
)
_reg("CMO", ("close",), ("CMO",), ta.CMO, {"N": 14}, "CMO 钱德动量振荡器")
_reg("TSI", ("close",), ("TSI", "TSI_MA"), ta.TSI, {"R": 25, "S": 13, "M": 13}, "TSI 真实强度指数")
_reg(
    "FISHER",
    ("high", "low"),
    ("FISHER", "FISHER_TRG"),
    ta.FISHER,
    {"N": 9},
    "FISHER 费雪变换（区间位置正态化，拐点尖锐）",
)

# 波动率/状态识别类
_reg(
    "SQUEEZE",
    ("close", "high", "low"),
    ("SQZ_ON", "SQZ_MOM"),
    ta.SQUEEZE,
    {"N": 20, "BB": 2.0, "KC": 1.5},
    "SQUEEZE TTM 挤压动量（布林收进肯特纳=挤压态，SQZ_MOM 为线性回归动量）",
)
_reg(
    "CHOP",
    ("close", "high", "low"),
    ("CHOP",),
    ta.CHOP,
    {"N": 14},
    "CHOP 盘整指数（>61.8 震荡 / <38.2 趋势）",
)
_reg(
    "BBP",
    ("close",),
    ("BBP",),
    ta.BBP,
    {"N": 20, "P": 2},
    "BBP 布林位置 %B（0=下轨，50=中轨，100=上轨）",
)
_reg("BBW", ("close",), ("BBW",), ta.BBW, {"N": 20, "P": 2}, "BBW 布林带宽（收窄=变盘预警）")

# 量能/资金类
_reg("AD", ("close", "high", "low", "vol"), ("AD",), ta.AD, {}, "AD 累积/派发线")
_reg("CMF", ("close", "high", "low", "vol"), ("CMF",), ta.CMF, {"N": 20}, "CMF 佳庆资金流量")
_reg("EFI", ("close", "vol"), ("EFI",), ta.EFI, {"N": 13}, "EFI 艾尔德强力指数")


def list_indicators() -> list[dict[str, object]]:
    """返回所有可用指标的元数据。"""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "inputs": list(spec.inputs),
            "outputs": list(spec.outputs),
            "default_params": dict(spec.default_params),
        }
        for spec in _REGISTRY.values()
    ]


def compute_indicators(
    df: pd.DataFrame,
    indicators: list[str],
    params: dict[str, dict[str, int | float]] | None = None,
    keep_ohlcv: bool = True,
    tail: int | None = None,
) -> pd.DataFrame:
    """在 K 线 DataFrame 上计算指定技术指标。

    Args:
        df: K 线数据，需包含 open/close/high/low/vol 等列。
        indicators: 指标名称列表（不区分大小写），如 ``["MACD", "KDJ"]``。
        params: 可选参数覆盖，如 ``{"MACD": {"SHORT": 10}}``。
        keep_ohlcv: True 则保留原始 OHLCV 列。
        tail: 计算后仅保留最后 N 行。

    Returns:
        包含指标列的 DataFrame。
    """
    if df.empty:
        return pd.DataFrame(df.copy())

    params = params or {}
    result_parts: list[pd.DataFrame] = []
    required_inputs: set[str] = set()

    names_upper = [n.strip().upper() for n in indicators]
    unknown = [n for n in names_upper if n not in _REGISTRY]
    if unknown:
        raise ValueError(f"未知指标: {unknown}。可用指标: {sorted(_REGISTRY.keys())}")

    for name in names_upper:
        spec = _REGISTRY[name]
        required_inputs.update(spec.inputs)

    missing_cols = required_inputs - set(df.columns)
    if missing_cols:
        raise ValueError(f"DataFrame 缺少必要列: {missing_cols}。指标需要这些列: {required_inputs}")

    if len(df) < 120:
        warnings.warn(
            f"数据仅 {len(df)} 行，EMA 类指标至少需要 120 行才能精确收敛",
            stacklevel=2,
        )

    for name in names_upper:
        spec = _REGISTRY[name]
        inputs = tuple(df[col].values for col in spec.inputs)
        override = params.get(name, params.get(spec.name, {}))
        kwargs = {**spec.default_params, **override}
        raw = spec.func(*inputs, **kwargs)

        if isinstance(raw, tuple):
            arrays = raw
        else:
            arrays = (raw,)

        if len(arrays) != len(spec.outputs):
            raise RuntimeError(f"{name}: 预期 {len(spec.outputs)} 个输出，实际 {len(arrays)} 个")

        part = pd.DataFrame(
            {col: arr for col, arr in zip(spec.outputs, arrays)},
            index=df.index,
        )
        result_parts.append(part)

    indicator_df: pd.DataFrame = pd.concat(result_parts, axis=1)

    if keep_ohlcv:
        out: pd.DataFrame = pd.concat([df, indicator_df], axis=1)
    else:
        time_cols = [c for c in ("datetime", "date") if c in df.columns]
        out = pd.concat([df[time_cols], indicator_df], axis=1) if time_cols else indicator_df

    if tail is not None and tail > 0:
        out = out.iloc[-tail:]

    return pd.DataFrame(out.reset_index(drop=True))
