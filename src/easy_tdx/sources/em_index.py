"""东财现货第三备源（经 AkShare，无需 API Key）。

为什么需要第三备
----------------
真指数报价链此前只有两级：新浪 ``hq.sinajs``（主）→ 腾讯 ``qt.gtimg``
（备）。两者同时失败（限流/网络抖动）时指数条直接缺数。本模块在链尾
再加一级东财现货：

================  ============================  ============================
指数               AkShare 接口                   说明
================  ============================  ============================
HSI/HSCEI/HSTECH  ``stock_hk_index_spot_em``     东财港股指数现货，代码同名
DJI/SPX           ``index_global_spot_em``       东财全球指数，DJI→DJIA
NDX/IXIC          ``index_global_spot_em``       尽力匹配（见下），缺失则抛异常
================  ============================  ============================

定位（与 :mod:`easy_tdx.sources.ak_index` 同模式的可选依赖）：

- 未安装 akshare 时整体静默关闭（``is_enabled()`` False），调用方回落到
  抛异常——排在链尾，抛异常即“指数暂无报价”，不炸整个看板。
- 两个现货接口都是**全表返回**（一次拿回几十~几百行），逐 code 调会把
  同一张表反复下载；这里按表做 10 秒 TTL 缓存，一轮 SSE fan-out 内
  （3 个港股指数同表）只产生一次真实请求。
- ``EASY_TDX_AKSHARE=0`` 可关闭（与 ak_index 共用同一开关）。
- 与新浪/腾讯一样是**延时快照**（东财网页港股自标延时），只解决“有无”，
  不解决“快慢”——不要当实时 tick 用。

美股代码注意
------------
我们的 ``NDX`` 指纳斯达克 100，``IXIC`` 指纳斯达克综合指数；东财全球表
实测行（AkShare 文档）只有 ``NDX（纳斯达克）`` 一行，无法从名称区分它
到底是 100 还是综合。策略：精确代码优先命中（NDX→NDX、IXIC→IXIC），
IXIC 再试 ``COMP``（雅虎系综合指数代码）；命中即用并记 info 日志（含
东财代码与名称），便于事后核对。缺失时抛 ``RuntimeError``——**宁可缺，
不可错**。
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

#: 现货全表缓存 TTL（秒）：覆盖一轮 SSE 批量拉取，避免同表反复下载。
_TTL: Final = 10.0

_lock: Final = threading.Lock()
# kind("hk"/"global") -> (monotonic_ts, DataFrame)
_cache: Final[dict[str, tuple[float, pd.DataFrame]]] = {}

#: 美股我们的代码 → 东财全球表候选代码（按序首个命中者胜出）。
_US_CANDIDATES: Final[dict[str, tuple[str, ...]]] = {
    "DJI": ("DJIA", "DJI"),
    "SPX": ("SPX", "INX"),
    "NDX": ("NDX",),
    "IXIC": ("IXIC", "COMP"),
}


def _akshare() -> Any:
    """按需加载 akshare（与 ak_index 同写法，避免 mypy import-untyped）。"""
    try:
        return importlib.import_module("akshare")
    except ImportError as exc:
        raise RuntimeError(
            "akshare 未安装（pip install easy-tdx[akshare] 或 pip install akshare）"
        ) from exc


def is_enabled() -> bool:
    """东财现货备源是否可用（未禁用且已安装 akshare）。"""
    if os.environ.get(_DISABLE_ENV, "").strip().lower() in {"0", "false", "off"}:
        return False
    try:
        _akshare()
    except RuntimeError:
        return False
    return True


def _bulk(kind: str) -> pd.DataFrame:
    """取现货全表（带 TTL 缓存）。kind: "hk" 港股指数 / "global" 全球指数。"""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(kind)
        if hit is not None and now - hit[0] < _TTL:
            return hit[1]
    ak = _akshare()
    t0 = time.perf_counter()
    try:
        df = ak.stock_hk_index_spot_em() if kind == "hk" else ak.index_global_spot_em()
    except Exception as exc:
        raise RuntimeError(f"东财现货全表失败({kind}): {exc}") from exc
    if df is None or len(df) == 0:
        raise RuntimeError(f"东财现货全表为空({kind})")
    logger.info("东财现货 %s 全表 %d 行（%.1fs）", kind, len(df), time.perf_counter() - t0)
    with _lock:
        _cache[kind] = (now, df)
    return df


def _num(row: pd.Series, names: tuple[str, ...], *, default: float = 0.0) -> float:
    """从中文列候选中取第一个可用的数值。"""
    for n in names:
        if n in row.index:
            v = pd.to_numeric(pd.Series([row[n]]), errors="coerce").iloc[0]
            if pd.notna(v):
                return float(v)
    return default


def _pick(df: pd.DataFrame, code_col: str, candidates: tuple[str, ...]) -> pd.Series:
    """按候选代码首个命中返回该行；全 miss 抛 RuntimeError。"""
    codes = df[code_col].astype(str).str.strip().str.upper()
    for cand in candidates:
        m = df[codes == cand]
        if len(m):
            return m.iloc[0]
    raise RuntimeError(f"东财现货无此指数: {candidates}")


def fetch_quote(market: str, code: str) -> dict[str, Any]:
    """取真指数东财现货报价（新浪/腾讯双双失败后的第三备）。

    返回与 :func:`easy_tdx.sources.qq_index.fetch_quote` 同构的
    ``{market, code, name, price, pre_close, open, high, low, amount}``；
    失败抛 ``RuntimeError``。
    """
    from easy_tdx.markets import normalize_market
    from easy_tdx.sources.qq_index import HTTP_INDEX_NAMES

    token = normalize_market(market)
    c = code.strip().upper()
    if token == "HK":
        df = _bulk("hk")
        row = _pick(df, "代码", (c,))
        name = str(row.get("名称", "") or "")
        price = _num(row, ("最新价",), default=float("nan"))
        pre = _num(row, ("昨收", "昨收价"), default=float("nan"))
        opn = _num(row, ("今开", "开盘价"))
        high = _num(row, ("最高", "最高价"))
        low = _num(row, ("最低", "最低价"))
        amount = _num(row, ("成交额",))
    elif token == "US":
        df = _bulk("global")
        cands = _US_CANDIDATES.get(c)
        if not cands:
            raise RuntimeError(f"东财现货不支持的美股指数: {c}")
        row = _pick(df, "代码", cands)
        em_code = str(row.get("代码", ""))
        name = str(row.get("名称", "") or "")
        logger.info("东财美股指数 %s 命中 %s(%s)", c, em_code, name)
        price = _num(row, ("最新价",), default=float("nan"))
        pre = _num(row, ("昨收价", "昨收"), default=float("nan"))
        opn = _num(row, ("开盘价", "今开"))
        high = _num(row, ("最高价", "最高"))
        low = _num(row, ("最低价", "最低"))
        amount = 0.0  # 全球表无成交额列
    else:
        raise RuntimeError(f"东财现货仅支持港美股指数，收到 {market}:{code}")

    if not (pd.notna(price) and pd.notna(pre)) or pre == 0:
        raise RuntimeError(f"东财现货缺关键字段 {token}:{c}")
    return {
        "market": token,
        "code": c,
        "name": name or HTTP_INDEX_NAMES.get(c, c),
        "price": float(price),
        "pre_close": float(pre),
        "open": float(opn),
        "high": float(high),
        "low": float(low),
        "amount": float(amount or 0.0),
    }


def fetch_quotes(market: str, codes: list[str]) -> pd.DataFrame:
    """批量取东财现货报价（同表 TTL 缓存，多 code 只产生一次真实请求）。"""
    rows: list[dict[str, Any]] = []
    for code in codes:
        try:
            rows.append(fetch_quote(market, code))
        except Exception as exc:  # noqa: BLE001 — 单只失败不阻断
            logger.warning("东财现货报价失败 %s%s: %s", market, code, exc)
    return pd.DataFrame(rows)


def clear_cache() -> None:
    """清空全表 TTL 缓存（自测用）。"""
    with _lock:
        _cache.clear()


__all__ = ["is_enabled", "fetch_quote", "fetch_quotes", "clear_cache"]
