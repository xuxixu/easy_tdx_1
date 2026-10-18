# 全仓代码审查报告（第三轮）

- 日期：2026-10-18
- 范围：后端 287 个 Python 模块 + 前端 Vue3（Vite）全量
- 版本：`easy-tdx` 1.32.6（未发布段）

## 一、审查方法

「静态扫描（并行子代理）+ 探针实证 + 修复 + 回归测试」。

子代理的扫描结论只作为线索，每条高/中级结论都用临时探针跑出确定证据后才采信。
这一步是必要的：本轮确实筛掉过误报（探针初版把断言写成循环论证——用 `.iloc`
取到的值反查 `.iloc` 位置，恒等——差点判成「无问题」）。

## 二、质量门禁（全部通过）

| 门禁 | 结果 |
|------|------|
| `pytest tests/unit` | 2030 → **2057 passed**（两轮共新增 27 项） |
| `ruff check src tests` | All checks passed |
| `ruff format --check` | 420 files already formatted |
| `mypy src/easy_tdx`（strict） | 287 源文件零错误 |
| `vue-tsc -b --noEmit` | 零错误 |
| 前端 `npm test`（node:test） | 42 → **50 passed** |
| 前端 `npm run build` | 成功（3.78s） |
| `smoke_all --offline` | 8 通过 / 0 失败 / 5 跳过（环境） |
| Web API（mock 模式） | 9 端点全 200 |

功能层面是正常的：所有离线命令、K线/指标/因子/回测链路、Web REST 端点均可用。
下方缺陷都是「特定条件下算错/显示错」，不会让程序崩溃，因此单测全绿也照样存在。

## 三、已实证并修复（4 项）

### 1. 降仓买入超支 → 现金为负（高）

`src/easy_tdx/backtest/orders.py` `reject_policy="reduce"` 分支用
`int(available_cash / price / 100) * 100` 计算可买手数，只预留了**最低佣金**，
未预留按比例佣金。整手取整后的「成交额 + 实际佣金」会超出可用现金。

实证：cash=350000、price=1、signal.size=500000 → 成交 349900 股、佣金 104.97，
结算后现金 **-4.97 元**。`reject_policy` 默认即 `"reduce"`，默认配置下可触发。

修复：改按 `price * (1 + commission)` 折算，与 `_calculate_buy_size` 同口径（同场景结余 +95.06）。

### 2. 成交落在错误的 K 线上（高）

`src/easy_tdx/backtest/engine.py` `_find_bar_index` 返回 `(dt_col == dt).idxmax()`
——这是 index **标签**；而 `ExecutionModel` 一律按**位置**取数（`df["open"].iloc[bar_idx]`）。
当 df 的 index 不是 `RangeIndex`（调用方做过 `dropna` / 切片 / 拼接时很常见），两者不等价。

实证：`df.iloc[5:]` 后在位置 10 产生信号，engine 传入 `bar_idx=15`，
`.iloc[15]` 取到 20240121 —— **错位 5 根 bar**，应在 20240116 成交。
影响 TWAP / VWAP / LimitExecution 分支。

修复：用 `df.index.get_loc()` 统一换算成位置索引，与 `PortfolioTracker`
的 datetime→位置 映射同口径。

> 注：`OrderSimulator` 一侧上一轮已修过同类问题（见 `TestNonContinuousIndex`），
> 本次补齐的是 `execution_model` 分支——同项目同类坑的第二处漏网。

### 3. 滑点不进 pnl，Σpnl 与净值变动对不上账（中）

`_compute_pnls` 中持仓成本基数与 `trade.pnl` 只用 `price + commission`，漏掉 `slippage`；
而现金/净值侧是扣了滑点的。

实证（`slippage=0.2%`）：净值变动 3610，Σpnl **3650**，差 40 元；
`slippage=0.5%` 差 100 元。且三档滑点下 Σpnl **恒为 3650 不变** ——
胜率 / 盈亏比 / 平均盈亏 / SQN 系统性偏乐观，「成交明细 pnl 求和 = 净值变动」
这个最基本的对账不成立。

