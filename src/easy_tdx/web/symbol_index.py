"""港股 / 美股符号索引：代码 → 子市场 / 中文名 / 搜索。

为什么需要这一层
----------------
港股在通达信里被拆成 5 个 ``ExMarket`` 子市场（主板 31 / 创业板 48 /
基金 49 / 指数 27 / 暗盘 98），而前端只认一个 ``HK`` 令牌。拿到
``("HK", "00700")`` 这对令牌后，必须反查它具体属于哪个子市场，
否则请求会打到错误的服务器分区上。

代码格式无法自行推断归属，因为存在真实歧义：

* 港股指数代码是字母（``CES100``），与美股 ticker（``AAPL``）完全同形
* 港股基金与主板同为 5 位数字，靠前缀区分不可靠

所以只能以服务器返回的标的清单为准——这��是「每个标的自带市场标识」
在服务端的落地。

数据来源与缓存
--------------
``MacExClient.goods_list(ex_market)``，全量约 2 秒：

============  ======  =========================================
市场           标的数   说明
============  ======  =========================================
US (74)        13391   字母 ticker
HK (31)        2525    主板
HK (48)        314     创业板
HK (49)        477     ETF / 基金
HK (27)        321     指数（字母代码，如 ``CES100``）
HK (98)        4       暗盘
============  ======  =========================================

首次加载后落盘到 ``~/.easy_tdx/cache/symbols_{market}.json``，
默认 12 小时 TTL，进程内另有内存缓存；``refresh=True`` 强制回源。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Final

from easy_tdx.markets import (
    HK_DEFAULT_EX_MARKET,
    HK_EX_MARKET_NAMES,
    MARKET_HK,
    MARKET_US,
    ex_market_label,
    ex_market_values,
    normalize_market,
)

logger = logging.getLogger(__name__)

#: 磁盘缓存有效期（秒）。12 小时：覆盖一个交易日，又能让新上市标的当天可见。
_CACHE_TTL: Final = 12 * 3600

#: 单次向服务器拉取的子市场分页大小。
_FETCH_BATCH: Final = 3000

#: 进程内内存缓存的市场令牌 → (过期时间戳, 索引)。
_MEM_CACHE: Final[dict[str, tuple[float, _SymbolIndex]]] = {}

#: 同一市场的并发加载只打一次服务器（其余调用等待同一个 future 结果）。
_LOAD_LOCK: Final = threading.Lock()


def _cache_dir() -> Path:
    """符号索引缓存目录（随 ``EASY_TDX_CONFIG_DIR`` 走）。"""
    base = Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))
    return base / "cache"


def _cache_path(market: str) -> Path:
    return _cache_dir() / f"symbols_{market.lower()}.json"


class _SymbolIndex:
    """单个市场的符号索引（不可变）。"""

    __slots__ = ("market", "by_code", "rows", "loaded_at")

    def __init__(self, market: str, rows: list[dict[str, Any]]) -> None:
        self.market = market
        self.rows = rows
        self.loaded_at = time.time()
        # 归一化为大写键，便于大小写不敏感地查代码
        self.by_code: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = str(row.get("code") or "").strip().upper()
            if code:
                self.by_code[code] = row


# --------------------------------------------------------------------------- #
# 同步入口（CLI / 脚本用）
# --------------------------------------------------------------------------- #


def get_index(market: str, *, client: Any = None, refresh: bool = False) -> _SymbolIndex:
    """取指定市场的符号索引（同步版）。

    Args:
        market: 市场令牌，如 ``"HK"`` / ``"US"``。
        client: 已连接的 ``MacExClient``/``MacExClient`` 实例。
            为 None 时就地新建并关闭（一次性查询用）。
        refresh: True 时跳过缓存强制回源。

    Returns:
        符号索引；拉取失败且无缓存时返回空索引（不抛异常——
        上层可以退化成"按主板兜底"而不是整体失败）。
    """
    token = normalize_market(market)
    if token not in (MARKET_HK, MARKET_US):
        raise ValueError(f"符号索引只支持港股/美股，收到 '{market}'")

    now = time.time()
    with _LOAD_LOCK:
        cached = _MEM_CACHE.get(token)
        if not refresh and cached and cached[0] > now:
            return cached[1]

    disk = _load_from_disk(token, refresh)
    if disk is not None:
        _MEM_CACHE[token] = (time.time() + _CACHE_TTL, disk)
        return disk

    own_client = client is None
    # connect() 必须在 try 内：from_best_host() 会 ping 全部候选 host、connect()
    # 会真正建连，二者恰恰最常抛异常（扩展行情服务器不可达是常态）。放在
    # try/finally 之外时，一旦抛错就永远走不到 finally，每次请求泄漏一条 socket。
    client_to_close = None
    try:
        if own_client:
            from easy_tdx import MacExClient

            client = MacExClient.from_best_host()
            client.connect()
            client_to_close = client
        rows = _fetch_all(client, token)
    except Exception as exc:  # noqa: BLE001 — 索引失败不应炸掉整个请求
        logger.warning("拉取 %s 符号索引失败: %s", token, exc)
        rows = []
    finally:
        if client_to_close is not None:
            try:
                client_to_close.close()
            except Exception:  # noqa: BLE001,S110 — 关闭失败无所谓
                pass

    index = _SymbolIndex(token, rows)
    if rows:
        _save_to_disk(index)
    else:
        # 回源失败但进程内有旧索引 → 降级用旧的，不要返回空
        stale = _MEM_CACHE.get(token)
        if stale:
            logger.warning("%s 索引回源失败，沿用进程内旧快照", token)
            return stale[1]

    if not rows:
        # 回源失败且进程内无任何旧快照时**不要**把空索引写进 _MEM_CACHE：
        # 否则一次网络抖动会让全市场标的搜索/查名在 _CACHE_TTL（12 小时）内
        # 永远返回空，且不会自动重试（只有 refresh=1 能绕过）。
        logger.warning("%s 符号索引为空且无可用缓存，本次不写入缓存以便下次重试", token)
        return index

    _MEM_CACHE[token] = (time.time() + _CACHE_TTL, index)
    return index


def lookup_ex_market(code: str, *, market: str = MARKET_HK) -> int | None:
    """查代码所属的子市场 int 取值。

    仅港股需要——A 股与美股的市场码是单字节的，无需解析。

    Args:
        code: 证券代码（大小写不敏感）。
        market: 市场令牌，默认港股。

    Returns:
        子市场 int（如主板 31）；查不到返回 None。

    >>> lookup_ex_market("00700")
    31
    """
    token = normalize_market(market)
    if token != MARKET_HK:
        return None
    index = get_index(token)
    row = index.by_code.get((code or "").strip().upper())
    if row is None:
        return None
    return int(row.get("ex_market") or HK_DEFAULT_EX_MARKET)


def lookup_symbol(code: str, *, market: str = MARKET_HK) -> dict[str, Any] | None:
    """查代码的完整标的行（含中文名与子市场）。

    Args:
        code: 证券代码。
        market: 市场令牌。

    Returns:
        ``{"code","name","ex_market","market","sub_market","symbol"}``；
        查不到返回 None。
    """
    token = normalize_market(market)
    index = get_index(token)
    row = index.by_code.get((code or "").strip().upper())
    if row is None:
        return None
    return _to_symbol(token, row)


def search(
    keyword: str,
    *,
    market: str = MARKET_HK,
    limit: int = 30,
    client: Any = None,
) -> list[dict[str, Any]]:
    """按代码前缀或中文名模糊搜索标的。

    搜索结果按「代码前缀命中 > 中文名包含 > 代码包含」排序，
    同档内按代码升序，保证结果稳定可复现。

    Args:
        keyword: 搜索词。
        market: 市场令牌（``HK`` / ``US``）。
        limit: 最多返回条数。
        client: 可选的已连接客户端（避免调用方重复建连）。

    Returns:
        标的行列表，每行含 ``symbol``（``HK:00700`` 形式的令牌串）。
    """
    token = normalize_market(market)
    key = (keyword or "").strip().upper()
    if not key:
        return []

    index = get_index(token, client=client)

    scored: list[tuple[int, str, dict[str, Any]]] = []
    for code, row in index.by_code.items():
        name = str(row.get("name") or "").strip()
        if code.startswith(key):
            rank = 0
        elif name.upper().startswith(key):
            rank = 1
        elif key in name.upper():
            rank = 2
        elif key in code:
            rank = 3
        else:
            continue
        scored.append((rank, code, row))

    scored.sort(key=lambda t: (t[0], t[1]))
    return [_to_symbol(token, row) for _, _, row in scored[: max(limit, 0)]]


def count(market: str, *, client: Any = None) -> int:
    """取该市场的标的总数（走索引，不额外打服务器）。"""
    return len(get_index(normalize_market(market), client=client).rows)


# --------------------------------------------------------------------------- #
# 内部实现
# --------------------------------------------------------------------------- #


def _fetch_all(client: Any, token: str) -> list[dict[str, Any]]:
    """从服务器拉取该市场全部子市场的标的清单（分页直到取完）。"""
    rows: list[dict[str, Any]] = []
    for ex_market in ex_market_values(token):
        try:
            total = int(client.goods_count(ex_market) or 0)
        except Exception as exc:  # noqa: BLE001 — 拿不到总数就只取第一页
            logger.warning("取 %s 子市场 %s 总数失败，退回单页: %s", token, ex_market, exc)
            total = _FETCH_BATCH

        offset = 0
        while True:
            try:
                df = client.goods_list(ex_market, start=offset, count=_FETCH_BATCH)
            except Exception as exc:  # noqa: BLE001 — 单页失败不阻断其余
                logger.warning(
                    "拉取 %s 子市场 %s offset=%d 失败: %s", token, ex_market, offset, exc
                )
                break
            if df is None or len(df) == 0:
                break
            for rec in df.to_dict(orient="records"):
                code = str(rec.get("code") or "").strip()
                if not code:
                    continue
                rows.append(
                    {
                        "code": code,
                        "name": str(rec.get("name") or "").strip(),
                        # goods_list 的 market 列可能缺失，以请求的子市场为准
                        "ex_market": int(rec.get("market") or ex_market),
                        "category": int(rec.get("category") or 0),
                    }
                )
            offset += len(df)
            # 已取满或服务器返回不满一页（末页）→ 停
            if total and offset >= total:
                break
            if len(df) < _FETCH_BATCH:
                break
    logger.info("%s 符号索引加载完成：%d 只", token, len(rows))
    # 真指数（TDX 无，HTTP 源）：保证搜索/解析能找到它们
    rows.extend(_http_index_rows(token))
    return rows


def _http_index_rows(token: str) -> list[dict[str, Any]]:
    """真指数补录行（source=http，ex_market 占位不用于实际请求）。"""
    try:
        from easy_tdx.sources.qq_index import HTTP_INDEX_NAMES, QQ_MAP
    except ImportError:
        return []
    rows: list[dict[str, Any]] = []
    for mkt, code in QQ_MAP:
        if mkt != token:
            continue
        rows.append(
            {
                "code": code,
                "name": HTTP_INDEX_NAMES.get(code, code),
                "ex_market": 27 if token == MARKET_HK else 74,
                "category": 5,  # 指数分类（与 TDX 27 分区口径一致）
                "source": "http",
            }
        )
    return rows


def _to_symbol(token: str, row: dict[str, Any]) -> dict[str, Any]:
    """内部行 → 对外的 symbol 行（含 ``symbol`` 令牌串与中文市场标签）。"""
    ex_market = int(row.get("ex_market") or HK_DEFAULT_EX_MARKET)
    code = str(row.get("code") or "")
    return {
        "symbol": f"{token}:{code}",
        "market": token,
        "code": code,
        "name": str(row.get("name") or ""),
        "ex_market": ex_market,
        "sub_market": ex_market_label(ex_market) or HK_EX_MARKET_NAMES.get(ex_market, ""),
        "category": int(row.get("category") or 0),
    }


def _load_from_disk(token: str, refresh: bool) -> _SymbolIndex | None:
    """读磁盘缓存；不存在 / 过期 / 损坏都返回 None（触发回源）。"""
    if refresh:
        return None
    path = _cache_path(token)
    try:
        if not path.exists() or time.time() - path.stat().st_mtime > _CACHE_TTL:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            return None
        return _SymbolIndex(token, rows)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("读取 %s 符号缓存失败，回源: %s", path, exc)
        return None


def _save_to_disk(index: _SymbolIndex) -> None:
    """落盘（失败只告警——缓存是可再生的，不该因此让请求失败）。"""
    path = _cache_path(index.market)
    payload = {"market": index.market, "loaded_at": index.loaded_at, "rows": index.rows}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("写入 %s 符号缓存失败: %s", path, exc)


# --------------------------------------------------------------------------- #
# FastAPI 依赖用的异步入口
# --------------------------------------------------------------------------- #


async def get_index_async(
    market: str,
    *,
    client: Any = None,
    refresh: bool = False,
) -> _SymbolIndex:
    """异步版 :func:`get_index`。

    同步 :func:`get_index` 里的建连 + 拉取会阻塞事件循环，这里把
    「回源」交给线程池跑，命中内存/磁盘缓存时零开销。
    """
    token = normalize_market(market)
    if token not in (MARKET_HK, MARKET_US):
        raise ValueError(f"符号索引只支持港股/美股，收到 '{market}'")

    now = time.time()
    with _LOAD_LOCK:
        cached = _MEM_CACHE.get(token)
        if not refresh and cached and cached[0] > now:
            return cached[1]

    import asyncio

    # _load_from_disk 是同步磁盘 IO（stat + read_text + json.loads）；美股索引
    # 上万个条目时解析耗时可观，放在事件循环里会卡住其他请求。
    disk = await asyncio.to_thread(_load_from_disk, token, refresh)
    if disk is not None:
        _MEM_CACHE[token] = (time.time() + _CACHE_TTL, disk)
        return disk

    loop = asyncio.get_running_loop()
    # 透传 client：此前这里固定 refresh=True 且不传 client，导致即使调用方已经
    # 持有共享的 MacExClient（app.state.mac_ex_client），每次冷路径刷新仍会另起
    # 一条 from_best_host()+connect() 的连接，用完再关——白白多一次建连+全网探测。
    return await loop.run_in_executor(None, lambda: get_index(token, client=client, refresh=True))


async def search_async(
    keyword: str,
    *,
    market: str = MARKET_HK,
    limit: int = 30,
    client: Any = None,
) -> list[dict[str, Any]]:
    """异步版 :func:`search`。"""
    token = normalize_market(market)
    index = await get_index_async(token, client=client)
    return _search_index(index, keyword, limit)


async def lookup_ex_market_async(code: str, *, market: str = MARKET_HK) -> int | None:
    """异步版 :func:`lookup_ex_market`。"""
    token = normalize_market(market)
    if token != MARKET_HK:
        return None
    index = await get_index_async(token)
    row = index.by_code.get((code or "").strip().upper())
    if row is None:
        return None
    return int(row.get("ex_market") or HK_DEFAULT_EX_MARKET)


async def lookup_symbol_async(code: str, *, market: str = MARKET_HK) -> dict[str, Any] | None:
    """异步版 :func:`lookup_symbol`（查代码的完整标的行）。"""
    token = normalize_market(market)
    index = await get_index_async(token)
    row = index.by_code.get((code or "").strip().upper())
    if row is None:
        return None
    return _to_symbol(token, row)


def _search_index(index: _SymbolIndex, keyword: str, limit: int) -> list[dict[str, Any]]:
    """在已有索引上做搜索（同步/异步共用同一套打分逻辑）。"""
    key = (keyword or "").strip().upper()
    if not key:
        return []
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for code, row in index.by_code.items():
        name = str(row.get("name") or "").strip()
        if code.startswith(key):
            rank = 0
        elif name.upper().startswith(key):
            rank = 1
        elif key in name.upper():
            rank = 2
        elif key in code:
            rank = 3
        else:
            continue
        scored.append((rank, code, row))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [_to_symbol(index.market, row) for _, _, row in scored[: max(limit, 0)]]


def clear_cache(market: str | None = None) -> None:
    """清空内存 / 磁盘缓存（改代码后自测用）。

    Args:
        market: 只清某个市场；None 表示全清。
    """
    tokens = (normalize_market(market),) if market else (MARKET_HK, MARKET_US)
    for token in tokens:
        _MEM_CACHE.pop(token, None)
        try:
            _cache_path(token).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("删除 %s 符号缓存失败: %s", token, exc)


__all__ = [
    "get_index",
    "get_index_async",
    "search",
    "search_async",
    "lookup_ex_market",
    "lookup_ex_market_async",
    "lookup_symbol",
    "lookup_symbol_async",
    "count",
    "clear_cache",
]
