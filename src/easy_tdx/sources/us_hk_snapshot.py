"""港美股个股免费快照数据源（新浪主 + 东财 push2 备，无需 API Key）。

为什么需要个股 HTTP 源
----------------------
通达信 7727 扩展栈是港美股主力，但在未连接、单只取数失败时需要兜底。
已有的 :mod:`easy_tdx.sources.qq_index` / ``em_index`` 只覆盖**指数**
（HSI/DJI 等 6 只）；个股（AAPL/00700 等）没有免费 HTTP 兜底，本模块补上。

免费 HTTP 源实测可用（2026-10-14，AAPL/00700/MSFT 多源交叉验证价格一致）：

====================  ============================  ========================
数据源                 接口                            说明
====================  ============================  ========================
新浪 hq.sinajs（主）   ``gb_aapl`` / ``rt_hk00700`` GBK逗号串；美股昨收由
                                                  现价-涨跌额推导；实测
                                                  抗限频最强（连续十余次
                                                  零失败）
东财 push2（备）       ``push2.eastmoney.com/api/qt/ 干净 JSON（``rc`` 状态码），
                      stock/get``                   价格字段 ×1000，另带昨收/
                                                  量/额；美股 105=NASDAQ/
                                                  106=NYSE/107=AMEX 依次试，
                                                  港股 116
====================  ============================  ========================

主备顺序说明：东财字段更全，但实测中连续探测十余次后对本机 IP 断连接
限频且窗口长；新浪全程稳定。回落链的首要目标是**不断供**，故新浪在前、
东财在后——与 :mod:`easy_tdx.sources.em_index` 把东财放链尾的经验一致。

本模块是纯 HTTP（urllib），无第三方依赖、无需 Key。超时短（8 秒）、
失败抛异常由上层转 503——拿不到就显示"—"，不炸整个看板。

延迟说明：两源都是**秒级快照**（实测时间戳与请求时刻一致），满足
"1 分钟延迟可接受"的场景；不要当交易所级实时 tick 用。
``EASY_TDX_US_HK_SNAPSHOT=0`` 可关闭。

限频说明（实测）：调用方（如 SSE 轮询）应控制批量频率，避免把两源
同时打进限频；本模块单只失败即换下一路（不重试、不等待），保证
回落链整体快速收敛。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any, Final

import pandas as pd

from easy_tdx.markets import MARKET_HK, MARKET_US

logger = logging.getLogger(__name__)

__all__ = ["is_enabled", "fetch_quotes", "fetch_quote"]

#: 关闭开关（与 akshare/baostock 的 ``=0 关闭``惯例一致）。
_DISABLE_ENV: Final = "EASY_TDX_US_HK_SNAPSHOT"

#: 请求超时（秒），与 qq_index 一致。
_TIMEOUT: Final = 8.0

#: 东财 push2 取数字段：现价/最高/最低/今开/量/额/昨收/代码/名称。
_EM_FIELDS: Final = "f43,f44,f45,f46,f47,f48,f60,f57,f58"

#: 东财价格字段除数（实测 341270→341.27，423400→423.40）。
_EM_PRICE_DIV: Final = 1000.0

#: 美股 secid 前缀候选（东财分区）：105=NASDAQ，106=NYSE，107=AMEX。
#: 按序首个 ``rc==0 且有 data`` 者胜出；AAPL 实测 105 命中。
_US_SECIDS: Final = ("105", "106", "107")

#: 港股 secid 前缀（5 位数字代码，如 00700）。
_HK_SECID: Final = "116"


def is_enabled() -> bool:
    """本数据源是否可用（纯标准库、无 Key，默认开；``=0`` 关）。"""
    return os.environ.get(_DISABLE_ENV, "").strip() != "0"


def _http_get_text(url: str, encoding: str = "utf-8") -> str:
    """GET 取文本（东财 JSON 用 utf-8，新浪用 gbk）。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://finance.sina.com.cn",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — 固定数据源域
        return str(resp.read().decode(encoding, errors="ignore"))


# --------------------------------------------------------------------------- #
# 新浪（主）
# --------------------------------------------------------------------------- #


