"""集中管理服务器地址、端口、超时等配置。

优先级：环境变量 > ~/.easy_tdx/config.json > 源码内嵌默认值。

配置文件示例::

    {
      "best_host": "180.153.18.170",
      "best_host_updated_at": "2026-05-22T10:30:00",
      "known_hosts": ["111.229.247.189", ...],
      "calc_hosts": ["120.76.152.87"],
      "mac_hosts": ["121.36.248.138", ...],
      "port": 7709,
      "timeout": 15.0
    }

环境变量覆盖::

    EASY_TDX_HOST        -- 单台主机地址
    EASY_TDX_PORT        -- 端口
    EASY_TDX_TIMEOUT     -- 超时秒数
    EASY_TDX_KNOWN_HOSTS -- 逗号分隔的候选主机列表
    EASY_TDX_CONFIG_DIR  -- 配置文件目录（默认 ~/.easy_tdx）
"""

import json
import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

_CONFIG_DIR = Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# 业务时间统一用上海时区（与 client.py 一致），避免 naive datetime 跨时区歧义（审计 #18）。
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# ---------------------------------------------------------------------------
# 源码内嵌默认值（config.json 不存在或字段缺失时的兜底）
# ---------------------------------------------------------------------------

_FALLBACK_HOSTS: list[str] = [
    "111.229.247.189",
    "150.158.160.2",
    "180.153.18.170",
    "124.71.187.122",
    "180.153.18.171",
    "180.153.18.172",
    "119.147.212.81",
    "115.238.56.198",
    "115.238.90.165",
    "218.75.126.9",
    "47.107.75.159",
    "59.175.238.38",
    "110.41.147.114",
    "110.41.2.72",
    "101.33.225.16",
    "175.178.112.197",
    "175.178.128.227",
    "43.139.95.83",
    "124.223.163.242",
    "122.51.120.217",
    "123.60.164.122",
    "124.70.199.56",
    "62.234.50.143",
    "81.70.151.186",
    "82.156.214.79",
    "159.75.29.111",
    "43.139.18.171",
    "81.71.32.47",
    "122.51.232.182",
    "118.25.98.114",
    "121.36.225.169",
    "123.60.70.228",
    "123.60.73.44",
    "124.70.133.119",
    "124.71.187.72",
    "119.97.185.59",
    "129.204.230.128",
    "101.42.240.54",
    "124.71.9.153",
    "123.60.84.66",
    "111.230.186.52",
    "101.43.159.194",
    "120.53.8.251",
    "152.136.191.169",
    "116.205.163.254",
    "116.205.171.132",
    "116.205.183.150",
    "49.232.15.141",
    "82.156.174.84",
    "101.42.164.241",
    "101.35.121.35",
    "111.231.113.208",
]

_FALLBACK_CALC_HOSTS: list[str] = [
    "120.76.152.87",
]

_FALLBACK_MAC_HOSTS: list[str] = [
    "121.36.248.138",
    "123.60.47.136",
    "121.37.207.165",
]

_FALLBACK_EX_HOSTS: list[str] = [
    "112.74.214.43",
    "120.25.218.6",
    "43.139.173.246",
    "159.75.90.107",
    "106.52.170.195",
    "139.9.191.175",
    "175.24.47.69",
    "150.158.9.199",
    "150.158.20.127",
    "49.235.119.116",
    "49.234.13.160",
    "116.205.143.214",
    "124.71.223.19",
    "113.45.175.47",
    "123.60.173.210",
    "118.89.69.202",
]

_FALLBACK_MAC_EX_HOSTS: list[str] = [
    "116.205.135.205",
    "121.37.232.167",
]

_FALLBACK_PORT = 7709
_FALLBACK_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# 内部读写
# ---------------------------------------------------------------------------


def _load() -> dict[str, Any]:
    try:
        if _CONFIG_FILE.exists():
            return cast(dict[str, Any], json.loads(_CONFIG_FILE.read_text("utf-8")))
    except Exception:
        pass
    return {}


