"""smoke_all — easy-tdx 全功能冒烟脚本。

逐个调用 `easy-tdx` 的真实命令（真实数据源）与 Web API，检查退出码与输出，
覆盖全部命令域：行情 / K线 / 分时 / 逐笔 / 集合竞价 / 板块 / 资金 / 指标 /
缠论 / 公式 / 因子 / 回测 / 寻优 / 组合 / 扩展市场（港股·美股·期货）/ 财务 /
公告 / 中金所 / 仓库 / 离线文件 / Web API（REST + WebSocket）。

与 `scripts/verify_ci.sh` 的分工：verify_ci 跑单测 + 静态检查 + 前端 E2E（全 mock、
不联网）；本脚本跑**真实数据链路**的端到端冒烟，用于发布前的人工验收。

用法::

    .venv/Scripts/python.exe scripts/smoke_all.py              # 全部（含联网）
    .venv/Scripts/python.exe scripts/smoke_all.py --offline    # 仅离线命令（不联网）
    .venv/Scripts/python.exe scripts/smoke_all.py --only kline,quote,chanlun
    .venv/Scripts/python.exe scripts/smoke_all.py --no-web     # 跳过 Web API 段
    .venv/Scripts/python.exe scripts/smoke_all.py --list       # 只列出检查项

退出码：0 = 无核心失败（第三方站点/本地数据依赖的失败仅告警），1 = 有核心检查失败。

检查分级:

    core  核心链路，失败记 FAIL 并影响退出码（默认）。
    net   依赖第三方站点（新浪/巨潮/中金所），失败记 WARN 不影响退出码。
    env   依赖本地通达信安装目录 / 可选依赖，环境不具备时记 SKIP。
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Check:
    name: str
    args: list[str]
    kind: str = "core"  # core | net | env
    timeout: int = 90


# ── 全量检查清单（name 即 CLI 子命令域）────────────────────────────────────────

CHECKS: list[Check] = [
    # 离线：不连任何网络
    Check("version", ["version"]),
    Check("indicator-list", ["indicator-list"]),
    Check("strategies", ["strategies"]),
    Check("factor-list", ["factor", "list"]),
    Check("factor-analyze", ["factor", "analyze", "momentum_20d"]),
    Check("pfactor-backtest", ["pfactor", "backtest", "momentum_20d"]),
    Check("offline-home", ["offline", "home"], kind="env"),
    Check("warehouse-stats", ["warehouse", "stats"], kind="env"),
    Check("warehouse-check", ["warehouse", "check"], kind="env"),
    # 联网：通达信协议核心链路
    Check("ping", ["ping"], timeout=60),
    Check("kline", ["kline", "SH", "600519", "--count", "5"]),
    Check("quote", ["quote", "SZ 000001,SH 600519"]),
    Check("quote-list", ["quote-list", "A", "--count", "5"]),
    Check("tick", ["tick", "SZ", "000001"]),
    Check("transaction", ["transaction", "SZ", "000001", "--count", "5"]),
    Check("auction", ["auction", "SZ", "000001"]),
    Check("symbol-info", ["symbol-info", "SZ", "000001"]),
    Check("server-info", ["server-info"]),
    Check("market-stat", ["market-stat"]),
    Check("unusual", ["unusual", "SH", "--count", "5"]),
    Check("board-list", ["board-list", "--type", "GN", "--count", "5"]),
    Check("board-members", ["board-members", "881001"]),
    Check("board-summary", ["board-summary", "881001"]),
    Check("board-ranking", ["board-ranking", "--type", "HY", "--top", "5"]),
    Check("board-change-ranking", ["board-change-ranking", "--type", "HY", "--days", "5"]),
    Check("belong-board", ["belong-board", "SZ", "000001"]),
    Check("capital-flow", ["capital-flow", "SH", "600519"]),
    Check(
        "indicator-multi",
        ["indicator", "MACD,KDJ,RSI,BOLL", "-m", "SH", "-c", "600519", "--count", "40"],
    ),
    Check(
        "indicator-zhuoyao", ["indicator", "ZHUOYAO", "-m", "SH", "-c", "600519", "--count", "40"]
    ),
    Check(
        "indicator-bias-signal",
        ["indicator", "BIAS_SIGNAL", "-m", "SH", "-c", "600519", "--count", "40"],
    ),
    Check("chanlun", ["chanlun", "SH", "600519", "--count", "200"]),
    Check(
        "chanlun-multilevel",
        ["chanlun", "SZ", "000001", "--multi-level", "30MIN", "--count", "300"],
    ),
    Check(
        "formula-compute",
        ["formula", "compute", "SH", "600519", "--formula", "金叉: CROSS(MA(C,5), MA(C,20));"],
    ),
    Check(
        "formula-backtest",
        [
            "formula",
            "backtest",
            "SH",
            "600519",
            "--formula",
            "金叉: CROSS(MA(C,5), MA(C,20));",
            "--count",
            "300",
        ],
    ),
    Check(
        "backtest",
        ["backtest", "SH", "600519", "--strategy-file", "strategies/ma_cross.py", "--count", "300"],
    ),
    Check(
        "backtest-evaluate",
        [
            "backtest",
            "SH",
            "600519",
            "--strategy-file",
            "strategies/ma_cross.py",
            "--count",
            "300",
            "--evaluate",
        ],
        timeout=150,
    ),
    Check(
        "optimize",
        [
            "optimize",
            "SH",
            "600519",
            "--strategy",
            "ma_cross",
            "--count",
            "250",
            "--workers",
            "1",
            "--top",
            "3",
        ],
        timeout=150,
    ),
    Check(
        "portfolio",
        [
            "portfolio",
            "--stocks",
            "SZ:000001,SH:600519",
            "--strategy-file",
            "strategies/ma_cross.py",
            "--count",
            "300",
        ],
        timeout=150,
    ),
    Check("run-all", ["run-all", "SH", "600519", "--count", "300"], timeout=240),
    Check("finance-info", ["finance-info", "SH", "600519"]),
    Check("company-info", ["company-info", "SH", "600519"]),
    # 扩展市场：港股 / 美股 / 期货
    Check("ex-markets", ["ex", "markets"]),
    Check("ex-kline", ["ex", "kline", "HK_MAIN_BOARD", "00700", "--count", "10"]),
    Check("ex-quote", ["ex", "quote", "US_STOCK", "TSLA"]),
    Check("ex-quote-list", ["ex", "quote-list", "HK_MAIN_BOARD"]),
    # 本地通达信文件（需装通达信并下载数据）
    Check("offline-daily", ["offline", "daily", "SZ", "000001"], kind="env"),
    Check(
        "screen-scan",
        ["screen", "scan", "--strategy", "strategies/rsi_reversal.py"],
        kind="env",
        timeout=180,
    ),
    Check("screen-strength", ["screen", "strength", "--top", "5"], kind="env", timeout=180),
    # 第三方独立数据源：新浪 / 巨潮 / 中金所
    Check("f10", ["f10", "600519"], kind="net"),
    Check("announcement", ["announcement", "600519", "--count", "5"], kind="net"),
    Check("ccpm", ["ccpm", "IF"], kind="net", timeout=60),
]


# ── 执行 ────────────────────────────────────────────────────────────────────


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # 隔离配置目录：冒烟不污染真实 ~/.easy_tdx（自选/策略库/任务/仓库缓存）
    env.setdefault("EASY_TDX_CONFIG_DIR", tempfile.mkdtemp(prefix="easy_tdx_smoke_"))
    env["EASY_TDX_NO_TASK_DB"] = "1"
    return env


def run_cli(check: Check, env: dict[str, str]) -> tuple[str, str]:
    """返回 (status, detail)，status ∈ {PASS, FAIL, WARN, SKIP}。"""
    cmd = [sys.executable, "-m", "easy_tdx", *check.args]
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=check.timeout,
        )
    except subprocess.TimeoutExpired:
        return "FAIL", f"超时 {check.timeout}s"
    elapsed = time.perf_counter() - started
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip().splitlines()
    tail = err[-1] if err else ""

    if proc.returncode == 0 and out:
        return "PASS", f"{elapsed:.1f}s, {len(out)}B"
    detail = f"rc={proc.returncode} {elapsed:.1f}s"
    if tail:
        detail += f" | {tail[:120]}"
    if check.kind == "net":
        return "WARN", detail
    if check.kind == "env":
        return "SKIP", detail
    return "FAIL", detail


# ── Web API ─────────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _get(url: str, timeout: float = 8.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (本机回环)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        return exc.code, b""
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode("utf-8", "replace")


def run_web(env: dict[str, str]) -> tuple[str, str]:
    """启动 mock 模式 serve，抽查 REST 端点 + WebSocket tick，随后关闭。"""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(env)
    env["EASY_TDX_E2E_MOCK"] = "1"
    # 服务端日志写文件而非 PIPE：写满管道缓冲区会阻塞 uvicorn 事件循环，
    # 后续请求全部超时（本脚本首版即踩此坑）。
    log_path = Path(env["EASY_TDX_CONFIG_DIR"]) / "smoke_serve.log"
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [sys.executable, "-m", "easy_tdx", "serve", "--port", str(port), "--no-open-browser"],
        cwd=ROOT,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.time() + 40
        up = False
        while time.time() < deadline:
            if proc.poll() is not None:
                return "FAIL", "serve 进程提前退出"
            status, _ = _get(f"{base}/api/v1/meta", timeout=2)
            if status == 200:
                up = True
                break
            time.sleep(0.5)
        if not up:
            return "FAIL", "serve 40s 内未就绪"

        endpoints = [
            "/api/v1/meta",
            "/api/v1/bars?market=SH&code=600519&category=DAY&count=30",
            "/api/v1/market/stat",
            "/api/v1/security/count?market=SH",
            "/api/v1/mac/quote-list?count=10",
            "/api/v1/backtest/strategies",
            "/api/v1/watchlist",
            "/docs",
            "/",
        ]
        failed: list[str] = []
        for ep in endpoints:
            status, body = _get(f"{base}{ep}")
            if status != 200:
                failed.append(f"{ep}->{status}")

        ws_note = ""
        ws_ok = _ws_check(base, env)
        if ws_ok is False:
            ws_note = "; ws 无 tick"
        elif ws_ok is None:
            ws_note = "; ws 跳过(缺 websockets)"

        if failed:
            return "FAIL", "REST 异常: " + ", ".join(failed) + ws_note
        return "PASS", f"{len(endpoints)} 端点 200{ws_note}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()


def _ws_check(base: str, env: dict[str, str]) -> bool | None:
    """WebSocket 实时推送抽查：收到至少一帧 tick 记 True；缺依赖返回 None。"""
    try:
        import asyncio

        import websockets
    except ImportError:
        return None

    ws_url = base.replace("http://", "ws://") + "/api/v1/ws/realtime/SZ000001"

    async def _listen() -> bool:
        try:
            async with websockets.connect(ws_url) as ws:
                for _ in range(3):
                    msg = await asyncio.wait_for(ws.recv(), timeout=8.0)
                    if '"tick"' in msg:
                        return True
        except Exception:  # noqa: BLE001
            return False
        return False

    try:
        return asyncio.run(_listen())
    except Exception:  # noqa: BLE001
        return False


# ── 主流程 ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="easy-tdx 全功能冒烟")
    parser.add_argument("--offline", action="store_true", help="只跑离线检查（跳过 core 联网）")
    parser.add_argument("--only", default=None, help="逗号分隔的检查名白名单")
    parser.add_argument("--no-web", action="store_true", help="跳过 Web API 段")
    parser.add_argument("--list", action="store_true", help="只列出检查项")
    args = parser.parse_args()

    if args.list:
        for c in CHECKS:
            print(f"[{c.kind:4}] {c.name:24} easy-tdx {' '.join(c.args)}")
        return 0

    selected = CHECKS
    if args.only:
        names = {n.strip() for n in args.only.split(",") if n.strip()}
        selected = [c for c in selected if c.name in names]
    if args.offline:
        selected = [c for c in selected if c.kind == "env" or c.name in _OFFLINE_NAMES]

    env = _child_env()
    print(
        f"easy-tdx 冒烟 — {len(selected)} 项 CLI"
        + ("" if args.no_web else " + Web API")
        + f"（配置目录 {env['EASY_TDX_CONFIG_DIR']}）\n"
    )

    results: list[tuple[Check, str, str]] = []
    for check in selected:
        status, detail = run_cli(check, env)
        results.append((check, status, detail))
        mark = {"PASS": "OK  ", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}[status]
        print(f"  [{mark}] {check.name:24} {detail}")

    if not args.no_web:
        status, detail = run_web(env)
        results.append((Check("web-api", [], kind="core"), status, detail))
        mark = {"PASS": "OK  ", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}[status]
        print(f"  [{mark}] {'web-api':24} {detail}")

    n_pass = sum(1 for _, s, _ in results if s == "PASS")
    n_warn = sum(1 for _, s, _ in results if s == "WARN")
    n_skip = sum(1 for _, s, _ in results if s == "SKIP")
    n_fail = sum(1 for _, s, _ in results if s == "FAIL")

    print(
        f"\n汇总：{n_pass} 通过 / {n_fail} 失败 / {n_warn} 告警（第三方源） / {n_skip} 跳过（环境）"
    )
    if n_fail:
        print("失败项：")
        for check, status, detail in results:
            if status == "FAIL":
                print(f"  - {check.name}: {detail}")
    return 1 if n_fail else 0


# 离线模式（--offline）保留的纯离线检查（不连任何网络，无需本地通达信目录）
_OFFLINE_NAMES: set[str] = {
    "version",
    "indicator-list",
    "strategies",
    "factor-list",
    "factor-analyze",
    "pfactor-backtest",
}


if __name__ == "__main__":
    raise SystemExit(main())
