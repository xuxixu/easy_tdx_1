"""重建「美股观测雷达」快照（冷路径：抓日线 → 算指标 → 扫信号 → 写 JSON）。

用法::

    python scripts/build_us_radar.py              # 全量重建
    python scripts/build_us_radar.py --dry-run    # 只抓数算指标，不写文件
    python scripts/build_us_radar.py --out X.json # 写到别处

为什么是独立脚本而不是挂到 CLI
------------------------------
本项目 CLI（``easy_tdx.cli``）面向「用户高频、日常」的看盘/回测操作；
重建快照是低频、耗时较长、且需要单独一套进度与摘要输出的运维动作。
塞进 CLI 会让主命令的执行时间从毫秒级变成分钟级，也让两者的参数空间互相污染。

耗时预期：冷启动（无缓存）320 只标的、4 并发，实测约 1~2 分钟；命中缓存时
只补过期部分，十几秒。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.radar import build, write_snapshot  # noqa: E402
from easy_tdx.radar.bars import default_cache_dir, workers  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="重建美股观测雷达快照")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出 JSON 路径（默认 web-ui/public/data/us-radar.json）",
    )
    ap.add_argument("--cache", type=Path, default=None, help="日线缓存目录")
    ap.add_argument("--workers", type=int, default=None, help="并发数（默认 4）")
    ap.add_argument("--dry-run", action="store_true", help="只抓数与计算，不写文件")
    ap.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    if args.workers:
        import os

        os.environ["EASY_TDX_RADAR_WORKERS"] = str(args.workers)

    t0 = time.time()
    # [已打印的条数, 上次打印的时刻]
    last: list[float] = [0, 0.0]

    def _progress(done: int, total: int, symbol: str) -> None:
        # 每 25 只或每 5 秒打一次，避免刷屏
        now = time.time()
        if done == total or done - last[0] >= 25 or now - last[1] >= 5:
            last[0], last[1] = done, now
            print(f"  取数 {done}/{total}  ({symbol})", flush=True)

    cache = args.cache or default_cache_dir()
    print(f"缓存目录：{cache}")
    print(f"并发数：  {workers()}")

    snap, report = build.build_snapshot(cache_dir=cache, on_progress=_progress)

    print()
    print(f"基准日：      {report.as_of}")
    print(f"实算标的：    {report.universe} 只（日线成功 {report.fetched}）")
    if report.failed:
        print(f"取数失败：    {len(report.failed)} 只 → {', '.join(report.failed[:12])}")
    print(f"分区状态：    {report.sections}")
    degraded = snap["meta"].get("degraded") or {}
    if degraded:
        print()
        print("以下分区无数据源，已写为 null（前端会显示「数据源不可用」）：")
        for k, v in degraded.items():
            print(f"  · {k}：{v}")

    if args.dry_run:
        print(f"\n[dry-run] 未写文件。用时 {time.time() - t0:.1f}s")
        return 0

    path = write_snapshot(snap, args.out)
    print(f"\n已写入 {path}  用时 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())