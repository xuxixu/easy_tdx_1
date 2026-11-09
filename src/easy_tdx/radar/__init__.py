"""美股观测雷达：把日线算成前端那份整页快照。

包内分工::

    universe.py    策展层：观测池与板块/题材/细分分类（从旧快照读，不含数值）
    bars.py        数据层：新浪日线取数 + 本地 parquet 缓存
    indicators.py  指标层：均线/RSI/量比/趋势/支撑压力（复用 easy_tdx.ta）
    signals.py     信号层：规则判定 + 历史命中率回测
    build.py       组装层：产出与前端 RadarData 形状一致的 JSON

入口是 :func:`easy_tdx.radar.build.build_snapshot`，命令行见
``scripts/build_us_radar.py``。定位是**冷路径构建**（构建一次、页面只读文件），
不做实时推送。
"""

from __future__ import annotations

from .build import BuildReport, build_snapshot, write_snapshot
from .universe import Universe, load_universe

__all__ = [
    "BuildReport",
    "Universe",
    "build_snapshot",
    "load_universe",
    "write_snapshot",
]
