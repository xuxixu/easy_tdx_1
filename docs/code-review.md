# easy-tdx 全面代码审查报告

> 审查范围：全库（数据管线、回测引擎、Web/实时推送、指标/走势/因子/选股）。
> 审查日期：2026-10-12
> 方法：直接阅读核心源码 + 分包并行探索。部分深层模块因工具限制未能逐行核验，已明确标注。

## 总体评价

整体工程质量高：七层架构清晰、协议层无 I/O、领域层零网络、网关统一入口、CLI 薄封装等原则执行到位；类型标注（mypy strict）覆盖面广；错误处理与边界防护（回撤除零、NaN 过滤、截断容错、空数据返回空结果）考虑周全。以下问题按严重度排序，多数为边界健壮性与语义一致性瑕疵而非功能性瘫痪。

---

## 一、数据获取管线（transport / commands / codec / client）

### 已核验缺陷

**1. 帧头失同步时 transport 层不清理 socket（sync + async）— 资源泄漏**
- `transport/sync.py` 的 `execute()` 只捕获 `OSError`（约 L197）做 `_close_socket_unlocked()`；但 `codec/frame.parse_header` 对魔数不符会抛 `TdxConnectionError`（设计上恰好对应“流失同步”场景），不会命中该 except，导致被污染连接的 socket 未关闭，直到上层显式 `close()`。
- `transport/async_.py` 的 `execute()` 同理只处理 `OSError/TimeoutError/IncompleteReadError`，`parse_header` 抛出的 `TdxConnectionError` 会直接浮出而不触发 `_close_unlocked()`。
- 客户端层 `_execute` 会因 `TdxConnectionError` 触发重连，所以高层面可自愈；但底层传输对象本身留下了未关闭的连接，属真实资源泄漏。
- 建议：在 `execute()`/`_heartbeat_loop` 的 except 分支把 `TdxConnectionError` 一并纳入清理。

**2. 同步心跳线程可能静默死亡**
- `transport/sync.py` 的 `_heartbeat_loop`（约 L268-274）只 `except OSError`；当连接半关或失同步时 `_recv_exact_sock`/`parse_header` 会抛 `TdxConnectionError`，导致后台 daemon 心跳线程以未捕获异常退出，socket 未回收，`_consecutive_heartbeats` 状态停滞。

### 需确认（参考研究，非本源直接核验）
- **K 线 `amount` 字段**：`commands/security_bars.py` 用 `get_volume`（TDX 4 字节浮点）解析 `amount`，而真实 K 线 amount 多为整数元；若语义不符可能量纲偏移。建议核对 pytdx 惯例。
- **`security_quotes` 未知字段**：`open_amount = unknown_3 * 100.0` 为魔法数，无来源说明；`limit_up/limit_down` 硬编码 `None` 从不填充；`_price_decimal_digits` 依赖市场/代码前缀启发式，新品类会回落默认 2 位。
- **`get_market_stat` 使用内置 `round()`（银行家舍入）**：计数类恰好 .5 时可能差 1。
- **`client.get_security_list_all` 代码前缀过滤**：`("60","68")/("00","30")` 未覆盖北交所 8xx/4xx/920 段。

### 编码/解码确认正确
- price 有符号变长整型（`get_price`）、volume 的 TDX 4 字节浮点（`get_volume`）、datetime（高位年份 + MMDD 十进制）、日期 `YYYYMMDD` 整数：均与 pytdx 一致，大小端全部小端，缩放系数（价格 /1000、周及以上 volume ×100、指数分钟 vol=NaN）均有注释且正确。
- `frame.py` 用 `IIIHH` 头部解码是文档化的兼容 shim：`zipsize/unzipsize/magic` 正确，`seq_id/method` 仅供信息参考。

---

## 二、回测引擎（backtest/engine.py + performance.py）

### 已核验
**`backtest/engine.py`**（直接通读）：
- 双路径信号生成（v1.28 向量化 vs 逐 bar）通过 `signal_path` 控制，两条路径对拍测试守护逐位一致。
- 止损/止盈/移动止损构成 OCO，`effective_stop` 固定价优先；移动止损水位在每根 bar 结束（触发检查**之后**）更新，因此**不可能在同一根创新高 bar 上触发**，与 `next_open` 成交语义一致——正确且谨慎。
- `warmup_bars` 前不调用 `next()` 不产生信号，但推进 `bar_index`，避免指标 NaN 期误信号。
- 空数据返回 `_empty_result()`，含空绩效/曲线/交易 DataFrame。
- `_find_bar_index` 对 `datetime` 兼容 `date` 列与 `dt.strftime("%Y%m%d")`。
- 缺点：`_execute_with_model` 与 `_update_strategy_position` 以收盘价估算仓位/现金，真实成交价稍后由 `OrderSimulator` 决定——文档化近似，结果以 simulator 为准，语义一致。