def _sina_symbol(market: str, code: str) -> str:
    """本项目 ``(code, market)`` → 新浪 symbol（美股 ``gb_aapl``，港股 ``rt_hk00700``）。"""
    token = market.upper()
    c = str(code).strip()
    if token == MARKET_US:
        return f"gb_{c.lower()}"
    if token == MARKET_HK:
        digits = "".join(ch for ch in c if ch.isdigit())
        return f"rt_hk{digits.zfill(5)}"
    return ""


def _sina_quote(market: str, code: str) -> dict[str, Any] | None:
    """新浪单只报价；失败返回 None。"""
    symbol = _sina_symbol(market, code)
    if not symbol:
        return None
    try:
        text = _http_get_text(f"https://hq.sinajs.cn/list={symbol}", encoding="gbk")
    except Exception as exc:  # noqa: BLE001 — 主源失败换备源
        logger.debug("新浪 %s 请求失败: %s", symbol, exc)
        return None
    try:
        payload = text.split('="', 1)[1].rsplit('"', 1)[0]
    except IndexError:
        return None
    parts = payload.split(",")
    token = market.upper()
    try:
        if token == MARKET_US:
            # gb_ 格式：名称,现价,涨跌幅,时间,涨跌额,开,高,低,...
            # 昨收无直接列，由 现价-涨跌额 推导（与 test_qq_index 同口径）。
            # 扩展时段（盘前/盘后）三元组见 _ext_fields（单样本无法区分盘前
            # 还是盘后，只保证是实时更新的扩展时段价；坏了不丢整行）。
            price = float(parts[1])
            change = float(parts[4])
            ext_price, ext_change, ext_pct = _ext_fields(parts)
            ext_vol, ext_amount = _ext_va_fields(parts)
            return {
                "market": token,
                "code": str(code).strip(),
                "price": price,
                "pre_close": price - change,
                "open": float(parts[5]),
                "high": float(parts[6]),
                "low": float(parts[7]),
                "vol": None,
                "amount": None,
                "ext_price": ext_price,
                "ext_change": ext_change,
                "ext_pct": ext_pct,
                "ext_vol": ext_vol,
                "ext_amount": ext_amount,
                "name": parts[0],
                "source": "sina",
            }
        # rt_hk 格式：名称,中文名,开,昨收,高,低,现价,涨跌额,涨跌幅,...
        # 港股串无扩展时段字段，ext_* 置 None（与东财行对齐列）。
        return {
            "market": token,
            "code": str(code).strip(),
            "price": float(parts[6]),
            "pre_close": float(parts[3]),
            "open": float(parts[2]),
            "high": float(parts[4]),
            "low": float(parts[5]),
            "vol": None,
            "amount": None,
            "ext_price": None,
            "ext_change": None,
            "ext_pct": None,
            "ext_vol": None,
            "ext_amount": None,
            "name": parts[1] or parts[0],
            "source": "sina",
        }
    except (IndexError, ValueError):
        return None


def _ext_fields(parts: list[str]) -> tuple[float | None, float | None, float | None]:
    """新浪美股扩展时段三元组 → ``(价, 涨跌额, 涨跌幅)``。

    位置（2026-10-14 实测 ``gb_aapl`` 36 字段）：``[21]``价、``[22]``幅、
    ``[23]``额。量级自洽：342.74-341.27=1.47（额），1.47/341.27=0.43%（幅）；
    跨时段漂移（342.74→342.8→342.87）证实实时更新。
    缺失/非法一律 None——扩展字段坏了不能丢整行常规报价。
    """
    try:
        return float(parts[21]), float(parts[23]), float(parts[22])
    except (IndexError, ValueError):
        return None, None, None


def _ext_va_fields(parts: list[str]) -> tuple[float | None, float | None]:
    """新浪美股扩展时段量额 → ``(成交量, 成交额)``。

    解码依据（2026-10-14 盘前双样本 × AAPL/MSFT 双标的）：
    ``[27]`` 与 ``[33]`` 在盘前持续增长（123250→129106，4101万→4424万），
    增量比值 Δ33/Δ27 ≈ 现价（2006933/5856≈342.7），故 ``[27]``=量、
    ``[33]``=额。常规量（``[10]``）盘前冻结，可作对照。
    未解码：``[31]/[32]/[34]`` 全天冻结，疑为盘前 OHLC 或昨日盘后
    OHLC（两种假设都自洽），需观察盘前突破其极值时是否更新才能定夺，
    在此之前不映射（宁可缺，不可错）。
    """
    try:
        return float(parts[27]), float(parts[33])
    except (IndexError, ValueError):
        return None, None


