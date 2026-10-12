"""推送服务路由：通道配置（填 key 即用）+ 测试 + 信号推送。

WebUI「推送设置」页表单 ⇆ ``~/.easy_tdx/push.json`` 同一份文件。
key 脱敏回显，空串/脱敏串回传 = 不修改已存 key（与 LLM 配置同语义）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from easy_tdx.web import push as push_mod

router = APIRouter(tags=["push"])


class PushChannelUpdate(BaseModel):
    provider: str = Field(..., description="serverchan/wxpush/baidu/mob/webhook")
    key: str = Field("", description="密钥（留空/传回脱敏串 = 不修改；CLEAR = 清除）")
    endpoint: str = Field("", description="网关地址（wxpush/baidu/mob/webhook 用）")
    enabled: bool = Field(True, description="是否启用")


class PushConfigUpdate(BaseModel):
    channels: list[PushChannelUpdate] = Field(default_factory=list, max_length=20)


class PushSendRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field("", max_length=10_000)


class PushSignalRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(..., min_length=1, max_length=2000)
    window_bars: int = Field(5, ge=1, le=60)


@router.get("/push/config")
async def get_push_config() -> dict[str, Any]:
    """当前推送配置（key 脱敏）+ 支持的通道表。"""
    cfg = push_mod.load_config()
    return {
        "config": cfg.to_dict(mask_api_key=True),
        "providers": [{"id": k, "label": v} for k, v in push_mod.PROVIDERS.items()],
        "configured": any(c.enabled and c.key for c in cfg.channels),
        "config_path": str(push_mod.config_path()),
    }


@router.put("/push/config")
async def update_push_config(req: PushConfigUpdate) -> dict[str, Any]:
    """保存推送通道配置（与手工编辑 push.json 等效）。"""
    current = {c.provider: c for c in push_mod.load_config().channels}
    channels: list[push_mod.PushChannel] = []
    for item in req.channels:
        provider = item.provider.strip().lower()
        if provider not in push_mod.PROVIDERS:
            valid = ", ".join(push_mod.PROVIDERS)
            raise ValueError(f"未知推送通道 '{item.provider}'，可选: {valid}")
        old_key = current[provider].key if provider in current else ""
        channels.append(
            push_mod.PushChannel(
                provider=provider,
                key=push_mod.merge_key(item.key, old_key),
                endpoint=item.endpoint.strip(),
                enabled=item.enabled,
            )
        )
    # 同 provider 去重保活最后一个
    dedup: dict[str, push_mod.PushChannel] = {}
    for c in channels:
        dedup[c.provider] = c
    cfg = push_mod.PushConfig(channels=list(dedup.values()))
    path = push_mod.save_config(cfg)
    return {"ok": True, "config_path": str(path), "config": cfg.to_dict(mask_api_key=True)}


@router.post("/push/test")
async def test_push() -> dict[str, Any]:
    """发一条测试消息，验证已保存通道是否可达（阻塞 ≤10s×通道数，线程池跑）。"""
    result = await asyncio.to_thread(
        push_mod.send_all, "easy-tdx 推送测试", "通道配置成功，这是一条测试消息。"
    )
    return result


@router.post("/push/send")
async def send_push(req: PushSendRequest) -> dict[str, Any]:
    """经全部启用通道发送自定义标题/正文。"""
    result = await asyncio.to_thread(push_mod.send_all, req.title, req.content)
    return result


@router.post("/push/send-signal")
async def send_signal(req: PushSignalRequest) -> dict[str, Any]:
    """把信号雷达结果的买入/卖出信号推送出去（标题自动汇总买/卖家数）。"""
    title, content = push_mod.format_signal_message(req.rows, req.window_bars)
    result = await asyncio.to_thread(push_mod.send_all, title, content)
    return {"title": title, "content": content, **result}


__all__ = ["router"]