修复：滑点计入持仓成本基数与卖出 pnl。三档滑点现已逐分对账。

### 4. 一键寻优费率口径与其余端点不一致（高）

`OptimizeAllBacktestRequest` 缺 `min_commission` / `stamp_tax` / `auto_fees`；
`_optimize_one_strategy` 也不接收这两项，恒落默认 `5.0` / `0.001`，
且 `_run_optimize_all` **未调用** `_resolve_effective_fees()`。

后果：ETF / 可转债在 `/backtest/optimize-all` 下仍按股票 0.1% 收印花税；
同一标的、同一策略在「一键寻优」与「单策略寻优」下算出的收益对不上；
用户即使想覆盖也无处可填。

修复：补齐 schema 三个字段，解析后透传（含买入持有基准）。

### 5. 前端序号守卫形同虚设（高）

`web-ui/src/components/StockDialog.vue`：`loadDaily()` / `loadMinute()`
内部各自直接写 `dailyBars` / `minutePoints`，而 `loadCharts` 的
`if (my !== chartSeq) return` 只在这两个 `await` **之后**才检查，撤不回已写入的数据。
快速切换标的时会出现「日K 属于 A、分时属于 B」，且不报错。
同文件 `loadIntra` 本就是正确范式（赋值前比对），属漏改。

修复：序号下传至两个加载函数，在每个 `await` 之后、每次赋值之前比对。
顺带修掉 `watch(minuteDays, loadMinute)` 会把 `(newVal, oldVal)` 误当 seq 传入的隐患。

## 四、遗留问题处理结果（本轮已全部修复）

> 以下 18 项在第二轮修复中全部处理完毕，逐项细节见 CHANGELOG「遗留问题清零」段。
> 保留原始位置索引，便于回溯当时的问题代码。

### 中（12 项，全部已修）

| 位置 | 问题 | 处理方式 |
|------|------|----------|
| `web/overseas_rank.py:152` | 翻页无 offset / 迭代上限；服务端忽略 `start` 时永不退出 + 内存无界增长 | 按「市场总数 / 页大小 + 2」定上限（总数未知时 400 页兜底）；补 `offset >= total` 即停；触顶记 warning |
| `web/symbol_index.py:141` | `connect()` 抛异常时 `client_to_close` 仍为 `None` → 每次冷路径漏一条 socket | 先登记 `client_to_close` 再 `connect()` |
| `backtest/rotation.py:261` | 资金/整手不足时挂单静默 `continue`，订单消失 | 顺延到次日（与停牌同语义），连续 5 日不成则放弃并 warning |
| `_reconnect.py:344` | 心跳 `except CancelledError: break` 吞掉取消 | 改 `raise`，与 `sentiment_sampler` / `quote_streamer` 一致 |
| `BoardDialog.vue:115` | 守卫只挡住 `loading`，`Promise.all` 两个请求都无守卫 | 守卫下传到 `loadMinute` / `loadDaily`，赋值前比对 |
| `AShareKlinePanel.vue:74` | `loadBars` 无守卫；周期 chip 无 `disabled` | 加守卫 + chip `:disabled="barsLoading"` + `applyCode` 补 catch |
| `OverseasDashboard.vue:190` | 分钟K / 日K 无守卫 | 加守卫；指数条迷你分时加 `alive` 断路 |
| `IndexCalendarView.vue:43` | `loadIndex` 无守卫，chip 与重试无 disabled | 加守卫（命中缓存的早返回也领新序号）+ 两处 `:disabled` |
| `SentimentView.vue:90` | `load` / `loadEx` 无守卫，A股↔外盘并发 | 两模式共用守卫 + `alive` + `render()` 守卫 |
| `CustomList.vue:141` | 预览无守卫，`fetchKlineOption` 支持 signal 却没传 | 加守卫 + `AbortController`，`disposePreview` 里 abort |
| `stores/backtest.ts:41` | `pollTask` 与 4 处内联轮询不支持 `AbortSignal` | 收敛为单个 `pollTask` + `newTaskSignal()` / `cancelAll()`；三个视图在卸载时调用 |
| `api.ts:995` | `runLlmChatWithPolling` 的 signal 只覆盖 sleep 边界 | signal 下发给两次 fetch，等待段改可中断 |