# --------------------------------------------------------------------------- #
# 东财 push2（备）
# --------------------------------------------------------------------------- #


def _em_secid(market: str, code: str) -> list[str]:
    """本项目 ``(code, market)`` → 东财 secid 候选列表。"""
    token = market.upper()
    c = str(code).strip().upper()
    if token == MARKET_US:
        return [f"{s}.{c}" for s in _US_SECIDS]
    if token == MARKET_HK:
        digits = "".join(ch for ch in c if ch.isdigit())
        return [f"{_HK_SECID}.{digits.zfill(5)}"]
    return []


def _em_fetch_one(secid: str) -> dict[str, Any] | None:
    """取单个 secid；成功返回 ``data`` 段，失败返回 None（换候选/换源）。"""
    url = (
        "https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={urllib.parse.quote(secid)}&fields={_EM_FIELDS}"
    )
    try:
        body = json.loads(_http_get_text(url))
    except Exception as exc:  # noqa: BLE001 — 网络/解码失败换下一候选
        logger.debug("东财 %s 请求失败: %s", secid, exc)
        return None
    if not isinstance(body, dict) or body.get("rc") != 0:
        return None
    data = body.get("data")
    return data if isinstance(data, dict) and data else None


def _em_quote(market: str, code: str) -> dict[str, Any] | None:
    """东财单只报价；全部候选失败返回 None。"""
    for secid in _em_secid(market, code):
        data = _em_fetch_one(secid)
        if data is None:
            continue
        div = _EM_PRICE_DIV
        return {
            "market": market.upper(),
            "code": str(code).strip(),
            "price": _num(data.get("f43"), div),
            "pre_close": _num(data.get("f60"), div),
            "open": _num(data.get("f46"), div),
            "high": _num(data.get("f44"), div),
            "low": _num(data.get("f45"), div),
            "vol": _num(data.get("f47")),
            "amount": _num(data.get("f48")),
            "ext_price": None,  # 东财快照无扩展时段字段（与新浪行对齐列）
            "ext_change": None,
            "ext_pct": None,
            "ext_vol": None,
            "ext_amount": None,
            "name": str(data.get("f58") or ""),
            "source": "em",
        }
    return None


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #


def fetch_quote(market: str, code: str) -> dict[str, Any]:
    """单只港美股快照（新浪主 → 东财备）。

    Raises:
        RuntimeError: 本模块被关闭 / 两源都失败。
    """
    if not is_enabled():
        raise RuntimeError("港美股个股快照源已关闭（EASY_TDX_US_HK_SNAPSHOT=0）")
    row = _sina_quote(market, code)
    if row is not None:
        return row
    row = _em_quote(market, code)
    if row is not None:
        logger.info("新浪 %s:%s 失败，回落东财", market, code)
        return row
    raise RuntimeError(f"港美股快照两源都失败：{market}:{code}")


def fetch_quotes(codes: list[tuple[str, str]]) -> pd.DataFrame:
    """批量个股快照（``[(code, market), ...]``）。

    单只失败跳过（行级降级，整批不失败）；全部失败返回空表。
    返回列对齐项目报价契约（另带 ``name``/``source``；美股新浪行另带
    ``ext_price``/``ext_change``/``ext_pct``/``ext_vol``/``ext_amount``
    扩展时段五元组）。
    """
    rows: list[dict[str, Any]] = []
    for code, market in codes:
        try:
            rows.append(fetch_quote(market, code))
        except Exception as exc:  # noqa: BLE001 — 单只失败不中断整批
            logger.warning("个股快照失败 %s:%s: %s", market, code, exc)
    return pd.DataFrame(rows)


def _num(value: Any, div: float = 1.0) -> float | None:
    """数值清洗（None/非法 → None；东财价格先除以 1000）。"""
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num / div if div != 1.0 else num
