"""AkShare 指数历史数据源（可选依赖，美股/港股真指数全历史日K）。

为什么需要 akshare
------------------
腾讯 fqkline 对美股指数只给最新 1 根（快照性质），画不出 K 线；
港股指数腾讯给全（320 根）但只有近 1 年多。AkShare 实测：

================  ============================  ==================
指数               接口                           数据量
================  ============================  ==================
.DJI / .IXIC      index_us_stock_sina             5730 根（2004 年起）
.INX / .NDX       index_us_stock_sina             5732 / 3180 根
HSI / HSCEI       stock_hk_index_daily_sina       3234 根
HSTECH            stock_hk_index_daily_sina       1511 根
================  ============================  ==================

定位（与 baostock 同模式的可选依赖）：
- 未安装 akshare 时本模块整体静默关闭（``is_enabled()`` False），
  上层回落到腾讯快照 + 明确 source 标注，不炸。
- 日K一天一变，进程内按日历日缓存（当日命中零请求）。
- 非线程安全问题 akshare 无全局连接（纯 HTTP），可并发。
- ``EASY_TDX_AKSHARE=0`` 可关闭。
"""

from __future__ import annotations

import importlib
import logging
import os
import threading
import time
from typing import Any, Final

import pandas as pd

logger = logging.getLogger(__name__)

_DISABLE_ENV: Final = "EASY_TDX_AKSHARE"

_lock: Final = threading.Lock()
# (market, code, category) -> (日历日, DataFrame)
_cache: Final[dict[tuple[str, str, str], tuple[str, pd.DataFrame]]] = {}

#: 我们的美股指数代码 → akshare(新浪) 代码。注意标普在新浪叫 .INX。
_US_SYMBOL: Final[dict[str, str]] = {
    "DJI": ".DJI",
    "IXIC": ".IXIC",
    "SPX": ".INX",
    "NDX": ".NDX",
}


def _akshare() -> Any:
    """按需加载 akshare 模块（用 importlib 而非 ``import akshare``）。

    akshare 无 py.typed 标记，直接 import 会让 mypy 报 import-untyped；
    走 importlib 与 baostock 源保持同一套可选依赖写法。
    """
    try:
        return importlib.import_module("akshare")
    except ImportError as exc:
        raise RuntimeError(
            "akshare 未安装（pip install easy-tdx[akshare] 或 pip install akshare）"
        ) from exc


def is_enabled() -> bool:
    """akshare 是否可用（未禁用且已安装）。"""
    if os.environ.get(_DISABLE_ENV, "").strip().lower() in {"0", "false", "off"}:
        return False
    try:
        _akshare()
    except RuntimeError:
        return False
    return True


def _today_str() -> str:
    from datetime import date

    return date.today().isoformat()


def fetch_bars(
    market: str,
    code: str,
    category: str = "DAY",
    start: int = 0,
    count: int = 800,
) -> pd.DataFrame:
    """取真指数历史 K 线（AkShare 全历史，日线；周/月本地聚合）。

    返回列与 /bars 契约对齐（``date`` + OHLCV）。失败抛 ``RuntimeError``。
    """
    from easy_tdx.markets import normalize_market

    token = normalize_market(market)
    c = code.strip().upper()
    cat = category.upper()
    if cat not in ("DAY", "WEEK", "MONTH"):
        raise RuntimeError(f"akshare 指数源仅支持日/周/月线，收到 {category}")

    key = (token, c, cat)
    today = _today_str()
    with _lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == today:
            full = hit[1]
        else:
            full = None
    if full is None:
        full = _fetch_daily(token, c)
        if cat != "DAY":
            full = _resample(full, cat)
        with _lock:
            _cache[key] = (today, full)

    total = len(full)
    lo = max(0, total - start - count)
    hi = max(0, total - start)
    return full.iloc[lo:hi].reset_index(drop=True)


def _fetch_daily(token: str, code: str) -> pd.DataFrame:
    """拉全历史日K并归一化列。"""
    ak = _akshare()

    t0 = time.perf_counter()
    try:
        if token == "US":
            # .DJI / .IXIC / .NDX；SPX 在 akshare 里叫 .INX
            symbol = _US_SYMBOL.get(code, code)
            df = ak.index_us_stock_sina(symbol=symbol)
        else:
            df = ak.stock_hk_index_daily_sina(symbol=code)
    except Exception as exc:
        raise RuntimeError(f"akshare 取数失败 {token}:{code}: {exc}") from exc
    if df is None or len(df) == 0:
        raise RuntimeError(f"akshare 无数据: {token}:{code}")
    logger.info(
        "akshare %s:%s 全历史 %d 根（%.1fs）", token, code, len(df), time.perf_counter() - t0
    )

    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"),
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "vol": pd.to_numeric(df["volume"], errors="coerce"),
            "amount": pd.to_numeric(df["amount"], errors="coerce"),
        }
    )
    out = out.dropna(subset=["close"])
    return out.sort_values("date").reset_index(drop=True)


def _resample(df: pd.DataFrame, category: str) -> pd.DataFrame:
    """日K → 周/月（周五收/月末收）。"""
    tmp = df.copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    tmp = tmp.set_index("date").sort_index()
    rule = "W-FRI" if category == "WEEK" else "ME"
    agg = tmp.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"}
    )
    agg["amount"] = 0.0
    agg = agg.dropna(subset=["close"]).reset_index()
    agg["date"] = agg["date"].dt.strftime("%Y-%m-%d")
    return agg


def clear_cache() -> None:
    """清空进程内缓存（自测用）。"""
    with _lock:
        _cache.clear()


__all__ = ["is_enabled", "fetch_bars", "clear_cache"]
