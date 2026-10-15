"""买卖信号推送服务：配好 key 即可把信号雷达的买入/卖出信号推出去。

支持的通道（全部 key-only，WebUI「推送设置」页填 key 即用）：

- ``serverchan`` Server酱 Turbo：key = SendKey，
  ``https://sctapi.ftqq.com/{key}.send``（POST title/desp）。
- ``wxpush`` WXPush（Cloudflare Workers 自部署版）：key = token，
  endpoint = 你的 Worker 地址（默认 ``https://wxpush.cn/api/push`` 兼容入口），
  POST JSON ``{token, title, content}``。
- ``baidu`` 百度云推送（服务端代理版）：key = ApiKey，
  endpoint = 自建/代理推送网关地址，POST JSON ``{api_key, title, content}``。
  直连百度推送需 ak+sk 双签，本模块走"填 key 经网关转发"形态，与其余通道一致。
- ``mob`` MobPush（服务端 REST 版）：key = appKey，
  endpoint = MobPush REST 地址（默认官网 REST 入口可配），
  POST JSON ``{app_key, title, content}``。
- ``webhook`` 通用 Webhook：endpoint = 完整 URL，key 可空（作 token 拼 query），
  POST JSON ``{title, content, key}``。企业微信机器人/钉钉/Bark 都可经此接入。

配置落盘 ``~/.easy_tdx/push.json``（随 ``EASY_TDX_CONFIG_DIR`` 走），结构::

    {"channels": [{"provider": "serverchan", "key": "...", "endpoint": "",
                   "enabled": true}], "only_signal": true}

发送走标准库 ``urllib``（不新增第三方依赖），单通道 10s 超时，
失败只返回 error，不抛错中断其余通道。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 支持的 provider id → 中文名（前端下拉与后端校验共用）。
PROVIDERS: dict[str, str] = {
    "serverchan": "Server酱",
    "wxpush": "WXPush",
    "baidu": "百度云推送",
    "mob": "MobPush",
    "webhook": "通用 Webhook",
}

_TIMEOUT = 10.0


def _config_dir() -> Path:
    return Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))


def config_path() -> Path:
    return _config_dir() / "push.json"


@dataclass
class PushChannel:
    """单个推送通道配置。key 脱敏回显，提交空串/脱敏串 = 不修改。"""

    provider: str = "serverchan"
    key: str = ""
    endpoint: str = ""
    enabled: bool = True

    def masked(self) -> dict[str, Any]:
        d = asdict(self)
        d["key"] = mask_key(self.key)
        return d


@dataclass
class PushConfig:
    channels: list[PushChannel] = field(default_factory=list)

    def to_dict(self, mask_api_key: bool = False) -> dict[str, Any]:
        if mask_api_key:
            return {"channels": [c.masked() for c in self.channels]}
        return {"channels": [asdict(c) for c in self.channels]}


def mask_key(key: str) -> str:
    """脱敏：保留首尾各 2 字符，其余打星；空串直接返回。"""
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return f"{key[:2]}***{key[-2:]}"


def load_config() -> PushConfig:
    try:
        raw = json.loads(config_path().read_text("utf-8"))
    except Exception:
        return PushConfig()
    channels: list[PushChannel] = []
    for item in raw.get("channels", []) if isinstance(raw, dict) else []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider", "")).strip().lower()
        if provider not in PROVIDERS:
            continue
        channels.append(
            PushChannel(
                provider=provider,
                key=str(item.get("key", "")),
                endpoint=str(item.get("endpoint", "")).strip(),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return PushConfig(channels=channels)


def save_config(cfg: PushConfig) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(path)
    return path


def merge_key(submitted: str, current: str) -> str:
    """表单语义：空串/脱敏串回传 = 沿用；CLEAR = 清除；其余 = 覆盖。"""
    key = (submitted or "").strip()
    if not key or key == mask_key(current):
        return current
    if key.upper() == "CLEAR":
        return ""
    return key


def _validate_url(url: str) -> str:
    """校验推送目标 URL 的 scheme，只允许 http/https。

    推送 endpoint 由用户在设置页自由填写。此前未做任何 scheme 校验，``file://``
    会被 urllib 的 FileHandler 直接打开并读取本地文件（FileHandler 不检查
    HTTP method）——构成"盲 SSRF + 本地文件存在性 oracle"。
    """
    import ipaddress

    raw = (url or "").strip()
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"推送地址只支持 http/https：{url!r}")
    if not parsed.netloc:
        raise ValueError(f"推送地址缺少主机名：{url!r}")
    host = (parsed.hostname or "").lower()
    # 云元数据/回环硬拦截（内网业务网关仍放行，但元数据/回环绝不放行；
    # 私有网段 10/172.16/192.168 刻意不禁：用户自配内网推送网关仍需可用，
    # 见 review 备注。此处只拦确定危险的本地/元数据/未指定地址。）
    if host in (
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.google",
        "localhost",
    ):
        raise ValueError(f"推送地址禁止访问云元数据：{url!r}")
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            # 169.254/16（含元数据）/127/8/::1/0.0.0.0/组播/保留段一律拒绝；
            # 私有网段刻意放行（内网网关场景）
            raise ValueError(f"推送地址禁止访问本地/链路地址：{url!r}")
    except ValueError as e:
        # ip_address 抛错 = 非 IP 主机名（域名），仅拦截元数据域名后放行
        if "禁止访问" in str(e):
            raise
    return url


def _validate_serverchan_key(key: str) -> str:
    """Server酱 SendKey 白名单：字母数字/_/-，4-128 字符，防路径注入（../ 破出 .send）。"""
    import re

    k = (key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,128}", k):
        raise ValueError("Server酱 SendKey 非法（须为 4-128 位字母/数字/_/-）")
    return k


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止跟随重定向。

    否则攻击者可把 endpoint 配成一个合法的 http 地址，再 302 到 ``file://``，
    绕过 :func:`_validate_url` 的 scheme 校验。
    """

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def _post_json(url: str, payload: dict[str, Any]) -> str:
    url = _validate_url(url)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with _OPENER.open(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — 用户自配网关
        text: str = resp.read().decode("utf-8", "replace")[:500]
        return text


def _post_form(url: str, fields: dict[str, str]) -> str:
    url = _validate_url(url)
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with _OPENER.open(req, timeout=_TIMEOUT) as resp:  # noqa: S310
        text: str = resp.read().decode("utf-8", "replace")[:500]
        return text


def send_one(channel: PushChannel, title: str, content: str) -> dict[str, Any]:
    """经单个通道发送。返回 ``{"ok": bool, "provider": ..., "error"?: ...}``。"""
    provider = channel.provider
    try:
        if provider == "serverchan":
            if not channel.key:
                raise ValueError("Server酱缺少 SendKey")
            _post_form(
                f"https://sctapi.ftqq.com/{_validate_serverchan_key(channel.key)}.send",
                {"title": title, "desp": content},
            )
        elif provider == "wxpush":
            if not channel.key:
                raise ValueError("WXPush 缺少 token")
            url = channel.endpoint or "https://wxpush.cn/api/push"
            _post_json(url, {"token": channel.key, "title": title, "content": content})
        elif provider == "baidu":
            if not channel.key:
                raise ValueError("百度云推送缺少 ApiKey")
            if not channel.endpoint:
                raise ValueError("百度云推送需填写网关 endpoint（直连需 ak+sk 双签，走网关转发）")
            _post_json(
                channel.endpoint, {"api_key": channel.key, "title": title, "content": content}
            )
        elif provider == "mob":
            if not channel.key:
                raise ValueError("MobPush 缺少 appKey")
            url = channel.endpoint or "https://api.push.mob.com/push"
            _post_json(url, {"app_key": channel.key, "title": title, "content": content})
        elif provider == "webhook":
            if not channel.endpoint:
                raise ValueError("Webhook 缺少 endpoint URL")
            url = channel.endpoint
            if channel.key:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}key={urllib.parse.quote(channel.key)}"
            _post_json(url, {"title": title, "content": content, "key": channel.key})
        else:
            raise ValueError(f"未知推送通道 '{provider}'")
    except Exception as exc:  # noqa: BLE001 — 单通道失败只记结果
        logger.warning("推送失败 (%s): %s", provider, exc)
        return {"ok": False, "provider": provider, "error": str(exc) or type(exc).__name__}
    return {"ok": True, "provider": provider}


