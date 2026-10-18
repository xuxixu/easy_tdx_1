"""美股日线取数与本地缓存（新浪，经 akshare）。

为什么单独一个源模块，而不是复用 :mod:`easy_tdx.sources.us_hk_snapshot`
----------------------------------------------------------------------
``us_hk_snapshot`` 取的是**秒级快照**（现价/昨收/量），够看盘但算不出
均线、RSI、支撑压力、量比——雷达页需要的是**日线序列**。两者接口与
生命周期都不同（快照每次都要打网络、日线取一次能用很久），混在一起会让
「拿不到就显示 —」的降级逻辑变得含糊。

为什么走新浪（akshare ``stock_us_daily``）而不是东财或 Yahoo
--------------------------------------------------------------
2026-10-18 实测本机可达性：

===========================  ============================  ==========
源                          用途                          实测
===========================  ============================  ==========
新浪 ``stock_us_daily``     美股个股/ETF 全历史日 K         可用，约 1.1s/只
东财 ``stock_us_spot_em``   美股全市场快照                  被限频（RemoteDisconnected）
Yahoo Finance chart/options 美股行情 + 期权链              403（本机 IP 被拒）
雪球 ``_us_xq``             美股基本面                      需 xq_a_token
===========================  ============================  ==========

也就是说：**行情与衍生指标有源，期权链 / 基本面 / 国会持仓 / 新闻没有**。
后者在快照里写成 ``null`` 并登记进 ``degraded``，由前端显示「数据源不可用」，
绝不拿旧值冒充实时——这是本模块之外整个 radar 包的首要纪律。

限频与并发
----------
新浪对单 IP 连续请求敏感，但比东财宽松。默认 4 并发（实测 ~320 只标的
冷启动 1~2 分钟），可用 ``EASY_TDX_RADAR_WORKERS`` 调低；单个标���失败不
重试、直接记为缺失，避免一只票拖垮整轮重建。
"""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

logger = logging.getLogger(__name__)

__all__ = [
    "BarFetchResult",
    "default_cache_dir",
    "fetch_daily",
    "load_pool",
    "workers",
]

#: 日线缓存目录：按标的分文件存 parquet，增量重建时只重取「过期」的那些。
_CACHE_ENV: Final = "EASY_TDX_RADAR_CACHE"

#: 并发数上限。4 是实测「不触发新浪限频」与「总时长可接受」的折中。
#:
#: 注意：akshare 的美股代码解码走 py_mini_racer（内嵌 JS 引擎，**非线程安全**）。
#: 并发取数时实测偶发其进程级崩溃——那是硬崩溃，try/except 拦不住。
#: 规避办法有三层：默认并发压到 3、崩溃时重跑（已缓存的标的不会重取）、
#: 以及每次运行都报告失败清单，便于确认丢了哪几只。
_WORKERS_ENV: Final = "EASY_TDX_RADAR_WORKERS"

_DEFAULT_WORKERS: Final = 3

#: 缓存有效期（天）。收盘后行情当日变化，次日重建必须重取。
_CACHE_TTL_DAYS: Final = 1

#: 单只标的取数重试次数（仅在抛异常时重试，退避极短）。
_RETRIES: Final = 2

#: 观测池代码 → 新浪代码。新浪对美股 B 类股用点号（``BRK.B``）而非连字符
#: （``BRK-B``），不映射就会静默取回空表。这类差异是「代码存在但取不到数」
#: 的头号原因，所以在这里集中维护而不是散落到调用方。
SYMBOL_ALIAS: Final[dict[str, str]] = {
    "BRK-B": "BRK.B",
}


@dataclass(frozen=True)
class BarFetchResult:
    """单只标的的取数结果。

    ``df`` 为空表示这只票没取到（新股、代码写错、或被限频）。调用方要
    区分「没数据」和「数据全为 0」——前者是取数失败，后者是真实行情。
    """

    symbol: str
    df: pd.DataFrame
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(not self.df.empty)


def _akshare() -> Any:
    """按需加载 akshare。

    用 importlib 而非 ``import akshare``：它是可选依赖，未安装时整个
    radar 重建应当优雅跳过，而不是让整个包的 import 崩掉。
    akshare 没有 py.typed 标记，直接 import 会让 mypy strict 报错。
    """
    try:
        return importlib.import_module("akshare")
    except ImportError as exc:  # pragma: no cover - 取决于环境是否装了可选依赖
        raise RuntimeError(
            "重建雷达快照需要 akshare：pip install easy-tdx[akshare] 或 pip install akshare"
        ) from exc