def _save(data: dict[str, Any]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(_CONFIG_FILE)


# 保护「读-改-写」全过程的进程内锁。
# _save() 用 tmp.replace() 保证了单文件写入的原子性，但 save_best_host /
# save_best_mac_host / ... 这些函数是 _load() → 改一个键 → _save() **整体覆写**。
# 它们会被 _execute 的成功/失败路径与 ping_all 的多个线程并发调用：线程 A 落
# best_host、线程 B 同时落 best_mac_host 时，后写者用的是自己读到的旧快照，
# A 的写入会凭空消失。锁把整段 read-modify-write 变成互斥的。
_CONFIG_LOCK = threading.Lock()


def _update(mutate: Callable[[dict[str, Any]], None]) -> None:
    """在锁内完成一次原子的「读 → 改 → 写」。"""
    with _CONFIG_LOCK:
        cfg = _load()
        mutate(cfg)
        _save(cfg)


# ---------------------------------------------------------------------------
# 公开 getter
# ---------------------------------------------------------------------------


def get_best_host() -> str:
    """返回当前最佳主机地址。优先级：环境变量 > config.json > 默认列表首个。

    含交叉污染校验：历史上 ``MacClient.from_best_host`` 曾误调 ``save_best_host``
    把 MAC 服务器写入 ``best_host``（v1.19.3 "取不到行情" bug）。这里检测到
    缓存的 host 不在标准 host 候选列表里时，自动重置为默认首个，避免用错协议。
    """
    env = os.environ.get("EASY_TDX_HOST")
    if env:
        return env
    cfg = _load()
    cached = cast(str, cfg.get("best_host", _FALLBACK_HOSTS[0]))

    # 交叉污染校验：cached 必须在标准 host 候选列表（known_hosts + 源码默认）里。
    # 如果是 MAC host（121.36.x.x 等），不在标准列表里 → 重置。
    all_std_hosts = set(cfg.get("known_hosts", [])) | set(_FALLBACK_HOSTS)
    if cached not in all_std_hosts:
        # 被污染了（MAC/ex host 混入），重置为默认首个并持久化
        cfg["best_host"] = _FALLBACK_HOSTS[0]
        cfg["best_host_updated_at"] = datetime.now(_SHANGHAI_TZ).isoformat()
        _save(cfg)
        return _FALLBACK_HOSTS[0]

    return cached


def get_known_hosts() -> list[str]:
    """返回候选行情主机列表。"""
    env = os.environ.get("EASY_TDX_KNOWN_HOSTS")
    if env:
        return [h.strip() for h in env.split(",") if h.strip()]
    cfg = _load()
    return cast(list[str], cfg.get("known_hosts", list(_FALLBACK_HOSTS)))


def get_calc_hosts() -> list[str]:
    """返回计算服务器列表。"""
    cfg = _load()
    return cast(list[str], cfg.get("calc_hosts", list(_FALLBACK_CALC_HOSTS)))


def get_mac_hosts() -> list[str]:
    """返回 MAC 行情服务器列表。"""
    cfg = _load()
    return cast(list[str], cfg.get("mac_hosts", list(_FALLBACK_MAC_HOSTS)))


def get_best_mac_host() -> str:
    """返回当前最佳 MAC 协议主机。

    与 ``get_best_host``（标准 TDX 协议）分开存：MAC 和标准协议用不同的
    服务器列表和协议格式，共用同一个字段会导致 MAC 客户端选出的 host
    被标准客户端误用，用标准协议请求 MAC 服务器返回空 body。
    """
    env = os.environ.get("EASY_TDX_MAC_HOST")
    if env:
        return env
    cfg = _load()
    return cast(str, cfg.get("best_mac_host", _FALLBACK_MAC_HOSTS[0]))


def get_ex_hosts() -> list[str]:
    """返回扩展行情服务器列表。"""
    cfg = _load()
    return cast(list[str], cfg.get("ex_hosts", list(_FALLBACK_EX_HOSTS)))


def get_best_ex_host() -> str:
    """返回当前最佳扩展行情主机。"""
    env = os.environ.get("EASY_TDX_EX_HOST")
    if env:
        return env
    cfg = _load()
    return cast(str, cfg.get("best_ex_host", _FALLBACK_EX_HOSTS[0]))


def get_mac_ex_hosts() -> list[str]:
    """返回 MAC 协议扩展行情服务器列表。"""
    cfg = _load()
    return cast(list[str], cfg.get("mac_ex_hosts", list(_FALLBACK_MAC_EX_HOSTS)))


def get_best_mac_ex_host() -> str:
    """返回当前最佳 MAC 协议扩展行情主机。"""
    env = os.environ.get("EASY_TDX_MAC_EX_HOST")
    if env:
        return env
    cfg = _load()
    return cast(str, cfg.get("best_mac_ex_host", _FALLBACK_MAC_EX_HOSTS[0]))


def get_port() -> int:
    """返回默认端口。"""
    env = os.environ.get("EASY_TDX_PORT")
    if env:
        return int(env)
    cfg = _load()
    return cast(int, cfg.get("port", _FALLBACK_PORT))


def get_timeout() -> float:
    """返回默认超时秒数。"""
    env = os.environ.get("EASY_TDX_TIMEOUT")
    if env:
        return float(env)
    cfg = _load()
    return cast(float, cfg.get("timeout", _FALLBACK_TIMEOUT))


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def save_best_host(host: str) -> None:
    """保存最佳主机到配置文件；首次写入时同时补全默认配置。"""

    def _mutate(cfg: dict[str, Any]) -> None:
        cfg["best_host"] = host
        cfg["best_host_updated_at"] = datetime.now(_SHANGHAI_TZ).isoformat()
        if "known_hosts" not in cfg:
            cfg["known_hosts"] = list(_FALLBACK_HOSTS)
        if "calc_hosts" not in cfg:
            cfg["calc_hosts"] = list(_FALLBACK_CALC_HOSTS)
        if "mac_hosts" not in cfg:
            cfg["mac_hosts"] = list(_FALLBACK_MAC_HOSTS)
        if "port" not in cfg:
            cfg["port"] = _FALLBACK_PORT
        if "ex_hosts" not in cfg:
            cfg["ex_hosts"] = list(_FALLBACK_EX_HOSTS)
        if "mac_ex_hosts" not in cfg:
            cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)

    _update(_mutate)


