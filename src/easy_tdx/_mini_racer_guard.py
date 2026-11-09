"""py_mini_racer（V8）并发安全预热。

akshare 的多个模块（``index_stock_us_sina`` / ``fund_em`` …）在函数内部直接
``py_mini_racer.MiniRacer()`` 新建 V8 实例。该内嵌 V8 的 *全局地址空间池*
只在进程首次初始化时配置一次；若**多个线程同时首次创建实例**，会命中
``FATAL:partition_address_space.cc(243) Check failed:
!IsConfigurablePoolInitialized()`` ——这是进程级硬崩溃，try/except 拦不住，
会连带把整个 easy-tdx 服务/重建脚本打挂。

实机复现（Python 3.15 + mini-racer 0.14.1）：8 线程并发各建一个
``MiniRacer()`` 必崩；而**只要进程启动时在主线程先构造并 eval 一次**
（完成全局初始化），之后任意线程并发新建实例都不再崩。原因是 V8 的平台级
初始化已由主线程串行做完，后续实例只是复用同一份已配置好的全局池。

因此这里的修复不是 monkeypatch、不是全局单例锁（共享一个 Context 会让不同
akshare 模块 eval 的脚本互相污染），而是**一次幂等的预热**：在任何并发线程
起来之前，先在主线程完成 V8 全局初始化。改不到也不改第三方行为。

用法：在 ``import akshare`` 之前调用 :func:`warmup_mini_racer`。
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_warmed = False


def warmup_mini_racer() -> bool:
    """在主线程完成 py_mini_racer 的 V8 全局初始化（幂等、线程安全）。

    Returns:
        ``True`` 表示已完成预热（本次或之前）；``False`` 表示无法预热
        （mini-racer 未安装，或其 native DLL 加载失败）。**绝不抛异常**——
        预热是尽力而为的优化，失败只回到「不预热」的旧行为，不能阻断
        create_app / 服务启动（PyInstaller onefile 若未收集 DLL 就会走到
        这条路径）。

    注意：本函数必须在**主线程、且在任何工作线程/线程池创建之前**调用才有
    意义。若已经有线程在跑 V8，预热也救不了那一刻，但能让之后的创建安全。
    """
    global _warmed
    if _warmed:
        return True
    with _lock:
        if _warmed:
            return True
        try:
            import py_mini_racer
        except ImportError:  # pragma: no cover - 可选依赖缺失
            logger.debug("py_mini_racer 未安装，跳过 V8 预热")
            return False
        # 构造 + eval 一次即完成 V8 的进程级初始化；实例随即释放，不缓存
        # （缓存 Context 反而会让 akshare 各模块的 eval 脚本互相污染）。
        # native DLL 缺失/损坏时 MiniRacer() 会抛 LibNotFoundError 等，必须
        # 就地吞掉：服务照常启动，只是回到未预热状态。
        try:
            ctx = py_mini_racer.MiniRacer()
            ctx.eval("1")
            del ctx
        except Exception as exc:  # noqa: BLE001 — native 加载失败属可恢复降级
            logger.warning("py_mini_racer V8 预热失败（不影响启动）：%s", exc)
            return False
        _warmed = True
        logger.debug("py_mini_racer V8 全局初始化完成（并发创建已安全）")
        return True
