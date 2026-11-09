"""美股观测雷达快照的定时重建调度器（Web 运行态专用，冷路径）。

为什么需要它
------------
``us-radar.json`` 原本是 ``scripts/build_us_radar.py`` 手跑一次的静态快照，
放久了会过期（曾出现 10-16 收盘、10-18 构建的快照挂了一个月）。本模块把它
变成 Web 服务生命周期内的**低频后台任务**：每日收盘后重跑一次
``radar.build.build_snapshot()``，原子替换产物，前端通过版本探测感知更新。

硬约束（决定了实现形态）
----------------------
1. ``build_snapshot()`` 是**同步重函数**：291 只标的 × 新浪日线，内部再开
   ``ThreadPoolExecutor`` 并发，冷启 1~2 分钟。直接放进 asyncio task 会把
   事件循环卡死、整个服务无响应 → 必须 ``asyncio.to_thread`` 丢到线程里跑，
   并用 ``_lock`` 防重入（定时触发与手动触发可能撞在一起）。
2. 产物写仓库里的 ``web-ui/public/data/us-radar.json``。**PyInstaller onefile
   EXE 态该文件是只读打包资源、且源码目录不存在** → EXE 态自动禁用重建，
   保留静态快照即可（见 :func:`rebuild_enabled`）。
3. 新浪源是**收盘后日线**，日频重建才合理；盘中重算拿不到新数据。默认间隔
   24h，可用 ``EASY_TDX_RADAR_REBUILD_INTERVAL`` 覆盖（秒），``<=0`` 关闭。
4. E2E mock 模式下不打外部源，自动禁用（避免测试期间抓真实网络）。

写入策略：先写同目录临时文件再 ``os.replace`` 原子替换——避免前端读到
写了一半的 JSON。构建失败保留旧快照，只记状态与日志，绝不中断服务。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["RadarRebuilder", "rebuild_enabled", "snapshot_path"]

_ENV_INTERVAL = "EASY_TDX_RADAR_REBUILD_INTERVAL"
_ENV_DISABLE = "EASY_TDX_RADAR_REBUILD"
_DEFAULT_INTERVAL = 24 * 3600.0


def snapshot_path() -> Path:
    """雷达快照文件路径（开发态 = 仓库内源码文件）。"""
    from easy_tdx.radar.universe import default_snapshot_path

    return default_snapshot_path()


def rebuild_enabled() -> bool:
    """当前进程是否允许定时重建。

    EXE（``sys.frozen``）/ 显式关闭 / 间隔<=0 均返回 False。缺 akshare 不在这里
    硬判（留给实际构建时报明确错误并降级），避免 import 期就耦合可选依赖。
    """
    if getattr(sys, "frozen", False):
        return False
    if os.environ.get(_ENV_DISABLE, "").strip().lower() in {"0", "false", "off"}:
        return False
    return _interval() > 0


def _interval() -> float:
    try:
        return float(os.environ.get(_ENV_INTERVAL, _DEFAULT_INTERVAL))
    except ValueError:
        return _DEFAULT_INTERVAL


def _is_mock() -> bool:
    return os.environ.get("EASY_TDX_E2E_MOCK", "").strip() == "1"


@dataclass
class RebuildState:
    """最近一次重建的状态（供路由 /api/v1/us-radar/status 暴露给前端）。"""

    enabled: bool = False
    running: bool = False
    last_attempt: float | None = None
    last_success: float | None = None
    last_error: str = ""
    builds: int = 0
    failures: int = 0
    built_at: str = ""
    as_of: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self.running,
            "last_attempt": self.last_attempt,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "builds": self.builds,
            "failures": self.failures,
            "built_at": self.built_at,
            "as_of": self.as_of,
            "interval_sec": _interval(),
        }


class RadarRebuilder:
    """定时 + 手动触发的快照重建器。start/stop 由 app.py lifespan 管理。"""

    def __init__(self, interval: float | None = None, *, enabled: bool | None = None) -> None:
        self._interval = interval if interval is not None else _interval()
        self._enabled = enabled if enabled is not None else (rebuild_enabled() and not _is_mock())
        self._task: asyncio.Task[None] | None = None
        # 线程锁：build_snapshot 在 to_thread 里跑，防「定时 + 手动」并发重入。
        self._lock = threading.Lock()
        self.state = RebuildState(enabled=self._enabled, built_at=_read_built_at())
        self._state_lock = threading.Lock()

    def start(self) -> None:
        if not self._enabled:
            logger.info("雷达定时重建未启用（EXE/显式关闭/mock 态），沿用静态快照")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
            logger.info("RadarRebuilder 启动（间隔 %.0fs）", self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            return self.state.as_dict()

    async def trigger(self) -> dict[str, Any]:
        """手动触发一次（非阻塞：构建丢线程池，立即返回当前状态）。

        返回 ``{started: bool, reason?: str, state: {...}}``。重复触发（已在跑）
        直接拒绝，不排队——避免连点堆出一串 1-2 分钟的重任务。
        """
        if not self._enabled:
            return {"started": False, "reason": "定时重建未启用", "state": self.status()}
        if self._lock.locked():
            return {"started": False, "reason": "已有重建在进行中", "state": self.status()}
        # 用 create_task 包装 to_thread，调用方立即拿到响应
        asyncio.create_task(self._build_once())
        return {"started": True, "state": self.status()}

    async def _run(self) -> None:
        while True:
            try:
                # 启动时先补一次「过期快照」：asOf 是收盘日线日期，若距今超过
                # 一个自然日，说明服务重启后手里的快照已过时，立即重建，而不
                # 是傻等一整个间隔。EASY_TDX_RADAR_REBUILD_AT_START=0 可关闭
                # （运维/测试只想沿用旧快照、不想启动就抓 291 只日线时）。
                if (
                    os.environ.get("EASY_TDX_RADAR_REBUILD_AT_START", "1").strip() != "0"
                    and self._snapshot_stale()
                ):
                    logger.info("雷达快照已过期，启动时立即重建")
                    await self._build_once()
                await asyncio.sleep(self._interval)
                await self._build_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — 调度器永不因单次失败退出
                logger.warning("雷达重建调度异常", exc_info=True)

    def _snapshot_stale(self) -> bool:
        """现有快照的 asOf 日期距今是否超过一个自然日。

        解析失败（旧格式 / 文件缺失）时返回 False——交给定时循环按间隔处理，
        不因为一个读不懂的日期就在启动瞬间触发 1-2 分钟的重构建。
        """
        from datetime import date, datetime

        meta = _read_meta()
        raw = str(meta.get("asOf", ""))
        head = raw[:10]
        try:
            d = datetime.strptime(head, "%Y-%m-%d").date()
        except ValueError:
            return False
        return (date.today() - d).days > 1

    async def _build_once(self) -> None:
        """跑一次完整重建（同步重函数放线程池）。"""
        with self._state_lock:
            self.state.running = True
            self.state.last_attempt = time.time()
        try:
            await asyncio.to_thread(self._build_sync)
        finally:
            with self._state_lock:
                self.state.running = False

    def _build_sync(self) -> None:
        """线程内：构建 → 原子写 → 更新状态。任何异常都降级为「保留旧快照」。"""
        if not self._lock.acquire(blocking=False):
            logger.info("雷达重建已有实例在跑，跳过本次触发")
            return
        try:
            from easy_tdx.radar.build import build_snapshot

            snap, _report = build_snapshot()
            _atomic_write(snap)
            with self._state_lock:
                self.state.builds += 1
                self.state.last_success = time.time()
                self.state.last_error = ""
                self.state.built_at = str(snap.get("meta", {}).get("builtAt", ""))
                self.state.as_of = str(snap.get("meta", {}).get("asOf", ""))
            logger.info("雷达快照已重建（第 %d 次）", self.state.builds)
        except Exception as exc:  # noqa: BLE001 — 构建失败不中断服务、保留旧快照
            with self._state_lock:
                self.state.failures += 1
                self.state.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("雷达快照重建失败，保留旧快照：%s", self.state.last_error, exc_info=True)
        finally:
            self._lock.release()


def _atomic_write(snap: dict[str, Any]) -> None:
    """临时文件 + os.replace 原子替换，避免前端读到半截 JSON。"""
    dest = snapshot_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(snap, ensure_ascii=False, indent=2, allow_nan=False)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, dest)


def _read_meta() -> dict[str, Any]:
    """读现有快照的 meta（文件缺失/损坏时返回空字典，不影响启动）。"""
    try:
        data = json.loads(snapshot_path().read_text(encoding="utf-8"))
        return dict(data.get("meta", {}))
    except Exception:  # noqa: BLE001
        return {}


def _read_built_at() -> str:
    """启动时读一次现有快照的 builtAt，供状态接口在首次重建前也能显示。"""
    return str(_read_meta().get("builtAt", ""))
