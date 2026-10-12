"""自定义策略类型 + 任务删除（零网络、零真实服务器）。"""

from __future__ import annotations

import time

import pytest


@pytest.fixture
def custom_env(tmp_path, monkeypatch):
    """独立配置目录 + 全新 store 单例；用例结束清理注册表中的自定义条目。"""
    from easy_tdx.backtest.strategies import get_registry
    from easy_tdx.web import custom_strategy_store as store_mod

    monkeypatch.setenv("EASY_TDX_CONFIG_DIR", str(tmp_path / "cfg"))
    store_mod._store = None
    before = set(get_registry().names())
    yield store_mod
    for name in set(get_registry().names()) - before:
        try:
            get_registry().unregister(name)
        except KeyError:
            pass
    store_mod._store = None


def test_custom_register_build_and_unregister(custom_env):
    from easy_tdx.backtest.strategies import get_registry
    from easy_tdx.web.custom_strategies import register_custom_type, unregister_custom_type
    from easy_tdx.web.custom_strategy_store import CustomStrategyType, get_custom_strategy_store

    rec = CustomStrategyType(
        id="ab12cd34",
        name="custom_ab12cd34",
        label="短线双均线",
        base="ma_cross",
        description="测试",
        default_params={"fast": 10},
    )
    get_custom_strategy_store().add(rec)
    entry = register_custom_type(rec)
    assert entry.custom is True
    assert "custom_ab12cd34" in get_registry().names()
    # 默认参数生效：fast=10，slow 沿基准默认
    inst = get_registry().get("custom_ab12cd34").build({})
    assert inst.p["fast"] == 10
    assert inst.p["slow"] == get_registry().get("ma_cross").build({}).p["slow"]
    # to_schema 带 custom 标记与新默认值
    schema = entry.to_schema()
    assert schema["custom"] is True
    fast_schema = next(p for p in schema["params"] if p["name"] == "fast")
    assert fast_schema["default"] == 10
    # 注销后恢复未知
    unregister_custom_type("custom_ab12cd34")
    with pytest.raises(KeyError):
        get_registry().get("custom_ab12cd34")


def test_custom_rejects_bad_definitions(custom_env):
    from easy_tdx.web.custom_strategies import register_custom_type
    from easy_tdx.web.custom_strategy_store import CustomStrategyType

    # 未知参数
    with pytest.raises(ValueError, match="未知参数"):
        register_custom_type(
            CustomStrategyType(
                id="bad00001",
                name="custom_bad00001",
                label="坏",
                base="ma_cross",
                default_params={"nope": 1},
            )
        )
    # 倒挂约束（fast >= slow）
    with pytest.raises(ValueError, match="必须小于"):
        register_custom_type(
            CustomStrategyType(
                id="bad00002",
                name="custom_bad00002",
                label="坏2",
                base="ma_cross",
                default_params={"fast": 60, "slow": 10},
            )
        )
    # 基于自定义类型
    with pytest.raises(ValueError, match="只能基于内置"):
        register_custom_type(
            CustomStrategyType(
                id="bad00003", name="custom_bad00003", label="坏3", base="custom_zzzzzzzz"
            )
        )
    # 基准不存在
    with pytest.raises(ValueError, match="不存在"):
        register_custom_type(
            CustomStrategyType(id="bad00004", name="custom_bad00004", label="坏4", base="no_such")
        )
    # 超大网格
    with pytest.raises(ValueError, match="超过上限"):
        register_custom_type(
            CustomStrategyType(
                id="bad00005",
                name="custom_bad00005",
                label="坏5",
                base="ma_cross",
                preset_grid={"fast": list(range(50)), "slow": list(range(50))},
            )
        )


def test_unregister_refuses_builtin():
    from easy_tdx.web.custom_strategies import unregister_custom_type

    with pytest.raises(ValueError, match="内置"):
        unregister_custom_type("ma_cross")


def test_load_custom_types_idempotent(custom_env):
    from easy_tdx.backtest.strategies import get_registry
    from easy_tdx.web.custom_strategies import load_custom_types
    from easy_tdx.web.custom_strategy_store import CustomStrategyType, get_custom_strategy_store

    get_custom_strategy_store().add(
        CustomStrategyType(id="cd34ef56", name="custom_cd34ef56", label="幂等", base="macd")
    )
    assert load_custom_types() == 1
    assert load_custom_types() == 1  # 重复加载不抛错不翻倍
    assert get_registry().get("custom_cd34ef56").custom is True


def test_strategy_types_router_crud(custom_env):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from easy_tdx.web.errors import register_exception_handlers
    from easy_tdx.web.routers import strategy_types as st_mod

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(st_mod.router, prefix="/api/v1")
    with TestClient(app) as client:
        # 新增
        r = client.post(
            "/api/v1/strategy-types",
            json={
                "label": "短线双均线",
                "base": "ma_cross",
                "description": "d",
                "default_params": {"fast": 10},
                "preset_grid": {},
            },
        )
        assert r.status_code == 200, r.text
        name = r.json()["type"]["name"]
        assert name.startswith("custom_")
        assert r.json()["schema"]["custom"] is True
        # 内置不可删
        bad = client.delete("/api/v1/strategy-types/ma_cross")
        assert bad.status_code == 400
        # 编辑（换基准）
        u = client.put(
            f"/api/v1/strategy-types/{name}",
            json={
                "label": "短线EMA",
                "base": "ema_cross",
                "description": "",
                "default_params": {},
                "preset_grid": {},
            },
        )
        assert u.status_code == 200, u.text
        # 非法编辑（未知参数）→ 400 且旧定义保留
        bad2 = client.put(
            f"/api/v1/strategy-types/{name}",
            json={
                "label": "坏",
                "base": "ema_cross",
                "description": "",
                "default_params": {"nope": 1},
                "preset_grid": {},
            },
        )
        assert bad2.status_code == 400
        # 删除
        d = client.delete(f"/api/v1/strategy-types/{name}")
        assert d.status_code == 200
        assert d.json()["in_use"] == 0
        # 再删 → 400
        assert client.delete(f"/api/v1/strategy-types/{name}").status_code == 400


def test_runner_delete_terminal_and_running():
    from easy_tdx.web.task_runner import BacktestTaskRunner

    runner = BacktestTaskRunner(max_workers=2)

    # done 任务可删
    tid = runner.submit(lambda: {"ok": True}, description="t1")
    for _ in range(100):
        if runner.status(tid) == "done":
            break
        time.sleep(0.05)
    assert runner.status(tid) == "done"
    runner.delete(tid)
    with pytest.raises(KeyError):
        runner.get(tid)
    # 未知任务
    with pytest.raises(KeyError):
        runner.delete("nope")
    runner.shutdown(wait=True)


def test_task_delete_endpoint():
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from easy_tdx.web.errors import register_exception_handlers
    from easy_tdx.web.routers import backtest as bt_mod
    from easy_tdx.web.task_runner import get_runner

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(bt_mod.router, prefix="/api/v1")

    tid = get_runner().submit(lambda: {"ok": True}, description="del-me")
    for _ in range(100):
        if get_runner().status(tid) == "done":
            break
        time.sleep(0.05)
    with TestClient(app) as client:
        r = client.delete(f"/api/v1/backtest/tasks/{tid}")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        # 列表里不再出现
        ids = [t["task_id"] for t in client.get("/api/v1/backtest/tasks").json()["tasks"]]
        assert tid not in ids
        # 未知 → 400
        assert client.delete("/api/v1/backtest/tasks/nope").status_code == 400
