"""美股观测雷达快照：状态 / 手动重建 / 版本探测。

前端日常仍直接 fetch 静态 ``/data/us-radar.json``（由 StaticFiles 托管），
本路由只补三件「静态文件做不到」的事：

- ``GET /us-radar/version``：轻量返回现有快照的 ``builtAt / asOf / rebuild``，
  前端轮询它判断快照是否已更新，避免每次都下载 465KB 全文。
- ``GET /us-radar/status``：定时重建器的运行状态（是否启用、上次成败）。
- ``POST /us-radar/rebuild``：手动触发一次重建（非阻塞，立即返回）。

定时重建器实例挂在 ``app.state.radar_rebuilder``（见 app.py lifespan）；
EXE / mock / 显式关闭时该实例为 ``None`` 或 enabled=False，接口如实返回，
不伪装成「实时」。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request

from easy_tdx.web import radar_rebuilder as rr

if TYPE_CHECKING:
    from easy_tdx.web.radar_rebuilder import RadarRebuilder

router = APIRouter(tags=["us-radar"])


def _rebuilder(request: Request) -> RadarRebuilder | None:
    return getattr(request.app.state, "radar_rebuilder", None)


def _read_meta() -> dict[str, Any]:
    """读现有快照的 meta（builtAt/asOf）。文件缺失时返回空字典而非 500。"""
    try:
        data = json.loads(rr.snapshot_path().read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        return {
            "built_at": str(meta.get("builtAt", "")),
            "as_of": str(meta.get("asOf", "")),
            "delay": str(meta.get("delay", "")),
            "source": str(meta.get("source", "")),
        }
    except Exception:  # noqa: BLE001 — 快照缺失/损坏时降级为空
        return {"built_at": "", "as_of": "", "delay": "", "source": ""}


@router.get("/us-radar/version")
async def us_radar_version(request: Request) -> dict[str, Any]:
    """轻量版本探测：前端轮询这个判断是否要重拉整份快照。"""
    meta = _read_meta()
    rb = _rebuilder(request)
    meta["rebuild"] = rb.status() if rb is not None else {"enabled": False}
    return meta


@router.get("/us-radar/status")
async def us_radar_status(request: Request) -> dict[str, Any]:
    """定时重建器状态；未启用时 enabled=False，前端据此标注「静态快照」。"""
    rb = _rebuilder(request)
    if rb is None:
        return {"enabled": False, "running": False, "builds": 0, "failures": 0}
    return rb.status()


@router.post("/us-radar/rebuild")
async def us_radar_rebuild(request: Request) -> dict[str, Any]:
    """手动触发一次重建。非阻塞：构建在后台线程池跑，立即返回。

    未启用 / 已在跑时返回 409 与明确原因，不排队堆积重任务。
    """
    rb = _rebuilder(request)
    if rb is None:
        raise HTTPException(status_code=409, detail="定时重建未启用（EXE/mock/显式关闭）")
    result = await rb.trigger()
    if not result.get("started"):
        raise HTTPException(status_code=409, detail=str(result.get("reason", "无法触发")))
    return result
