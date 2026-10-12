"""港股 / 美股全市场榜单：后台翻页拉取 + 缓存快照。

为什么需要后台任务
------------------
扩展市场报价接口（MAC 0x122B）单次最多 80 只，而港股可交易标的约 2800 只
（主板 31 + 创业板 48）、美股约 1.3 万只。全量翻页港股约 20 秒、美股约
70 秒——HTTP 请求内同步等必然超时。

所以这里仿照 ``/board-mac/hotspot`` 的 building 模式：

* 首次请求触发后台线程全量拉取，立即返回 ``{"status": "building"}``
* 前端每 2 秒轮询，直至 ``{"status": "ready", "data": {...}}``
* 快照缓存 5 分钟（``_SNAPSHOT_TTL``），命中时零行情请求直接返回

榜单范围
--------
只统计**可交易的股票**：港股主板（31）+ 创业板（48）；指数（27）、
基金（49）、暗盘（98）不计入——ETF 涨跌幅小会淹没榜单，暗盘只有 4 只。
美股全量（74）一次拉取。

返回的每行含 ``change_pct``（现价/昨收-1，前端直接渲染，无需再算）。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Final

import pandas as pd

from easy_tdx.markets import MARKET_HK, MARKET_US, is_ex, market_label, normalize_market

logger = logging.getLogger(__name__)

#: 快照有效期（秒）。5 分钟：榜单不需要秒级新鲜度，太短会频繁触发 70 秒级全量。
_SNAPSHOT_TTL: Final = 300

#: 后台拉取的单页大小（协议上限 80）。
_PAGE_SIZE: Final = 80

#: 榜单范围：港股只取主板 + 创业板（可交易股票）。
_RANK_EX_MARKETS: Final[dict[str, tuple[int, ...]]] = {
    MARKET_HK: (31, 48),
    MARKET_US: (74,),
}

#: 每榜返回条数（成交量排名需求 Top30，其余榜同步 30 对齐前端表格高度）。
_TOP_N: Final = 30

#: 涨跌分布桶（与前端看板 BUCKETS 对齐，共 22 桶）：
#: [0]='≤-10'，[1..10]='-10'..'-1'，[11]='0'，[12..20]='+1'..'+9'，[21]='≥10'。
#: 桶公式 idx = 11 + floor(pct)，两端 clamp（与 DashboardView.loadDist 同口径）。
_DIST_BUCKETS: Final = 22

_lock: Final = threading.Lock()
_snapshots: Final[dict[str, dict[str, Any]]] = {}
_building: Final[set[str]] = set()


def rank_snapshot(market: str) -> dict[str, Any]:
    """取榜单快照；缺失/过期时触发后台刷新并返回 building 状态。

    Returns:
        ``{"status": "ready", "data": {...}, "updated_at": ...}`` 或
        ``{"status": "building", "progress": "x/y"}``。
    """
    token = normalize_market(market)
    if not is_ex(token):
        raise ValueError(f"榜单只支持港股/美股，收到 '{market}'")

    now = time.time()
    with _lock:
        snap = _snapshots.get(token)
        if snap and now - snap["built_at"] < _SNAPSHOT_TTL:
            return {"status": "ready", **snap["payload"]}
        building = token in _building
        progress = snap.get("progress", "") if snap else ""
        if not building:
            _building.add(token)
            _start_build(token)
        return {"status": "building", "progress": progress}


def _start_build(token: str) -> None:
    """起后台线程（daemon），主线程立即返回。"""

    def _run() -> None:
        try:
            _build(token)
        except Exception:  # noqa: BLE001 — 后台失败只记日志，前端下轮重试
            logger.warning("港美股榜单构建失败 (%s)", token, exc_info=True)
        finally:
            with _lock:
                _building.discard(token)

    t = threading.Thread(target=_run, name=f"overseas-rank-{token}", daemon=True)
    t.start()


def _build(token: str) -> None:
    """后台全量翻页拉取 + 排序 + 落快照（多服务器容灾：逐个候选 host 重试）。"""
    from easy_tdx.config import get_mac_ex_hosts
    from easy_tdx.ex.mac_client import MacExClient

    # 候选服务器轮询容灾：best host 优先，其余按配置顺序兜底。
    # MacExClient(host) 直连指定 host，避免 from_best_host 每次 ping 全量
    # （榜单构建本身已是 20~70 秒，省一次全量 ping）。
    try:
        from easy_tdx.config import get_best_mac_ex_host

        ordered = [get_best_mac_ex_host()] + [
            h for h in get_mac_ex_hosts() if h != get_best_mac_ex_host()
        ]
    except Exception:  # noqa: BLE001 — 兜底走默认列表
        ordered = list(get_mac_ex_hosts())

    last_exc: Exception | None = None
    for host in ordered:
        client = MacExClient(host=host)
        try:
            client.connect()
        except Exception as exc:  # noqa: BLE001 — 换下一台继续
            last_exc = exc
            logger.warning("港美股榜单连接 %s 失败，尝试下一台: %s", host, exc)
            try:
                client.close()
            except Exception:  # noqa: BLE001,S110
                pass
            continue
        try:
            _build_with_client(token, client)
            return
        except Exception as exc:  # noqa: BLE001 — 拉取中失败也换下一台
            last_exc = exc
            logger.warning("港美股榜单拉取经 %s 失败，尝试下一台: %s", host, exc)
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001,S110
                pass
    logger.warning("港美股榜单全部服务器失败 (%s): %s", token, last_exc)


def _build_with_client(token: str, client: Any) -> None:
    """经已连接 client 翻页拉取 + 落快照（无连接管理，调用方负责容灾/关闭）。"""
    frames: list[pd.DataFrame] = []
    targets = _RANK_EX_MARKETS[token]
    total_est = sum(_safe_count(client, m) for m in targets)
    done = 0
    for ex_market in targets:
        offset = 0
        while True:
            try:
                df = client.goods_quotes_list(ex_market, start=offset, count=_PAGE_SIZE)
            except Exception as exc:  # noqa: BLE001 — 单页失败记日志继续
                logger.warning("榜单拉取 %s/%s offset=%d 失败: %s", token, ex_market, offset, exc)
                break
            if df is None or len(df) == 0:
                break
            frames.append(df)
            offset += len(df)
            done += len(df)
            with _lock:
                _snapshots[token] = {
                    "built_at": 0,  # 0 = 未完成，rank_snapshot 视为过期继续 building
                    "payload": {},
                    "progress": f"{done}/{total_est}" if total_est else str(done),
                }
            if len(df) < _PAGE_SIZE:
                break
    payload = _to_payload(token, frames)
    with _lock:
        _snapshots[token] = {"built_at": time.time(), "payload": payload, "progress": ""}
    logger.info("港美股榜单构建完成 (%s): %d 只", token, payload["total"])


def _safe_count(client: Any, ex_market: int) -> int:
    try:
        return int(client.goods_count(ex_market) or 0)
    except Exception:  # noqa: BLE001
        return 0


def _to_payload(token: str, frames: list[pd.DataFrame]) -> dict[str, Any]:
    """原始报价帧 → 榜单 payload（排序 + 统计 + 行裁剪，Top30）。"""
    if not frames:
        return {
            "market": token,
            "label": market_label(token),
            "total": 0,
            "up": 0,
            "down": 0,
            "flat": 0,
            "gainers": [],
            "losers": [],
            "by_amount": [],
            "by_vol": [],
            "dist_counts": [],
            "dist_total": 0,
            "dist_gt5": 0,
            "dist_lt5": 0,
        }
    df = pd.concat(frames, ignore_index=True)
    # 同代码去重（翻页边界重复）：保留最后一次快照
    if "code" in df.columns:
        df = df.drop_duplicates(subset=["code"], keep="last")

    df = df.copy()
    for col in ("close", "pre_close", "amount", "vol"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close", "pre_close"])
    df = df[df["pre_close"] > 0]
    df["change_pct"] = (df["close"] / df["pre_close"] - 1) * 100

    up = int((df["change_pct"] > 0).sum())
    down = int((df["change_pct"] < 0).sum())
    flat = int(len(df) - up - down)

    # 全市场涨跌分布（服务端一次算好，前端直方图直接渲染，无需全量行下发）
    dist_counts = _dist_counts(df["change_pct"])
    dist_total = int(len(df))
    dist_gt5 = int((df["change_pct"] > 5).sum())
    dist_lt5 = int((df["change_pct"] < -5).sum())

    def _rows(sub: pd.DataFrame) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for rec in sub.to_dict(orient="records"):
            out.append(
                {
                    "market": token,
                    "code": str(rec.get("code", "")),
                    "name": str(rec.get("name", "")),
                    "close": _num(rec.get("close")),
                    "pre_close": _num(rec.get("pre_close")),
                    "change_pct": _num(rec.get("change_pct")),
                    "amount": _num(rec.get("amount")),
                    "vol": _num(rec.get("vol")),
                    "ex_market": int(rec.get("market") or 0),
                }
            )
        return out

    amount_col = "amount" if "amount" in df.columns else "vol"
    vol_col = "vol" if "vol" in df.columns else amount_col
    # 涨跌榜排除权证：美股权证（名称含"权证"）价格基数小、单日波动常达几十个点，
    # 不过滤会长期霸榜，把真正的股票挤出 Top30。成交额/成交量榜不过滤（看资金去向）。
    trade_df = df[~df["name"].astype(str).str.contains("权证", na=False)]
    if len(trade_df) == 0:
        trade_df = df
    return {
        "market": token,
        "label": market_label(token),
        "total": int(len(df)),
        "up": up,
        "down": down,
        "flat": flat,
        "gainers": _rows(trade_df.nlargest(_TOP_N, "change_pct")),
        "losers": _rows(trade_df.nsmallest(_TOP_N, "change_pct")),
        "by_amount": _rows(df.nlargest(_TOP_N, amount_col)),
        "by_vol": _rows(df.nlargest(_TOP_N, vol_col)),
        "dist_counts": dist_counts,
        "dist_total": dist_total,
        "dist_gt5": dist_gt5,
        "dist_lt5": dist_lt5,
    }


def _dist_counts(change_pct: Any) -> list[int]:
    """涨跌幅序列 → 22 桶分布（与前端 DashboardView.loadDist 同口径）。

    桶布局：[0]='≤-10'，[1..10]='-10'..'-1'，[11]='0'，
    [12..20]='+1'..'+9'，[21]='≥10'；公式 idx = 11 + floor(pct)，两端 clamp。
    非有限值跳过。
    """
    import math

    counts = [0] * _DIST_BUCKETS
    try:
        values = list(change_pct)
    except TypeError:
        return counts
    for v in values:
        try:
            pct = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(pct):
            continue
        if pct <= -10:
            idx = 0
        elif pct >= 10:
            idx = _DIST_BUCKETS - 1
        else:
            idx = 11 + math.floor(pct)
            idx = max(0, min(_DIST_BUCKETS - 1, idx))
        counts[idx] += 1
    return counts


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


__all__ = ["rank_snapshot"]
