"""缠论因子 — 桥接 ChanlunAnalyser。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.factor.base import Factor, register_factor


@register_factor
class ChanlunBiDir(Factor):
    name = "chanlun_bi_dir"
    category = "chanlun"
    description = "当前笔方向（+1=向上笔，-1=向下笔，0=无笔）"
    inputs = ("open", "high", "low", "close", "vol", "amount")

    def compute(self, df: pd.DataFrame) -> pd.Series:
        result = pd.Series(0.0, index=df.index, dtype=np.float64)

        try:
            from easy_tdx.chanlun.analyser import ChanlunAnalyser

            analyser = ChanlunAnalyser(frequency="DAILY")
            chanlun_result = analyser.process_klines(df)
            bis = chanlun_result.bis

            if not bis:
                return result

            # BI 只有 start/end 分型（见 chanlun/types.py），无 start_index/end_index。
            # 用分型中间 K 线的 k_index 映射回原始 bar 序号，避免 getattr 回退导致全序列被末笔覆盖。
            n = len(df)
            for bi in bis:
                start_k = getattr(getattr(bi, "start", None), "k", None)
                end_k = getattr(getattr(bi, "end", None), "k", None)
                start = getattr(start_k, "k_index", None)
                end = getattr(end_k, "k_index", None)
                if start is None or end is None:
                    continue
                direction = 1.0 if bi.direction == "up" else -1.0
                lo = max(0, min(int(start), int(end)))
                hi = min(n, max(int(start), int(end)) + 1)
                if hi > lo:
                    result.iloc[lo:hi] = direction

            last_bi = bis[-1]
            direction = 1.0 if last_bi.direction == "up" else -1.0
            result.iloc[-1] = direction

        except Exception:
            pass

        return result


@register_factor
class ChanlunMMD(Factor):
    name = "chanlun_mmd"
    category = "chanlun"
    description = "最近买卖点类型编码（正=买点，负=卖点，0=无信号）"
    inputs = ("open", "high", "low", "close", "vol", "amount")

    _MMD_MAP: dict[str, float] = {
        "1buy": 1.0,
        "2buy": 2.0,
        "3buy": 3.0,
        "l3buy": 3.0,
        "1sell": -1.0,
        "2sell": -2.0,
        "3sell": -3.0,
        "s3sell": -3.0,
    }

    def compute(self, df: pd.DataFrame) -> pd.Series:
        result = pd.Series(0.0, index=df.index, dtype=np.float64)

        try:
            from easy_tdx.chanlun.analyser import ChanlunAnalyser

            analyser = ChanlunAnalyser(frequency="DAILY")
            chanlun_result = analyser.process_klines(df)
            mmds = chanlun_result.mmds

            if not mmds:
                return result

            # MMD 字段为 mmd_type/bi/zs（见 chanlun/types.py），无 type/index。
            # 用触发笔结束分型的 k_index 定位，避免恒 0。
            for mmd in mmds:
                mmd_type = getattr(getattr(mmd, "mmd_type", ""), "value", None)
                if mmd_type is None:
                    mmd_type = str(getattr(mmd, "mmd_type", "") or "")
                bi = getattr(mmd, "bi", None)
                end_fx = getattr(bi, "end", None) if bi is not None else None
                k = getattr(end_fx, "k", None) if end_fx is not None else None
                mmd_index = getattr(k, "k_index", -1)
                try:
                    mmd_index = int(mmd_index)
                except (TypeError, ValueError):
                    continue
                value = self._MMD_MAP.get(str(mmd_type), 0.0)
                if 0 <= mmd_index < len(df):
                    result.iloc[mmd_index] = value

        except Exception:
            pass

        return result