### 低（6 项，全部已修）

| 位置 | 问题 | 处理方式 |
|------|------|----------|
| `engine.py:114` / `orders.py` | docstring 写 `'reject'`，实现只认 `reduce`/`skip`，传错值产生**超额买入** | docstring 改正 + `OrderSimulator.__post_init__` 对非法值 `ValueError` 快失败 |
| `rotation.py:420` | `cost_basis` 用卖出金额，与主引擎口径不可比 | 改为持仓成本 `pos.cost * pos.shares` |
| `quotes.ts:17` | Map 只增不删；SSE 退避无抖动无上限 | 5000 条上限按插入顺序淘汰；退避加抖动 + 20 次上限；新增 `retrying` 状态；页面可见时恢复 |
| `WatchlistView.vue:53` | `fillMissingNames` 无 catch 且串行 | 4 路并发 + 单条失败跳过 + `void` 调用避免污染页面错误态 |
| `CcpmView` / `AiInterpretModal` / `OverseasDashboard` | 卸载后仍写状态 | 均补 `alive` 标志与（`CcpmView`）`onBeforeUnmount` |
| bundle 1.18 MB 未拆包 | 首屏等全部代码解析 | 路由级 `() => import()`（仅首屏静态）→ 主 chunk **93.5 kB**（gzip 30 kB）；echarts 独立 664 kB

## 五、已排查确认无问题（不必再查）

- 协议层：`_recv_exact_sock` 用 `while len(buf) < n` 正确补读短读；`parse_header` 校验 magic；`execute` 在 `OSError` / `TdxConnectionError` 后一律作废连接；async 版用 `readexactly` + `wait_for` 超时。
- SQLite：`_sqlite.py` 用 `_ClosingConnection` 保证 `with` 退出即 close；`app_settings_store` / `task_store` 的裸 `sqlite3.connect` 均配 `try/finally close`。
- `task_store` 的 `_write_lock` 与 `_init_lock` **无死锁**（初始化路径只取 `_init_lock`，反向路径不存在）。
- 安全：全仓无 `subprocess` / `shell=True`；`strategy_store` 的 f-string 只拼白名单字段名、值走占位符；`push.py` 的 `_validate_url` 限 scheme + 拦元数据/回环地址 + 防 302 绕过；无路径穿越、无 SSRF。
- pandas：无 `fillna(method=)`、无 `np.bool`、无链式赋值。

## 六、后续可选优化（非缺陷，供参考）

1. **新页面一律复用 `src/utils/asyncGuard.ts`**：`createSeqGuard()` 处理竞态、`sleep(ms, signal)` 处理可中断等待、`isAbortError()` 静默主动取消。守卫的正确用法是**下传序号**、在每个 `await` 之后、每次赋值之前比对。
2. **echarts 若还需瘦身**：`HeatmapChart` 只在热点相关性 / 寻优热力图用到，可拆到独立模块按需注册（首屏用的是 `RadarChart`，不能一起拆）。预计再省 20-40 kB。
3. **`_MAX_PENDING_RETRIES = 5`** 是经验值，若某些低流动性池子需要更长的挂单耐心，可考虑提到构造函数参数。
4. **建议加 pre-commit 钩子**跑 `ruff check` / `ruff format --check` / `mypy`，避免格式问题在提交后才被发现。
5. **CI 建议把前端 `npm test` 与 `vue-tsc` 也纳入**，本次修改中有多处纯前端竞态问题只有类型检查与单测能兜住。
