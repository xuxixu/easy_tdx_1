"""py_mini_racer V8 并发预热守护测试。

崩溃是进程级的，测试里**不能**真的去触发它（会把 pytest 自己打挂）。
这里验证的是「预热契约」：幂等、未安装时优雅返回 False、预热后多线程
并发各建 MiniRacer 实例可正常工作（这正是线上 akshare 的用法）。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from easy_tdx._mini_racer_guard import warmup_mini_racer


def _mini_racer_available() -> bool:
    try:
        import py_mini_racer  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _mini_racer_available(), reason="py_mini_racer 未安装")
def test_warmup_is_idempotent() -> None:
    """多次调用只做一次初始化，返回值恒为 True。"""
    assert warmup_mini_racer() is True
    assert warmup_mini_racer() is True
    assert warmup_mini_racer() is True


@pytest.mark.skipif(not _mini_racer_available(), reason="py_mini_racer 未安装")
def test_warmup_makes_concurrent_context_creation_safe() -> None:
    """预热后 8 线程并发各建实例不再触发 V8 全局初始化崩溃。

    这是回归核心：未预热时本机（Python 3.15 + mini-racer 0.14.1）必现
    ``FATAL:partition_address_space.cc`` 进程级崩溃。
    """
    assert warmup_mini_racer() is True

    def work(i: int) -> int:
        import py_mini_racer

        ctx = py_mini_racer.MiniRacer()
        return int(ctx.eval(f"1+{i}"))

    with ThreadPoolExecutor(max_workers=8) as ex:
        assert list(ex.map(work, range(8))) == list(range(1, 9))


def test_warmup_missing_dependency_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """mini-racer 未安装时返回 False（调用方按可选依赖缺失处理，不抛错）。"""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "py_mini_racer":
            raise ImportError("simulated missing")
        return real_import(name, *args, **kwargs)

    # 重置模块状态，确保真的走到 import 分支
    import easy_tdx._mini_racer_guard as guard

    monkeypatch.setattr(guard, "_warmed", False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert guard.warmup_mini_racer() is False


@pytest.mark.skipif(not _mini_racer_available(), reason="py_mini_racer 未安装")
def test_warmup_native_dll_failure_returns_false_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """native DLL 加载失败（PyInstaller onefile 漏收集）时必须优雅降级。

    回归点：create_app 曾因 warmup 里 MiniRacer() 抛 LibNotFoundError 而
    整个启动失败。预热是尽力而为，绝不阻断服务启动。
    """
    import py_mini_racer

    import easy_tdx._mini_racer_guard as guard

    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("LibNotFoundError: mini_racer.dll missing")

    monkeypatch.setattr(guard, "_warmed", False)
    monkeypatch.setattr(py_mini_racer, "MiniRacer", boom)
    assert guard.warmup_mini_racer() is False  # 不抛异常
    assert guard._warmed is False  # 保持未预热，后续可重试