def save_best_ex_host(host: str) -> None:
    """保存最佳扩展行情主机到配置文件。"""

    def _mutate(cfg: dict[str, Any]) -> None:
        cfg["best_ex_host"] = host
        cfg["best_ex_host_updated_at"] = datetime.now().isoformat()
        if "ex_hosts" not in cfg:
            cfg["ex_hosts"] = list(_FALLBACK_EX_HOSTS)
        if "mac_ex_hosts" not in cfg:
            cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)

    _update(_mutate)


def save_best_mac_ex_host(host: str) -> None:
    """保存最佳 MAC 协议扩展行情主机到配置文件。"""

    def _mutate(cfg: dict[str, Any]) -> None:
        cfg["best_mac_ex_host"] = host
        cfg["best_mac_ex_host_updated_at"] = datetime.now().isoformat()
        if "mac_ex_hosts" not in cfg:
            cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)

    _update(_mutate)


def save_best_mac_host(host: str) -> None:
    """保存最佳 MAC 协议主机到配置文件（独立于标准 TDX 的 best_host）。

    MAC 客户端必须用这个，不能复用 ``save_best_host``——否则选出的 MAC
    服务器会污染标准 TDX 协议的 ``best_host``，导致标准客户端用错协议请求
    MAC 服务器，返回空 body（v1.19.3 "取不到行情" bug 的根因）。
    """

    def _mutate(cfg: dict[str, Any]) -> None:
        cfg["best_mac_host"] = host
        cfg["best_mac_host_updated_at"] = datetime.now(_SHANGHAI_TZ).isoformat()
        if "mac_hosts" not in cfg:
            cfg["mac_hosts"] = list(_FALLBACK_MAC_HOSTS)

    _update(_mutate)


