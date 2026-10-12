"""港美股真指数 HTTP 数据源（新浪实时 + 腾讯 K 线/分时）。

为什么需要 HTTP 源
------------------
通达信 7727 扩展行情服务器（18 台全测）没有国企指数（HSCEI）、恒生科技
（HSTECH）、道指（.DJI）、纳指（.IXIC）、标普（.INX）：goods_list 里没有、
goods_kline 直接取返回 0 行。只有恒生指数（HSI）是真的。

免费 HTTP 源实测可用（2026-10-11）：

================  ================  ====================================
数据               接口               说明
================  ================  ====================================
实时报价           新浪 hq.sinajs     rt_hkHSI/rt_hkHSCEI/rt_hkHSTECH +
                                     gb_dji/gb_ixic/gb_inx（注意标普是 inx）
实时报价（备）     腾讯 qt.gtimg      r_hkHSI/r_hkHSCEI + ff_DJI/ff_INX/ff_CCMP
日/周/月K          腾讯 fqkline       hkHSI/hkHSCEI/hkHSTECH/usDJI/usIXIC/usINX
分时               腾讯 minute/query  hkHSI 全天逐分钟点
================  ================  ====================================

本模块是纯 HTTP（urllib），无第三方依赖、无需 API Key。超时短（8 秒）、
失败抛异常由上层转 503——指数条拿不到就显示"—"，不炸整个看板。

指数映射（我们的 market/code → 各源代码）
--------------------------------------
港股走 27 分区的是 HSI（TDX 有）；HSCEI/HSTECH 在 TDX 无，HTTP 源 code
与 TDX 目标 code 同名。美股 DJI/IXIC/SPX 在 TDX 无（注意标普在腾讯叫
usINX、在新浪叫 gb_inx，名字不统一，映射表收敛掉这个差异）。
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Final

import pandas as pd

logger = logging.getLogger(__name__)

_TIMEOUT: Final = 8.0
_UA: Final = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}

#: (market, code) → 腾讯代码。code 即用户要的真指数代码。
QQ_MAP: Final[dict[tuple[str, str], str]] = {
    ("HK", "HSI"): "hkHSI",
    ("HK", "HSCEI"): "hkHSCEI",
    ("HK", "HSTECH"): "hkHSTECH",
    ("US", "DJI"): "usDJI",
    ("US", "IXIC"): "usIXIC",
    ("US", "SPX"): "usINX",
    ("US", "NDX"): "usNDX",
}

#: (market, code) → 新浪代码。
SINA_MAP: Final[dict[tuple[str, str], str]] = {
    ("HK", "HSI"): "rt_hkHSI",
    ("HK", "HSCEI"): "rt_hkHSCEI",
    ("HK", "HSTECH"): "rt_hkHSTECH",
    ("US", "DJI"): "gb_dji",
    ("US", "IXIC"): "gb_ixic",
    ("US", "SPX"): "gb_inx",
    ("US", "NDX"): "gb_ndx",
}

#: 真指数集合（网关据此把请求分流到本模块，而不是发向 TDX 服务器）。
HTTP_INDEX_NAMES: Final[dict[str, str]] = {
    "HSI": "恒生指数",
    "HSCEI": "国企指数",
    "HSTECH": "恒生科技指数",
    "DJI": "道琼斯指数",
    "IXIC": "纳斯达克综合指数",
    "SPX": "标普500指数",
    "NDX": "纳斯达克100指数",
}


def is_http_index(market: str, code: str) -> bool:
    """判断是否为 HTTP 源真指数（TDX 服务器取不到的那 6 个）。"""
    from easy_tdx.markets import normalize_market

    try:
        token = normalize_market(market)
    except ValueError:
        return False
    return (token, (code or "").strip().upper()) in QQ_MAP


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data: Any = resp.read()
        return bytes(data)


# --------------------------------------------------------------------------- #
# 实时报价
# --------------------------------------------------------------------------- #


def fetch_quote(market: str, code: str) -> dict[str, Any]:
    """取真指数实时报价（新浪主，腾讯备）。

    Returns:
        ``{market, code, name, price, pre_close, open, high, low, amount}``；
        失败抛 ``RuntimeError``。
    """
    from easy_tdx.markets import normalize_market

    token = normalize_market(market)
    key = (token, code.strip().upper())
    try:
        return _sina_quote(key)
    except Exception as exc:  # noqa: BLE001 — 主源失败自动切备源
        logger.warning("新浪指数报价失败 %s%s，切腾讯: %s", token, code, exc)
    return _qq_quote(key)


def _sina_quote(key: tuple[str, str]) -> dict[str, Any]:
    sina_code = SINA_MAP[key]
    raw = _http_get(f"https://hq.sinajs.cn/list={sina_code}").decode("gbk", errors="replace")
    # var hq_str_rt_hkHSI="HSI,恒生指数,昨收,今开,最高,最低,今收,涨跌额,涨跌幅,...";
    # var hq_str_gb_ixic="纳斯达克,今收,涨跌幅,时间,涨跌额,昨收,最高,最低,...";
    start = raw.find('"')
    end = raw.rfind('"')
    if start < 0 or end <= start:
        raise RuntimeError(f"新浪返回为空: {sina_code}")
    parts = raw[start + 1 : end].split(",")
    if len(parts) < 8 or not parts[0]:
        raise RuntimeError(f"新浪无数据: {sina_code}")
    token, code = key
    if token == "HK":
        # HSI,恒生指数,昨收,今开,最高,最低,今收,涨跌额,涨跌幅
        name, pre, opn, high, low, close = (
            parts[1],
            parts[2],
            parts[3],
            parts[4],
            parts[5],
            parts[6],
        )
        amount = parts[12] if len(parts) > 12 else 0
    else:
        # 纳斯达克,今收,涨跌幅,时间,涨跌额,昨收,最高,最低
        name, close, _, _, _, pre, high, low = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
            parts[5],
            parts[6],
            parts[7],
        )
        opn = parts[1]
        amount = 0
    return {
        "market": token,
        "code": code,
        "name": name or HTTP_INDEX_NAMES.get(code, code),
        "price": float(close),
        "pre_close": float(pre),
        "open": float(opn),
        "high": float(high),
        "low": float(low),
        "amount": float(amount or 0),
    }


def _qq_quote(key: tuple[str, str]) -> dict[str, Any]:
    qq_code = QQ_MAP[key]
    prefix = "r_" if key[0] == "HK" else "ff_"
    raw = _http_get(f"https://qt.gtimg.cn/q={prefix}{qq_code}").decode("gbk", errors="replace")
    start = raw.find('"')
    end = raw.rfind('"')
    if start < 0 or end <= start:
        raise RuntimeError(f"腾讯返回为空: {qq_code}")
    parts = raw[start + 1 : end].split("~")
    if len(parts) < 6 or not parts[2]:
        raise RuntimeError(f"腾讯无数据: {qq_code}")
    token, code = key
    # HK: 100~名称~代码~今收~昨收~今开...~时间~涨跌额~涨跌幅~最高~最低...
    # US(ff_): 名称~今收~涨跌幅~时间~涨跌额~昨收~最高~最低...
    if token == "HK":
        name, close, pre, opn = parts[1], parts[3], parts[4], parts[5]
        high, low = (
            (parts[33] if len(parts) > 33 else close),
            (parts[34] if len(parts) > 34 else close),
        )
    else:
        name, close, pre = parts[0], parts[1], parts[5]
        opn, high, low = close, parts[6], parts[7]
    return {
        "market": token,
        "code": code,
        "name": name or HTTP_INDEX_NAMES.get(code, code),
        "price": float(close),
        "pre_close": float(pre),
        "open": float(opn),
        "high": float(high),
        "low": float(low),
        "amount": 0.0,
    }


def fetch_quotes(market: str, codes: list[str]) -> pd.DataFrame:
    """批量取真指数报价（逐个取，指数只有 6 个，量小）。"""
    rows: list[dict[str, Any]] = []
    for code in codes:
        try:
            rows.append(fetch_quote(market, code))
        except Exception as exc:  # noqa: BLE001 — 单只失败不阻断
            logger.warning("真指数报价失败 %s%s: %s", market, code, exc)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# K 线（腾讯 fqkline）
# --------------------------------------------------------------------------- #

_FQ_PERIOD: Final[dict[str, str]] = {
    "DAY": "day",
    "WEEK": "week",
    "MONTH": "month",
    "MIN_1": "m1",
    "MIN_5": "m5",
    "MIN_15": "m15",
    "MIN_30": "m30",
    "MIN_60": "m60",
}


def fetch_bars(
    market: str,
    code: str,
    category: str = "DAY",
    start: int = 0,
    count: int = 800,
) -> pd.DataFrame:
    """取真指数 K 线（腾讯 fqkline，日/周/月/分钟）。

    返回列与 /bars 契约对齐：日线 ``date``，分钟线 ``datetime``，
    外加 open/high/low/close/vol/amount。失败抛 ``RuntimeError``。
    """
    from easy_tdx.markets import normalize_market

    token = normalize_market(market)
    key = (token, code.strip().upper())
    qq_code = QQ_MAP[key]
    period = _FQ_PERIOD.get(category.upper(), "day")
    # 美股周/月线腾讯只给 1 根（接口限制），用日K本地聚合
    if token == "US" and period in ("week", "month"):
        return _resample_weekly_monthly(token, code, period, start, count)
    # 取够 start+count（fqkline 按条数从最新往回取）
    want = min(max(start + count, 10), 2000)
    url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={qq_code},{period},,,{want},qfq"
    payload = json.loads(_http_get(url).decode("utf-8", errors="replace"))
    try:
        rows = payload["data"][qq_code][period]
    except KeyError as exc:
        raise RuntimeError(f"腾讯无K线: {qq_code}/{period}") from exc
    if not rows:
        raise RuntimeError(f"腾讯K线为空: {qq_code}/{period}")
    # 行格式 [日期, 开, 收, 高, 低, 量]，分钟线日期为 "2026-10-09 0935"
    records: list[dict[str, Any]] = []
    for r in rows:
        dt = str(r[0]).strip()
        records.append(
            {
                "date" if len(dt) <= 10 else "datetime": dt.replace(" ", "T")
                if len(dt) > 10
                else dt,
                "open": float(r[1]),
                "close": float(r[2]),
                "high": float(r[3]),
                "low": float(r[4]),
                "vol": float(r[5]),
                "amount": 0.0,
            }
        )
    df = pd.DataFrame(records)
    is_minute = "datetime" in df.columns
    time_col = "datetime" if is_minute else "date"
    df = df.sort_values(time_col).reset_index(drop=True)
    # start/count 分页语义与 TDX 一致：start=0 从最新往回数
    if start or len(df) > count:
        total = len(df)
        lo = max(0, total - start - count)
        hi = max(0, total - start)
        df = df.iloc[lo:hi].reset_index(drop=True)
    return df


def _resample_weekly_monthly(
    market: str, code: str, period: str, start: int, count: int
) -> pd.DataFrame:
    """美股周/月线：腾讯只给 1 根，用日K本地聚合（周五收/月末收）。"""
    # 周线约需 count*7+30 根日K，月线约 count*32+60 根
    need = count * (32 if period == "month" else 7) + 60
    daily = fetch_bars(market, code, "DAY", 0, min(need, 2000))
    if daily.empty:
        raise RuntimeError(f"无日K可聚合: {market}:{code}")
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    rule = "W-FRI" if period == "week" else "ME"
    agg = df.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"}
    )
    agg["amount"] = 0.0
    agg = agg.dropna(subset=["close"]).reset_index()
    agg["date"] = agg["date"].dt.strftime("%Y-%m-%d")
    total = len(agg)
    lo = max(0, total - start - count)
    hi = max(0, total - start)
    return agg.iloc[lo:hi].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 分时（腾讯 minute/query，全天逐分钟点）
# --------------------------------------------------------------------------- #


def fetch_minute(market: str, code: str) -> pd.DataFrame:
    """取真指数当日分时（腾讯 minute/query）。

    返回平表 ``datetime/price/vol``（时间只有 HHMM，日期按今天）。
    失败抛 ``RuntimeError``。
    """
    from datetime import date

    from easy_tdx.markets import normalize_market

    token = normalize_market(market)
    key = (token, code.strip().upper())
    qq_code = QQ_MAP[key]
    url = f"https://ifzq.gtimg.cn/appstock/app/minute/query?code={qq_code}"
    payload = json.loads(_http_get(url).decode("utf-8", errors="replace"))
    try:
        points: list[str] = payload["data"][qq_code]["data"]["data"]
    except KeyError as exc:
        raise RuntimeError(f"腾讯无分时: {qq_code}") from exc
    if not points:
        raise RuntimeError(f"腾讯分时为空: {qq_code}")
    today = date.today().isoformat()
    rows = []
    for p in points:
        # "0930 23941.260 774816 7748155171.626"（时间 价格 量 金额）
        seg = p.split()
        if len(seg) < 2:
            continue
        rows.append(
            {
                "datetime": f"{today}T{seg[0][:2]}:{seg[0][2:]}:00",
                "price": float(seg[1]),
                "vol": float(seg[2]) if len(seg) > 2 else 0.0,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "QQ_MAP",
    "SINA_MAP",
    "HTTP_INDEX_NAMES",
    "is_http_index",
    "fetch_quote",
    "fetch_quotes",
    "fetch_bars",
    "fetch_minute",
]
