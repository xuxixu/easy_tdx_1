"""观测池与分类体系：哪些标的、分到哪个板块/题材/细分。

为什么「观测池」要从快照里读，而不是重新抓
----------------------------------------
观测池是**策展结果**而非市场数据：为什么是这 299 只、为什么 NVDA 归
「AI算力-芯片」而不是「半导体」、为什么把 SMH 单列为一个「板块」——这些
是人的判断，没有任何一个数据源能告诉你。因此本模块从已有快照里读出这层
**分类与选池**，而所有**数值**（价格、均线、信号、排名）一律用实时日线重算。

换句话说：策展沿用旧快照，数字全部换成当天的。快照里被判定为缺失的标的
（取不到日线）不会静默留在池子里——它们会被 ``missing`` 列出来，由构建脚本
报告，让「池子为什么从 299 变成 280」这种事有据可查。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)

__all__ = ["Universe", "load_universe", "default_snapshot_path"]


#: 板块 ETF 基准：11 大板块 + SMH（半导体，与参考页口径一致单列）。
#: 用 ETF 而不是指数，是因为它可交易、且能直接拿到日线。
SECTOR_ETFS: Final[tuple[tuple[str, str], ...]] = (
    ("XLK", "科技"),
    ("XLF", "金融"),
    ("XLE", "能源"),
    ("XLV", "医疗"),
    ("XLC", "通信"),
    ("XLY", "可选消费"),
    ("XLP", "必需消费"),
    ("XLI", "工业"),
    ("XLB", "材料"),
    ("XLU", "公用事业"),
    ("XLRE", "房地产"),
    ("SMH", "半导体"),
)

#: 宏观/跨资产 ETF（用于大盘环境区）。
MACRO_ETFS: Final[tuple[tuple[str, str], ...]] = (
    ("TLT", "20年美债"),
    ("GLD", "黄金"),
    ("SLV", "白银"),
    ("UUP", "美元指数"),
    ("HYG", "高收益债"),
    ("KWEB", "中概互联"),
)

#: 每日三板斧：先看指数环境，再看个股。
TRIPLE_AXES: Final[tuple[str, ...]] = ("QQQ", "SPY", "SOXX")

#: 相对强度基准：RS = 标的月涨幅 − 该 ETF 月涨幅。
RS_BENCHMARK: Final = "SPY"

#: 策展文件名（构建的输入，与快照产物分离）。
UNIVERSE_FILE: Final = "us-radar.universe.json"

#: 播种策展时读取的快照文件名。
SEED_SNAPSHOT: Final = "us-radar.json"

#: 真指数（ak_index 的新浪代码）。行情快照用 ^GSPC 等写法是拿不到的，
#: 这里统一用新浪的 . 前缀形式，与既有 sources/ak_index.py 一致。
US_INDICES: Final[tuple[tuple[str, str, str], ...]] = (
    (".INX", "标普500", "^GSPC"),
    (".IXIC", "纳斯达克", "^IXIC"),
    (".DJI", "道琼斯", "^DJI"),
    (".VIX", "VIX恐慌指数", "^VIX"),
    (".RUT", "罗素2000", "^RUT"),
)


@dataclass
class Universe:
    """策展后的观测池：标的清单 + 三套分类。"""

    #: 全部个股/ETF 代码（含板块与宏观 ETF，因为它们也要算指标）
    tickers: list[str]
    #: 个股代码 → 题材
    theme_of: dict[str, str]
    #: 个股代码 → GICS 行业
    gics_of: dict[str, str]
    #: 个股代码 → 所属板块 ETF
    sector_of: dict[str, str]
    #: 细分名 → 成分代码
    subsectors: dict[str, list[str]]
    #: 题材名 → 成分代码
    themes: dict[str, list[str]]
    #: 拥挤度聚合用的「题材」（比 theme_of 更粗一层）
    crowd_groups: dict[str, list[str]]
    #: 期权代表池（无数据源时仍记下来，供前端说明为何缺失）
    option_pool: list[str] = field(default_factory=list)
    #: 从快照里读到的原始观察池只数
    declared_size: int = 0

    @property
    def equities(self) -> list[str]:
        """纯个股（去掉板块/宏观 ETF）。"""
        etfs = {c for c, _ in SECTOR_ETFS} | {c for c, _ in MACRO_ETFS}
        return [t for t in self.tickers if t not in etfs]


def default_snapshot_path() -> Path:
    """仓库内 ``web-ui/public/data/us-radar.json``。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent / "web-ui" / "public" / "data" / SEED_SNAPSHOT
    raise FileNotFoundError("找不到仓库根目录（web-ui/public/data）")


