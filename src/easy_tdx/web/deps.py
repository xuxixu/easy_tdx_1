"""Dependency injection for Web API routers."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from easy_tdx.client import AsyncTdxClient


def get_client(request: Request) -> AsyncTdxClient:
    """从 app.state 获取共享的 AsyncTdxClient 实例。"""
    client: AsyncTdxClient = request.app.state.tdx_client
    return client


def get_mac_client(request: Request) -> Any:
    """从 app.state 获取共享的 AsyncMacClient 实例。"""
    from easy_tdx.exceptions import TdxConnectionError

    client: Any | None = request.app.state.mac_client
    if client is None:
        raise TdxConnectionError("MAC 客户端未连接")
    return client


def get_mac_client_optional(request: Request) -> Any | None:
    """从 app.state 获取 AsyncMacClient 实例，未连接时返回 None（不抛异常）。

    供需要"MAC 不可用时自动回退标准 TdxClient"的端点使用（如 ``/bars``）。
    其他强制依赖 MAC 的端点（``/mac/*``）仍用 :func:`get_mac_client`。
    """
    return request.app.state.mac_client


def get_ex_client(request: Request) -> Any:
    """从 app.state 获取共享的 AsyncExTdxClient 实例（可选）。"""
    client: Any | None = request.app.state.ex_client
    if client is None:
        from easy_tdx.exceptions import TdxConnectionError

        raise TdxConnectionError("扩展市场客户端未启用")
    return client


def get_mac_ex_client(request: Request) -> Any:
    """从 app.state 获取共享的 AsyncMacExClient 实例（美股 / 期货协议栈）。

    美股（``ExMarket.US_STOCK=74``）只能走这条 MAC 协议栈（0x122F），
    标准 ``TdxClient`` 与老 ``ExTdxClient`` 都取不到美股数据。
    """
    client: Any | None = request.app.state.mac_ex_client
    if client is None:
        from easy_tdx.exceptions import TdxConnectionError

        raise TdxConnectionError("美股客户端未连接（MAC 扩展市场协议栈不可用）")
    return client


def get_mac_ex_client_optional(request: Request) -> Any | None:
    """取 AsyncMacExClient，未连接时返回 None（不抛异常）。

    供需要"美股不可用时降级"的端点使用（如 ``/bars`` 的市场分流）。
    用 getattr 而不是直接属性访问——只挂单路由的最小 app（单测）
    根本没初始化这个 state，直接访问会 AttributeError 把 A 股请求也炸掉。
    """
    return getattr(request.app.state, "mac_ex_client", None)


def get_gateway(request: Request) -> Any | None:
    """取统一取数网关（按市场自动分流到对应协议栈）。

    刻意返回 ``None`` 而不抛异常：网关只服务港股/美股分支，A 股走
    ``get_mac_client`` / ``get_client``。若这里抛错，会把"A 股可用但
    扩展栈没初始化"整个场景打成 503——包括只挂了单一路由的最小 app
    （测试里 ``_bars_app`` 就是这种）。真正需要网关的端点自己检查
    ``None`` 并给出明确报错。
    """
    return getattr(request.app.state, "gateway", None)
