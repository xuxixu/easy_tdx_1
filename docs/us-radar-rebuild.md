# 美股观测雷达：快照定时重建

本文说明 `us-radar.json`（美股观测雷达整页数据）在运行态如何自动重建、前端如何感知更新，以及哪些情况下会自动降级。

## 这份数据是什么

- 一整份快照 JSON：`web-ui/public/data/us-radar.json`（约 465KB），18 个区块 / 291 只观测池。
- 由 `scripts/build_us_radar.py` → `radar.build.build_snapshot()` 生成：抓新浪美股**日线** → 算指标/信号/归因 → 写 JSON。
- 数据源是**收盘后日线**，不是盘中实时行情。`meta.asOf` 标注基准交易日，`meta.builtAt` 标注构建日。
- 快照里 `meta.degraded` 登记了无可达数据源的分区（期权链/基本面/机构持股/国会披露/新闻/原油期货等），前端显示为「数据源不可用」，不冒充有数据。

## 定时重建（开发 / 源码运行态）

`easy_tdx serve` 启动时，lifespan 会挂载 `RadarRebuilder`（`src/easy_tdx/web/radar_rebuilder.py`）：

- **默认每 24 小时**重建一次（可用 `EASY_TDX_RADAR_REBUILD_INTERVAL` 覆盖，单位秒）。
- 启动时若发现现有快照的 `asOf` 距今超过 1 天，**立即补一次**重建，避免服务重启后一整天都用过时快照。
- 构建是同步重函数（291 只 × 日线，内部线程池，冷启 1~2 分钟），放在 `asyncio.to_thread` 里跑，**不阻塞 Web 事件循环**；加锁防「定时 + 手动」并发重入。
- 产物用**临时文件 + `os.replace` 原子替换**，前端不会读到写了一半的 JSON。
- 构建失败（如新浪源不可达）**保留旧快照**，只记状态与日志，绝不中断服务。

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `EASY_TDX_RADAR_REBUILD` | 开 | 设为 `0/false/off` 完全关闭定时重建 |
| `EASY_TDX_RADAR_REBUILD_INTERVAL` | `86400` | 重建间隔秒数；`<=0` 等价关闭 |
| `EASY_TDX_RADAR_REBUILD_AT_START` | `1` | 设为 `0` 关闭「启动时立即补建」（运维/测试只想沿用旧快照时） |
| `EASY_TDX_E2E_MOCK` | — | `1` 时（E2E/测试）自动禁用重建，不打外部源 |

## 前端如何感知更新

- 页面加载时 `fetchUsRadar()` 拉取整份快照。
- 每 60 秒轮询一次 `GET /api/v1/us-radar/version`（**只读一个 meta**，不下载 465KB 全文）。
  - 返回的 `built_at` 与当前已加载的 `builtAt` 一致 → 什么都不做；
  - 变了 → 重新拉全文并替换页面数据。
- 页头「定时重建 · 每日收盘后」状态块显示启用/未启用、累计成功/失败次数；启用时可点「重新构建」手动触发。
- 版本接口不可用时（纯静态托管 / 老后端）静默降级为「纯静态快照」，不弹错误。

### 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/us-radar/version` | 轻量版本探测：`built_at` / `as_of` / `rebuild` 状态 |
| GET | `/api/v1/us-radar/status` | 重建器状态（是否启用、上次成败、累计次数） |
| POST | `/api/v1/us-radar/rebuild` | 手动触发一次（非阻塞）；未启用/已在跑返回 409 |

## 降级：EXE 与纯静态托管

PyInstaller onefile EXE 里，`web-ui/public/data/us-radar.json` 是**只读打包资源**，且源码目录不存在——无法回写。因此：

- `sys.frozen` 为真时 `rebuild_enabled()` 返回 `False`，`RadarRebuilder` 不启动；
- 状态接口如实返回 `enabled: false`，页头标注「静态快照（未启用定时重建）」；
- 页面正常使用**打包时的那份快照**，功能完整，只是不会自动更新。

要让 EXE 用户拿到新数据，重新构建并发布新版 EXE 即可。

## 手动重建（不启服务）

```bash
python scripts/build_us_radar.py              # 全量重建并写回默认路径
python scripts/build_us_radar.py --dry-run    # 只算不写，验证数据源
python scripts/build_us_radar.py --workers 2  # 降低并发（新浪限频时）
```

## 为什么不做「盘中实时行情叠加」

18 个区块里大量字段是**离线派生量**（RSI/MA/支撑压力/信号命中率/质地分/题材聚合/拥挤度），必须由完整日线序列重算；后端实时报价接口（`/overseas/quotes`）只给一个价格点，无法重算这些量。另有 8 类分区根本无可达数据源（见 `meta.degraded`）。因此本页的定位始终是「收盘后日线快照」，定时重建解决的是**快照过期**问题，不是把整页伪装成盘中实时终端。若将来需要盘中行情叠加，应作为独立层（只刷新 `close`/当日涨跌等点值并明确标注），不要混入快照的派生字段。