def data_dir() -> Path:
    """``web-ui/public/data`` 目录。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent / "web-ui" / "public" / "data"
    raise FileNotFoundError("找不到仓库根目录（web-ui/public/data）")


def default_universe_path() -> Path:
    """策展文件路径（构建的**输入**）。"""
    return data_dir() / UNIVERSE_FILE


def _seed_from_snapshot(dest: Path) -> dict[str, Any]:
    """从旧快照抽出策展层，写成独立的 universe 文件。

    只在策展文件缺失时执行一次；之后以策展文件为准。
    """
    src = default_snapshot_path()
    raw = json.loads(src.read_text(encoding="utf-8"))

    def _rows(section: str) -> list[dict[str, Any]]:
        """分区可能被写成 ``null``（无数据源），取 rows 时要兜住。"""
        sec = raw.get(section)
        if not isinstance(sec, dict):
            return []
        rows = sec.get("rows")
        return [r for r in (rows or []) if isinstance(r, dict)]

    payload = {
        "note": "观测池与分类（策展层）。首次由 build_us_radar.py 从快照播种；"
        "此文件不会被重建覆盖，可直接编辑以调整池子与分类。",
        "watchlist": [
            {"ticker": r.get("ticker"), "theme": r.get("theme"), "gics": r.get("gics")}
            for r in (raw.get("watchlist") or [])
            if r.get("ticker")
        ],
        "sectors": [
            {
                "ticker": s.get("ticker"),
                "constituents": [
                    {"ticker": c.get("ticker")}
                    for c in (s.get("constituents") or [])
                    if c.get("ticker")
                ],
            }
            for s in (raw.get("sectors") or [])
            if s.get("ticker")
        ],
        "subsectors": [
            {
                "name": r.get("name"),
                "constituents": [
                    {"ticker": c.get("ticker")}
                    for c in (r.get("constituents") or [])
                    if c.get("ticker")
                ],
            }
            for r in _rows("subsectors")
            if r.get("name")
        ],
        "theme_trend": [
            {"theme": r.get("theme"), "tickers": r.get("tickers") or []}
            for r in _rows("theme_trend")
            if r.get("theme")
        ],
        "crowding": [
            {"theme": r.get("theme"), "tickers": r.get("tickers") or []}
            for r in _rows("crowding")
            if r.get("theme")
        ],
        "option_pool": [
            str(c.get("ticker"))
            for c in ((raw.get("options") or {}).get("chains") or [])
            if c.get("ticker")
        ],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已从 %s 播种策展文件 %s", src.name, dest.name)
    return payload


def load_universe(path: Path | None = None) -> Universe:
    """读出策展层（池子 + 三套分类）。

    只读分类、**不读任何数值**——``watchlist`` 里的 close/rsi/inst 等字段
    在这里一律不取，避免旧值以任何形式渗进新快照。

    策展文件不存在时，从快照播种一次并落盘。
    """
    src = path or default_universe_path()
    raw: dict[str, Any]
    if src.is_file():
        raw = json.loads(src.read_text(encoding="utf-8"))
    else:
        raw = _seed_from_snapshot(src)

    theme_of: dict[str, str] = {}
    gics_of: dict[str, str] = {}
    for row in raw.get("watchlist") or []:
        tk = row.get("ticker")
        if not tk:
            continue
        theme_of[tk] = str(row.get("theme") or "")
        gics_of[tk] = str(row.get("gics") or "")

    sector_of: dict[str, str] = {}
    for sec in raw.get("sectors") or []:
        etf = sec.get("ticker")
        for c in sec.get("constituents") or []:
            tk = c.get("ticker")
            if tk and etf:
                sector_of[tk] = etf

    subsectors = {
        str(r.get("name")): [
            str(c.get("ticker")) for c in (r.get("constituents") or []) if c.get("ticker")
        ]
        for r in raw.get("subsectors") or []
        if r.get("name")
    }
    themes = {
        str(r.get("theme")): [str(t) for t in (r.get("tickers") or [])]
        for r in raw.get("theme_trend") or []
        if r.get("theme")
    }
    crowd_groups = {
        str(r.get("theme")): [str(t) for t in (r.get("tickers") or [])]
        for r in raw.get("crowding") or []
        if r.get("theme")
    }
    option_pool = [str(t) for t in (raw.get("option_pool") or []) if t]

    # 全量代码 = 个股 + 板块 ETF + 宏观 ETF + 三板斧，全部要算指标
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(items: list[str]) -> None:
        for t in items:
            if t and t not in seen:
                seen.add(t)
                ordered.append(t)

    _add(list(theme_of))
    _add([c for c, _ in SECTOR_ETFS])
    _add([c for c, _ in MACRO_ETFS])
    _add(list(TRIPLE_AXES))

    u = Universe(
        tickers=ordered,
        theme_of=theme_of,
        gics_of=gics_of,
        sector_of=sector_of,
        subsectors=subsectors,
        themes=themes,
        crowd_groups=crowd_groups,
        option_pool=option_pool,
        declared_size=len(theme_of),
    )
    logger.info(
        "观测池 %d 只（快照声明 %d），板块 %d / 细分 %d / 题材 %d",
        len(u.equities), u.declared_size, len(sector_of), len(subsectors), len(themes),
    )
    return u