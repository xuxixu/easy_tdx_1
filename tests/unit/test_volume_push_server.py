"""成交量 Top30 + 服务器增删改 + 推送服务（零网络、零真实服务器）。"""

from __future__ import annotations

import json

import pandas as pd
import pytest


def _row(code, name, close, pre, amount=100.0, vol=10.0):
    return {
        "market": 74,
        "code": code,
        "name": name,
        "close": close,
        "pre_close": pre,
        "amount": amount,
        "vol": vol,
    }


def test_overseas_payload_has_by_vol_top30():
    from easy_tdx.web import overseas_rank as rank_mod

    assert rank_mod._TOP_N == 30
    rows = [
        _row(f"C{i:02d}", f"股{i:02d}", 10 + i * 0.1, 10.0, amount=100.0 + i, vol=float(i))
        for i in range(35)
    ]
    payload = rank_mod._to_payload("US", [pd.DataFrame(rows)])
    assert len(payload["by_vol"]) == 30
    assert len(payload["by_amount"]) == 30
    assert len(payload["gainers"]) == 30
    # vol 最大者在首位
    assert payload["by_vol"][0]["code"] == "C34"


def test_overseas_payload_empty_has_by_vol():
    from easy_tdx.web import overseas_rank as rank_mod

    payload = rank_mod._to_payload("HK", [])
    assert payload["by_vol"] == []
    assert payload["by_amount"] == []
    assert payload["dist_counts"] == []
    assert payload["dist_total"] == 0


def test_overseas_payload_dist_counts():
    """22 桶分布与前端 loadDist 同口径（idx = 11 + floor(pct)，两端 clamp）。"""
    import pandas as pd

    from easy_tdx.web import overseas_rank as rank_mod

    df = pd.DataFrame(
        [
            _row("N10", "跌停", 89.0, 100.0),  # -11% → 桶 0
            _row("N5", "跌", 94.5, 100.0),  # -5.5% → 桶 5
            _row("Z", "平", 100.0, 100.0),  # 0% → 桶 11
            _row("P3", "涨", 103.2, 100.0),  # +3.2% → 桶 14
            _row("P10", "涨停", 112.0, 100.0),  # +12% → 桶 21
        ]
    )
    payload = rank_mod._to_payload("US", [df])
    counts = payload["dist_counts"]
    assert len(counts) == 22
    assert sum(counts) == 5
    assert counts[0] == 1 and counts[5] == 1 and counts[11] == 1
    assert counts[14] == 1 and counts[21] == 1
    assert payload["dist_total"] == 5
    assert payload["dist_gt5"] == 1 and payload["dist_lt5"] == 2


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    from easy_tdx import config as cfg

    monkeypatch.setattr(cfg, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "_CONFIG_FILE", tmp_path / "config.json")
    return tmp_path


def test_config_add_remove_host(isolated_config):
    from easy_tdx import config as cfg

    hosts = cfg.add_custom_host("9.9.9.9")
    assert "9.9.9.9" in hosts
    # 去重：重复新增不翻倍
    hosts2 = cfg.add_custom_host("9.9.9.9")
    assert hosts2.count("9.9.9.9") == 1
    # 非法地址拒绝
    with pytest.raises(ValueError):
        cfg.add_custom_host("   ")
    # 删除
    hosts3 = cfg.remove_custom_host("9.9.9.9")
    assert "9.9.9.9" not in hosts3
    # 删空拒绝
    cfg.set_known_hosts(["only.one"])
    with pytest.raises(ValueError):
        cfg.remove_custom_host("only.one")
    # 整体替换校验
    with pytest.raises(ValueError):
        cfg.set_known_hosts([])