# ---------------------------------------------------------------------------
# 自定义服务器增删改（WebUI「服务器设置」页用）
# ---------------------------------------------------------------------------


def _valid_host(host: str) -> bool:
    """校验候选服务器地址：IP 或域名，无 scheme/路径/端口/凭据。

    这个值会被直接拿去建 TCP 连接（POST /server/hosts → /server/switch），
    所以只允许"纯主机"形态：拒绝空白与控制字符、拒绝 ``http://`` 之类带
    scheme 的串、拒绝内嵌路径或 ``user:pass@host`` 凭据、拒绝内嵌端口
    （端口由 config 的 port 字段统一决定）。这样可避免把任意 URL 串当主机名
    交给连接层，也避免 ``169.254.169.254/xxx`` 这类带路径的探测输入。
    """
    if not host or len(host) > 253:
        return False
    s = host.strip()
    if not s or s != host:
        return False
    if any(c.isspace() or ord(c) < 33 for c in host):
        return False
    # 不允许 scheme / 路径 / 凭据 / 端口等"非纯主机"字符
    if any(c in host for c in "/\\@:?#[]"):
        return False
    # 只允许字母、数字、连字符、点的组合（域名 / IPv4 的字面形态）
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.")
    if not all(c in allowed for c in host):
        return False
    # 不能以点或连字符开头/结尾，不能有连续点
    if host[0] in ".-" or host[-1] in ".-" or ".." in host:
        return False
    return True


def add_custom_host(host: str) -> list[str]:
    """新增一台候选行情服务器（去重，追加到 known_hosts 末尾并持久化）。

    Raises:
        ValueError: host 非法（空/超长/含空白）。
    """
    h = (host or "").strip()
    if not _valid_host(h):
        raise ValueError(f"非法服务器地址 '{host}'（须为 IP 或域名，无空白，≤253 字符）")
    result: list[str] = []

    def _mutate(cfg: dict[str, Any]) -> None:
        hosts = list(cfg.get("known_hosts", list(_FALLBACK_HOSTS)))
        if h not in hosts:
            hosts.append(h)
            cfg["known_hosts"] = hosts
        result[:] = hosts

    _update(_mutate)
    return result


def remove_custom_host(host: str) -> list[str]:
    """删除一台候选服务器。至少保留 1 台（删空会被拒绝）。

    当前 best_host 被删时自动回落到列表首个。

    Raises:
        ValueError: host 不在列表 / 删除后列表为空。
    """
    h = (host or "").strip()
    result: list[str] = []

    def _mutate(cfg: dict[str, Any]) -> None:
        hosts = list(cfg.get("known_hosts", list(_FALLBACK_HOSTS)))
        if h not in hosts:
            raise ValueError(f"服务器 {h} 不在候选列表里")
        if len(hosts) <= 1:
            raise ValueError("至少保留 1 台服务器，不能全部删除")
        hosts = [x for x in hosts if x != h]
        cfg["known_hosts"] = hosts
        if cfg.get("best_host") == h:
            cfg["best_host"] = hosts[0]
            cfg["best_host_updated_at"] = datetime.now(_SHANGHAI_TZ).isoformat()
        result[:] = hosts

    _update(_mutate)
    return result


def set_known_hosts(hosts: list[str]) -> list[str]:
    """整体替换候选列表（去重保序，至少保留 1 台并持久化）。

    Raises:
        ValueError: 列表为空 / 含非法地址。
    """
    cleaned: list[str] = []
    for h in hosts or []:
        item = (h or "").strip()
        if not _valid_host(item):
            raise ValueError(f"非法服务器地址 '{h}'")
        if item not in cleaned:
            cleaned.append(item)
    if not cleaned:
        raise ValueError("候选服务器列表不能为空")

    def _mutate(cfg: dict[str, Any]) -> None:
        cfg["known_hosts"] = cleaned
        if cfg.get("best_host") not in cleaned:
            cfg["best_host"] = cleaned[0]
            cfg["best_host_updated_at"] = datetime.now(_SHANGHAI_TZ).isoformat()

    _update(_mutate)
    return cleaned
