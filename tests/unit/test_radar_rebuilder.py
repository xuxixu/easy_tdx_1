"""RadarRebuilder 定时重建调度器的守护测试。

不真跑 build_snapshot（291 只 × 新浪日线、1-2 分钟）；用 monkeypatch 把
构建换成替身，验证：启用判定、防重入、原子写、失败保留旧快照、状态更新、
以及路由的接口契约。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from easy_tdx.web import radar_rebuilder as rr


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """隔离环境：快照路径指到临时目录，关掉真实网络构建。"""
    snap = tmp_path / "us-radar.json"
    snap.write_text(
        json.dumps({"meta": {"builtAt": "2026-01-01", "asOf": "2025-12-31 收盘"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rr, "snapshot_path", lambda: snap)
    return snap


def test_rebuild_enabled_false_in_frozen_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    """EXE 态（sys.frozen）自动禁用：只读打包资源无法回写。"""
    monkeypatch.setattr(rr.sys, "frozen", True, raising=False)
    monkeypatch.delenv(rr._ENV_DISABLE, raising=False)
    assert rr.rebuild_enabled() is False
    monkeypatch.delattr(rr.sys, "frozen", raising=False)


def test_rebuild_enabled_false_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(rr._ENV_DISABLE, "0")
    assert rr.rebuild_enabled() is False


def test_rebuild_enabled_false_when_interval_nonpositive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(rr._ENV_INTERVAL, "0")
    assert rr.rebuild_enabled() is False


def test_rebuild_enabled_true_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(rr._ENV_DISABLE, raising=False)
    monkeypatch.delenv(rr._ENV_INTERVAL, raising=False)
    monkeypatch.delattr(rr.sys, "frozen", raising=False)
    assert rr.rebuild_enabled() is True


def test_atomic_write_replaces_snapshot(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """原子写：写完后旧文件被完整替换，且不残留 .tmp。"""
    import easy_tdx.radar.build as build

    fake_snap = {"meta": {"builtAt": "2026-11-09", "asOf": "2026-11-08 收盘"}, "regime": {}}
    monkeypatch.setattr(build, "build_snapshot", lambda: (fake_snap, object()))

    rb = rr.RadarRebuilder(enabled=True)
    asyncio.run(rb._build_once())

    data = json.loads(env.read_text(encoding="utf-8"))
    assert data["meta"]["builtAt"] == "2026-11-09"
    assert rb.status()["builds"] == 1
    assert rb.status()["last_error"] == ""
    assert rb.status()["built_at"] == "2026-11-09"
    assert not env.with_suffix(".json.tmp").exists()


def test_build_failure_keeps_old_snapshot(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """构建失败保留旧文件、状态记错误，绝不写出半截 JSON。"""
    import easy_tdx.radar.build as build

    def boom():
        raise RuntimeError("新浪源不可达")

    monkeypatch.setattr(build, "build_snapshot", boom)

    rb = rr.RadarRebuilder(enabled=True)
    asyncio.run(rb._build_once())

    data = json.loads(env.read_text(encoding="utf-8"))
    assert data["meta"]["builtAt"] == "2026-01-01"  # 旧快照完整保留
    assert rb.status()["builds"] == 0
    assert rb.status()["failures"] == 1
    assert "新浪源不可达" in rb.status()["last_error"]
    assert not env.with_suffix(".json.tmp").exists()


def test_trigger_rejects_when_disabled() -> None:
    rb = rr.RadarRebuilder(enabled=False)
    result = asyncio.run(rb.trigger())
    assert result["started"] is False
    assert "未启用" in str(result.get("reason"))


def test_trigger_rejects_concurrent_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    """正在构建时重复触发直接拒绝，不排队堆积重任务。"""
    rb = rr.RadarRebuilder(enabled=True)
    # 手工占住锁，模拟一次正在进行的构建
    assert rb._lock.acquire(blocking=False)
    try:
        result = asyncio.run(rb.trigger())
        assert result["started"] is False
        assert "进行中" in str(result.get("reason"))
    finally:
        rb._lock.release()


def test_snapshot_stale_when_old(env: Path) -> None:
    """asOf 超过一天 → 启动时应立即补一次重建。"""
    rb = rr.RadarRebuilder(enabled=True)
    assert rb._snapshot_stale() is True  # 2025-12-31 相对今天是旧的


def test_snapshot_fresh_today(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    env.write_text(
        json.dumps({"meta": {"asOf": f"{date.today().isoformat()} 美股收盘"}}),
        encoding="utf-8",
    )
    rb = rr.RadarRebuilder(enabled=True)
    assert rb._snapshot_stale() is False


def test_snapshot_stale_unknown_date_returns_false(env: Path) -> None:
    """asOf 读不懂时不盲目触发重建，交给定时循环。"""
    env.write_text(json.dumps({"meta": {"asOf": "未知"}}), encoding="utf-8")
    rb = rr.RadarRebuilder(enabled=True)
    assert rb._snapshot_stale() is False


def test_start_stop_lifecycle() -> None:
    """start 起 task、stop 取消；禁用时不创建任务（真实 lifespan 有运行中的 loop）。"""

    async def scenario() -> None:
        disabled = rr.RadarRebuilder(enabled=False)
        disabled.start()
        assert disabled._task is None

        enabled = rr.RadarRebuilder(enabled=True, interval=3600)
        enabled.start()
        assert enabled._task is not None
        assert not enabled._task.done()
        await enabled.stop()
        assert enabled._task is None

    asyncio.run(scenario())
