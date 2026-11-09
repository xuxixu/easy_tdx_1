"""美股雷达重建路由（/api/v1/us-radar/*）的契约测试。

用 TestClient + 临时快照文件，验证版本探测、状态、手动触发的返回形状与
降级行为；不触发真实重建（会抓 291 只日线）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from easy_tdx.web import create_app  # noqa: E402
from easy_tdx.web import radar_rebuilder as rr  # noqa: E402
from easy_tdx.web.radar_rebuilder import RadarRebuilder  # noqa: E402


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # lifespan 连真实 TDX 会拖到超时；mock 模式走合成客户端、秒起。
    monkeypatch.setenv("EASY_TDX_E2E_MOCK", "1")
    snap = tmp_path / "us-radar.json"
    snap.write_text(
        json.dumps({"meta": {"builtAt": "2026-11-09", "asOf": "2026-11-08 收盘", "delay": "日线"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rr, "snapshot_path", lambda: snap)
    app = create_app()
    # 禁用实际网络重建：状态接口仍要如实反映 enabled=False
    app.state.radar_rebuilder = RadarRebuilder(enabled=False)
    with TestClient(app) as c:
        yield c


def test_version_returns_snapshot_meta_and_rebuild_state(client: TestClient) -> None:
    r = client.get("/api/v1/us-radar/version")
    assert r.status_code == 200
    body = r.json()
    assert body["built_at"] == "2026-11-09"
    assert body["as_of"] == "2026-11-08 收盘"
    assert body["rebuild"]["enabled"] is False


def test_status_endpoint(client: TestClient) -> None:
    r = client.get("/api/v1/us-radar/status")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["builds"] == 0


def test_rebuild_rejected_when_disabled(client: TestClient) -> None:
    r = client.post("/api/v1/us-radar/rebuild")
    assert r.status_code == 409
    assert "未启用" in r.json()["detail"]


def test_version_degrades_when_snapshot_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """快照文件缺失时版本探测返回空串而非 500（前端据此沿用旧数据）。"""
    monkeypatch.setenv("EASY_TDX_E2E_MOCK", "1")
    monkeypatch.setattr(rr, "snapshot_path", lambda: tmp_path / "nope.json")
    app = create_app()
    app.state.radar_rebuilder = None
    with TestClient(app) as c:
        r = c.get("/api/v1/us-radar/version")
        assert r.status_code == 200
        assert r.json()["built_at"] == ""
        assert r.json()["rebuild"]["enabled"] is False