def test_server_router_add_remove(isolated_config):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from easy_tdx.web.errors import register_exception_handlers
    from easy_tdx.web.routers import server as server_mod

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(server_mod.router, prefix="/api/v1")

    class _Dummy:
        _host = "1.1.1.1"

        async def reconnect_to(self, host):
            self._host = host

    app.state.tdx_client = _Dummy()
    with TestClient(app) as client:
        r = client.post("/api/v1/server/hosts", json={"host": "9.9.9.9"})
        assert r.status_code == 200, r.text
        assert any(h["host"] == "9.9.9.9" for h in r.json()["hosts"])
        # 非法 → 400（pydantic min_length 或业务校验）
        bad = client.post("/api/v1/server/hosts", json={"host": ""})
        assert bad.status_code in (400, 422)
        # 删除
        d = client.delete("/api/v1/server/hosts/9.9.9.9")
        assert d.status_code == 200
        assert not any(h["host"] == "9.9.9.9" for h in d.json()["hosts"])
        # 删不存在 → 404
        nf = client.delete("/api/v1/server/hosts/10.255.255.1")
        assert nf.status_code == 404


def test_push_config_and_send(monkeypatch, tmp_path):
    from easy_tdx.web import push as push_mod

    monkeypatch.setenv("EASY_TDX_CONFIG_DIR", str(tmp_path))
    # 空配置发送 → ok=False
    assert push_mod.send_all("t", "c")["ok"] is False
    # 保存 serverchan 通道，mock 掉网络层
    cfg = push_mod.PushConfig(
        channels=[push_mod.PushChannel(provider="serverchan", key="fake-key", enabled=True)]
    )
    push_mod.save_config(cfg)
    loaded = push_mod.load_config()
    assert loaded.channels[0].provider == "serverchan"
    assert json.loads(push_mod.config_path().read_text("utf-8"))["channels"][0]["key"] == "fake-key"

    calls = {}

    def _fake_post_form(url, fields):
        calls["url"] = url
        calls["fields"] = fields
        return "ok"

    monkeypatch.setattr(push_mod, "_post_form", _fake_post_form)
    res = push_mod.send_all("标题", "正文")
    assert res["ok"] is True
    assert "fake-key" in calls["url"]
    # 未知 provider → 400
    bad_ch = push_mod.PushChannel(provider="nope", key="x")
    assert push_mod.send_one(bad_ch, "t", "c")["ok"] is False


def test_push_format_signal():
    from easy_tdx.web.push import format_signal_message

    rows = [
        {
            "symbol": "SH:600519",
            "strategy": "ma_cross",
            "strategy_label": "均线",
            "latest_signal": "BUY",
            "signal_date": "2026-01-01",
            "last_close": 10.0,
        },
        {
            "symbol": "SZ:000001",
            "strategy": "ma_cross",
            "strategy_label": "",
            "latest_signal": "SELL",
            "signal_date": "2026-01-02",
            "last_close": 5.0,
        },
        {"symbol": "SH:600000", "error": "bad"},
    ]
    title, content = format_signal_message(rows, 5)
    assert "买入 1" in title and "卖出 1" in content or "卖出 1" in title
    assert "600519" in content


def test_push_router_endpoints(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from easy_tdx.web import push as push_mod
    from easy_tdx.web.errors import register_exception_handlers
    from easy_tdx.web.routers import push as push_router

    monkeypatch.setenv("EASY_TDX_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(push_mod, "_post_form", lambda url, fields: "ok")

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(push_router.router, prefix="/api/v1")
    with TestClient(app) as client:
        r = client.get("/api/v1/push/config")
        assert r.status_code == 200
        assert "providers" in r.json()
        # 保存通道
        s = client.put(
            "/api/v1/push/config",
            json={
                "channels": [
                    {"provider": "serverchan", "key": "k123", "endpoint": "", "enabled": True}
                ]
            },
        )
        assert s.status_code == 200, s.text
        # 未知通道 → 400
        bad = client.put(
            "/api/v1/push/config", json={"channels": [{"provider": "nope", "key": "x"}]}
        )
        assert bad.status_code == 400
        # 测试推送（mock 网络层，直接 ok）
        t = client.post("/api/v1/push/test")
        assert t.status_code == 200
        assert t.json()["ok"] is True
        # 信号推送
        sig = client.post(
            "/api/v1/push/send-signal",
            json={
                "rows": [
                    {
                        "symbol": "SH:600519",
                        "latest_signal": "BUY",
                        "strategy": "ma",
                        "signal_date": "d",
                        "last_close": 1.0,
                    }
                ],
                "window_bars": 5,
            },
        )
        assert sig.status_code == 200
        assert "买入" in sig.json()["title"]