**`backtest/performance.py`**（直接通读，25 项指标）：
- 除零/NaN 防护成熟：`daily_ret` 过滤非有限值；`safe_prev` 前值为 0 置 NaN；`Sharpe` 分母为 0 时返回 0；`Sortino` 无负收益且均值为正时返回 999（约定值）；`Calmar` 近似。
- 单笔收益率 = `pnl/cost_basis`，无 `cost_basis` 或为 0 时置 NaN 再过滤——稳妥。
- 被拒绝交易（`rejected`）从胜率/连亏统计中剔除，避免 `reject_policy="skip"` 时污染胜率——正确。
- `avg_holding_days` 用 FIFO 配对、按 size 加权、按**真实日历日**（解析 YYYYMMDD→date 相减）而非整数差，正确规避跨月放大。组合成交表带 `symbol` 时按标的分组配对。
- `_compute_max_dd_duration` 以 `drawdown == 0` 创新高分段，取相邻新高间隔 >1 的最长段，末日未修复计到末根——合理。
- **潜在小问题**：`lose_trades_mask = pnl <= 0`（把 0 记为亏损），与“平手算亏”口径一致，但让 `win+lose` 可能不等于总笔数。属口径选择，非 bug。

> 说明：本层未发现结构性回测逻辑 bug；walkforward/validation/scoring/grading/optimizer/slippage/execution/attribution 等未逐行核验（探索受限），建议重点跟进以确认防过拟合与滑点/执行模型。

---

## 三、Web 与实时推送（web/app.py + deps.py + gateway + streamer + hub + sqlite）

### 已核验（直接通读）
- **CORS 姿态正确**：`allow_origins="*"` 但 `allow_credentials=False`，符合规范；README 已声明本机回环无鉴权定位，属有意设计。
- **SPA 静态服务**：`_resolve_web_dist_dir()` 四级探测（环境变量→PyInstaller `_MEIPASS`→仓库 `web-ui/dist`→包内 `dist`）；`SPAStaticFiles` 404 时仅对非 `/api/*` 的 GET 回退 `index.html`，不会掩盖 API 路由错误。
- **错误处理**：`TdxConnectionError→503`、`ValueError→400`、兜底 `Exception→500`。注意兜底处理器会把 `str(exc)` 暴露给客户端，本机回环可接受，若外扩会泄露内部细节。
- **SSE（quote_streamer.py）**：单轮询循环 + 每连接独立队列（maxsize 2）扇出；后端满时 `get_nowait/put_nowait` 丢旧保新（快照型数据合适）；无订阅者时休眠不轮询；交易时段 8s、空闲 60s（mock 2s）；`CancelledError` 重抛，其余错误记日志后休眠退避——稳妥。
- **WebSocket（realtime_hub.py）**：引用计数订阅集 + 无订阅即停喂；`_sync_feed` 在订阅集合变化时重启喂任务（≤0.5s 退出）；扇出满则丢旧保新。
- **SQLite（_sqlite.py）**：`_ClosingConnection` 子类在 `__exit__` 里 `close()`，修复了 `with sqlite3.connect()` 只管理事务不关闭连接的 fd 泄漏；`check_same_thread=False` 支持 FastAPI 后台线程池访问——良好的连接规范。

### 需确认 / 关注
- **`_on_event` 扇出未持锁**（realtime_hub.py 约 L228-247）：`self._subs.get(cid, set())` 无锁读取，可能在某连接并发断开时出现 `KeyError`/在变更中迭代的竞态。建议对订阅集合迭代做快照或加锁。
- **SSE 连接清理**：`subscribe()` 生成队列后，若路由未在客户端断开时调用 `unsubscribe()`，`self._queues` 会增长——需在 `routers/stream.py` 的生成器 `finally` 中确认 `unsubscribe()`（未能核验该路由）。
- **SQLite 锁**：`_sqlite.py` 未见 `PRAGMA busy_timeout`/WAL 设置，跨线程并发写（后台任务 + 请求）可能命中 `database is locked`；需确认各 store 是否在连接级设置。
- **出站 HTTP 源（sources/qq_index、ak_index 等）**：用户驱动 `code` 是否在拼 URL 前做严格校验（能否 SSRF/URL 变形）未能在路由内核验；`market_gateway.py` 的 `validate_code` 已限长 12 并剥离非字母数字 `.-`，是好的防线。