def send_all(title: str, content: str) -> dict[str, Any]:
    """经全部启用的通道发送，汇总结果（无启用通道时 ok=False）。"""
    cfg = load_config()
    active = [c for c in cfg.channels if c.enabled and c.provider in PROVIDERS]
    if not active:
        return {"ok": False, "sent": 0, "results": [], "error": "尚未配置启用的推送通道"}
    results = [send_one(c, title, content) for c in active]
    sent = sum(1 for r in results if r["ok"])
    return {"ok": sent > 0, "sent": sent, "total": len(results), "results": results}


def format_signal_message(rows: list[dict[str, Any]], window_bars: int = 5) -> tuple[str, str]:
    """信号扫描结果行 → 推送标题/正文（只含窗口内有 BUY/SELL 的行）。"""
    buys = [r for r in rows if not r.get("error") and r.get("latest_signal") == "BUY"]
    sells = [r for r in rows if not r.get("error") and r.get("latest_signal") == "SELL"]
    title = f"信号雷达：买入 {len(buys)} / 卖出 {len(sells)}（近{window_bars}根）"
    lines = []
    for r in buys + sells:
        sig = "买入" if r.get("latest_signal") == "BUY" else "卖出"
        lines.append(
            f"{sig} {r.get('symbol', '')} {r.get('strategy_label') or r.get('strategy', '')}"
            f" @{r.get('signal_date', '')} 收{r.get('last_close', '-')}"
        )
    content = "\n".join(lines[:50]) or "窗口内无买卖信号"
    if len(lines) > 50:
        content += f"\n…等共 {len(lines)} 条"
    return title, content


__all__ = [
    "PROVIDERS",
    "PushChannel",
    "PushConfig",
    "config_path",
    "format_signal_message",
    "load_config",
    "mask_key",
    "merge_key",
    "save_config",
    "send_all",
    "send_one",
]
