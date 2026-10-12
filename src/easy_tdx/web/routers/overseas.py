"""港股 / 美股路由：标的搜索、批量报价、市场元信息。

路径设计
--------
``/api/v1/overseas/*`` 是通用入口（``market=HK|US``）；
``/api/v1/us/*`` 是美股专用快捷路径，等价于 ``market=US`` 固定值——
保留它是因为前端早期版本已对接过这组路径，去掉会直接 404。

为什么走本地符号索引而不是直连服务器
------------------------------------
``MacExClient.goods_list`` 每次全量拉取美股要 4 秒（1.3 万只）、港股 4 秒
（3600 只，散在 5 个子市场），而前端搜索框是每键触发一次的。
:class:`easy_tdx.web.symbol_index` 把清单缓存到内存 + 磁盘
（``~/.easy_tdx/cache/``，12 小时 TTL），搜索走本地倒排，整次响应 <10ms。

索引拿不到时（扩展栈未连接）返回 503，而不是空列表——
空列表在前端表现为"搜不到任何东西"，比报错更难排查。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from easy_tdx.markets import (
    ALL_MARKETS,
    EX_MARKETS,
    MARKET_HK,
    MARKET_US,
    currency_label,
    ex_market_label,
    ex_market_values,
    is_ex,
    market_currency,
    market_label,
    normalize_market,
)
from easy_tdx.web import symbol_index
from easy_tdx.web.deps import get_gateway
from easy_tdx.web.market_gateway import validate_code
from easy_tdx.web.schemas import DataFrameResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["overseas"])

#: 允许的港美股子市场，供 OpenAPI 文档展示。
_MARKET_DESC = "市场: HK(港股) / US(美股)"


def _require_ex_market(market: str) -> str:
    """校验 market 是港股或美股，否则 400（不静默回落成 A 股）。"""
    token = normalize_market(market)
    if not is_ex(token):
        valid = " / ".join(m.upper() for m in EX_MARKETS)
        raise HTTPException(status_code=400, detail=f"市场必须为 {valid}，收到 '{market}'")
    return token


# --------------------------------------------------------------------------- #
# 标的搜索
# --------------------------------------------------------------------------- #


@router.get("/overseas/symbols")
@router.get("/us/symbols")
async def overseas_symbols(
    market: str = Query(MARKET_US, description=_MARKET_DESC),
    keyword: str | None = Query(None, description="按代码或名称模糊搜索；留空返回全部"),
    limit: int = Query(50, ge=1, le=500, description="最多返回条数"),
    refresh: bool = Query(False, description="跳过缓存强制回源刷新"),
) -> dict[str, Any]:
    """搜索港股 / 美股标的。

    返回每行含 ``symbol``（``HK:00700`` / ``US:AAPL`` 形式的令牌串）、
    ``market``、``code``、``name``、``ex_market``（子市场 int）与
    ``sub_market``（子市场中文名，如「主板」「创业板」）。

    排序：代码前缀命中 > 中文名前缀 > 中文名包含 > 代码包含。
    """
    token = _require_ex_market(market)
    try:
        index = await symbol_index.get_index_async(token, refresh=refresh)
    except Exception as exc:  # noqa: BLE001 — 统一转 503
        logger.warning("/overseas/symbols %s 索引加载失败: %s", token, exc)
        raise HTTPException(
            status_code=503, detail=f"{market_label(token)}标的列表不可用: {exc}"
        ) from exc

    if not index.rows:
        raise HTTPException(
            status_code=503,
            detail=f"{market_label(token)}标的列表为空：扩展市场协议栈（端口 7727）可能未连接",
        )

    rows = symbol_index._search_index(index, keyword or "", limit)
    return {
        "market": token,
        "label": market_label(token),
        "total": len(index.rows),
        "count": len(rows),
        "data": rows,
    }


@router.get("/overseas/symbols/count")
async def overseas_symbol_count(
    market: str = Query(MARKET_US, description=_MARKET_DESC),
) -> dict[str, Any]:
    """标的总数（走缓存索引，不额外打服务器）。"""
    token = _require_ex_market(market)
    try:
        index = await symbol_index.get_index_async(token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("/overseas/symbols/count 失败: %s", exc)
        raise HTTPException(status_code=503, detail=f"标的总数不可用: {exc}") from exc
    return {"market": token, "label": market_label(token), "total": len(index.rows)}


# --------------------------------------------------------------------------- #
# 批量报价
# --------------------------------------------------------------------------- #


@router.get("/overseas/quotes")
@router.get("/us/quotes")
async def overseas_quotes(
    market: str = Query(MARKET_US, description=_MARKET_DESC),
    codes: str = Query(..., description="逗号分隔的代码，如 AAPL,MSFT 或 00700,09988"),
    gateway: Any = Depends(get_gateway),
) -> DataFrameResponse:
    """批量获取港股 / 美股实时报价（五档 + 成交额 + 换手率等）。"""
    token = _require_ex_market(market)
    parsed = [validate_code(c, token) for c in codes.split(",") if c.strip()]
    if not parsed:
        return DataFrameResponse(data=[], count=0)
    if len(parsed) > 80:
        raise HTTPException(status_code=400, detail=f"单次最多 80 只，收到 {len(parsed)} 只")
    try:
        df = await gateway.quotes(token, parsed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("/overseas/quotes %s 获取失败: %s", token, exc)
        raise HTTPException(
            status_code=503, detail=f"{market_label(token)}报价不可用: {exc}"
        ) from exc
    return DataFrameResponse.from_dataframe(df)


# --------------------------------------------------------------------------- #
# 市场元信息
# --------------------------------------------------------------------------- #


@router.get("/overseas/meta")
@router.get("/us/meta")
async def overseas_meta(gateway: Any = Depends(get_gateway)) -> dict[str, Any]:
    """全部市场的元信息（前端顶栏的市场切换器据此渲染）。

    一次返回所有市场的可用性与标的总数，前端启动时打一次即可，
    不必为切换器逐个市场发请求。
    """
    result: dict[str, Any] = {
        "default_market": MARKET_HK,
        "markets": {},
        "ex_markets": {
            MARKET_HK: [
                {"value": v, "label": ex_market_label(v)} for v in ex_market_values(MARKET_HK)
            ]
        },
    }

    for token in ALL_MARKETS:
        entry: dict[str, Any] = {
            "label": market_label(token),
            "currency": market_currency(token),
            "currency_label": currency_label(token),
            "available": True,
        }
        if is_ex(token):
            available = gateway.ex_available
            entry["available"] = available
            if available:
                try:
                    entry["symbol_count"] = len((await symbol_index.get_index_async(token)).rows)
                except Exception:  # noqa: BLE001 — 拿不到总数不算失败
                    logger.warning("/overseas/meta %s 总数获取失败", token, exc_info=True)
                    entry["symbol_count"] = None
            else:
                entry["symbol_count"] = None
                entry["unavailable_reason"] = "扩展市场协议栈（端口 7727）未连接"
        result["markets"][token] = entry

    return result


# --------------------------------------------------------------------------- #
# 全市场榜单
# --------------------------------------------------------------------------- #


@router.get("/overseas/rank")
async def overseas_rank(
    market: str = Query(MARKET_US, description=_MARKET_DESC),
) -> dict[str, Any]:
    """港股 / 美股全市场榜单（涨幅 / 跌幅 / 成交额 / 成交量 Top30 + 涨跌家数）。

    全量翻页港股约 20 秒、美股约 70 秒，不可能在请求内同步完成——
    首次返回 ``{"status": "building"}``，前端每 2 秒轮询直到
    ``{"status": "ready"}``。快照缓存 5 分钟。
    """
    from easy_tdx.web.overseas_rank import rank_snapshot

    token = _require_ex_market(market)
    try:
        return rank_snapshot(token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("/overseas/rank %s 失败: %s", token, exc)
        raise HTTPException(
            status_code=503, detail=f"{market_label(token)}榜单不可用: {exc}"
        ) from exc


__all__ = ["router"]