def default_cache_dir() -> Path:
    """缓存目录：``EASY_TDX_RADAR_CACHE`` 或仓库内 ``.radar_cache``。"""
    env = os.environ.get(_CACHE_ENV)
    if env:
        return Path(env)
    # scripts/ 下运行时的仓库根；安装成包时退到用户缓存目录
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent / ".radar_cache"
    return Path.home() / ".easy-tdx" / "radar_cache"


def workers() -> int:
    """并发数（1~16，越界则夹取）。"""
    try:
        n = int(os.environ.get(_WORKERS_ENV, _DEFAULT_WORKERS))
    except ValueError:
        n = _DEFAULT_WORKERS
    return max(1, min(16, n))


def fetch_daily(symbol: str, adjust: str = "qfq") -> pd.DataFrame:
    """取单只标的全历史日线。

    返回列固定为 ``date, open, high, low, close, volume``，按日期升序，
    已去掉全空行——下游指标计算依赖这个形状，不必到处防御。

    新浪的美股代码不带市场前缀，ETF 与普通股同路径，因此调用方直接传
    ``"AAPL"`` / ``"XLK"`` 即可。B 类股等特例见 :data:`SYMBOL_ALIAS`。
    """
    ak = _akshare()
    raw = ak.stock_us_daily(symbol=SYMBOL_ALIAS.get(symbol, symbol), adjust=adjust)
    if raw is None or raw.empty:
        return _empty_frame()

    df = raw.rename(columns={"date": "date"}).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return df


def _empty_frame() -> pd.DataFrame:
    cols = ("date", "open", "high", "low", "close", "volume")
    return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})


def _cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"{symbol}.parquet"


def _is_fresh(path: Path, today: pd.Timestamp) -> bool:
    """缓存是否还在有效期内。

    用文件 mtime 而不是「缓存里的最后交易日」：后者在周末/节假日会一直
    判定为「新鲜」，导致节假日期间拿不到真正的收盘。
    """
    if not path.is_file():
        return False
    mtime = pd.Timestamp(path.stat().st_mtime, unit="s").normalize()
    return bool((today - mtime).days < _CACHE_TTL_DAYS)


def load_pool(
    symbols: list[str],
    cache_dir: Path | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, BarFetchResult]:
    """批量取日线，带本地缓存与有限并发。

    返回 ``symbol -> BarFetchResult``，**包含取数失败的标的**（error 非空）。
    调用方据此在快照里如实标注缺失，而不是当成「零成交」算进指标。

    缓存策略：命中且未过期直接读盘；否则重取并覆盖。冷启动（首次或隔日）
    全部走网络，热重建只补过期的那部分。
    """
    cache = cache_dir or default_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.today().normalize()

    results: dict[str, BarFetchResult] = {}
    todo: list[str] = []
    for sym in symbols:
        path = _cache_path(cache, sym)
        if _is_fresh(path, today):
            try:
                df = pd.read_parquet(path)
                results[sym] = BarFetchResult(sym, df)
                continue
            except Exception as exc:  # 缓存损坏：当成未命中，重取
                logger.debug("缓存读取失败 %s: %s", sym, exc)
        todo.append(sym)

    total = len(symbols)
    done = total - len(todo)

    def _fetch(sym: str) -> BarFetchResult:
        last = ""
        for _ in range(_RETRIES):
            try:
                df = fetch_daily(sym)
                if not df.empty:
                    try:
                        df.to_parquet(_cache_path(cache, sym), index=False)
                    except Exception as exc:  # 缓存写失败不该影响本次结果
                        logger.debug("缓存写入失败 %s: %s", sym, exc)
                    return BarFetchResult(sym, df)
                last = "空数据（代码不存在或无历史）"
            except Exception as exc:
                last = f"{type(exc).__name__}: {exc}"
        return BarFetchResult(sym, _empty_frame(), last)

    if todo:
        n = workers()
        if n == 1:
            for i, sym in enumerate(todo, start=1):
                r = _fetch(sym)
                results[sym] = r
                done += 1
                if on_progress:
                    on_progress(done, total, sym)
        else:
            with ThreadPoolExecutor(max_workers=n) as pool:
                for i, r in enumerate(pool.map(_fetch, todo), start=1):
                    results[r.symbol] = r
                    done += 1
                    if on_progress:
                        on_progress(done, total, r.symbol)

    failed = [s for s, r in results.items() if not r.ok]
    if failed:
        logger.warning("日线取数失败 %d/%d 只：%s", len(failed), total, ", ".join(failed[:10]))
    return results