---

## 四、指标 / 公式 / 走势 / 因子 / 选股

（探索受限，多数为参考研究，建议后续独立回顾；以下为已提出且值得跟进的具体点）

- **`LONGCROSS` 可能 off-by-one**：`core.py:385` 用 `LAST(a<b, N, 1) & (a>b)`。若 `LAST` 覆盖含当前 bar 的最近 N 个元素，则“维持 N 期低于”与“本期上穿”在同一 bar 上互斥，可能永不触发。需核对 `LAST` 是否将当前 bar 计入。（探索代理提出，我未能最终读到 `LAST` 定义核实。）
- **`RET` 返回标量而非序列**：`core.py:124-127` `arr[-_as_int(N)]` 取第 N 个末尾元素（标量），与 TDX 的序列引用语义不符，公式中当序列用会广播错误。
- **`MACD` 柱状图 = `DIF - DEA` 而非 ×2**：`talib_ind.py` 与 TDX 惯例（×2）不同，属文档化差异，但按通达信图表校准的阈值会被差 2 倍。
- **`DMI` 的 `M2` 形同虚设**：`talib_ind.py` ADXR 按 `M1` 计算而忽略 `M2`，`M2` 为无效参数。
- **`BIAS` 零均值可产 `inf`**：`chinese.py` 无 `where(den>0)` 防护（对比 `CR` 有）。
- **公式 `==`/`!=` 用 `np.isclose`**：`formula.py` 采用容差相等，可能对触发奇异信号造成意外。
- **无 future 保证**：仅 DSL 层对 `REF` 负偏移设闸（`_ref_no_lookahead`）；底层 `core.REF` 与 `chinese.ICHIMOKU`（`REF(c,-shift)`）内部使用未加保护（走势中注释为仅作图用途）。
- **公式安全性**：确认安全——自定义 tokenizer + 递归下降解析器 + 白名单函数表，不走 `eval`，有递归深度上限，杜绝任意代码执行。

---

## 五、风险点汇总（建议优先处理）

| # | 位置 | 描述 | 严重度 | 状态 |
|---|---|---|---|---|
| 1 | transport sync/async `execute` | 帧头失同步抛 `TdxConnectionError` 不清理 socket | 中 | 已核验 |
| 2 | transport sync `_heartbeat_loop` | 心跳线程遇 `TdxConnectionError` 静默死亡 | 中 | 已核验 |
| 3 | web `realtime_hub._on_event` | 扇出读订阅集合未持锁，断开并发时竞态 | 中低 | 已核验 |
| 4 | web sqlite | 未见 busy_timeout/WAL，并发写可能锁库 | 中低 | 需确认 |
| 5 | web streamer 路由 | SSE 断开时未确认 unsubscribe | 中低 | 需确认 |
| 6 | ta/core `RET` | 返回标量 vs 序列 | 中 | 已核验 |
| 7 | ta/core `LONGCROSS` | 可能 off-by-one | 中 | 需核实 |
| 8 | ta/talib_ind `MACD` | 柱状图未 ×2 | 低 | 已核验（文档化） |
| 9 | ta/talib_ind `DMI` | `M2` 无效 | 低 | 已核验 |
| 10 | backtest performance | 0 盈亏计为亏损（口径） | 低 | 已核验 |

---

## 六、结论

项目整体成熟、可读、可维护；工程化防护（除零、NaN、空数据、断线重连、健康分/故障转移、OCO 止损、双路径对拍）表现出色。上表问题均不构成阻断性缺陷，多数为边界健壮性/一致性问题。

**建议下一步**：优先落实 #1/#2 传输层清理逻辑、#6 的 `RET` 语义；随后独立复核 walkforward/validation/grading 等回测副件与 factor 引擎的 IC/衰减与无前视保证，以及 `routers/stream.py` 的 SSE 清理。

> 免责声明：本次为静态人工审查，未运行回测/实时链路；未逐行核验的模块标注为“需确认”，请以实测为准。