// 回测状态管理（Pinia）。
// 持有：策略列表、当前 OHLCV、回测结果、运行状态、错误信息。

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  fetchStrategies,
  formatError,
  runBacktest,
  submitPortfolioTask,
  submitPortfolioEvaluateTask,
  submitPortfolioWalkforwardTask,
  submitOptimizeAllTask,
  submitOptimizeTask,
  submitMultiStrategyTask,
  submitMultiStrategyEvaluateTask,
  submitMultiStrategyWalkforwardTask,
  submitWalkforwardTask,
  submitEvaluateTask,
  fetchTask,
} from '../api'
import { abortError, isAbortError, sleep } from '../utils/asyncGuard'
import type {
  BacktestRequest,
  BacktestResult,
  Bar,
  Category,
  EvaluateReport,
  MultiStrategyBacktestRequest,
  PortfolioBacktestRequest,
  PortfolioResult,
  OptimizeAllBacktestRequest,
  OptimizeAllResult,
  OptimizeBacktestRequest,
  OptimizeResult,
  StrategySchema,
  WalkForwardResult,
} from '../types'

/**
 * 所有后台任务轮询共用的中止开关。
 *
 * 回测类任务最长要跑 10 分钟（600s 超时），轮询间隔 300~500ms。旧实现完全
 * 不支持中止：用户切走页面后轮询仍在后台持续打 HTTP，结束时还会把
 * running / error 写回 store —— 而 BacktestView 与其它页面共享同一个 store，
 * 于是用户会在**无关的页面**上看到一条不属于本页的报错横幅。
 *
 * 用法：页面在 `onBeforeUnmount` 里调用 `cancelAll()`。
 */
let taskControllers: AbortController[] = []

/** 领一个受 store 统一管理的中止信号（每发起一次任务轮询调用一次）。 */
function newTaskSignal(): AbortSignal {
  const ctrl = new AbortController()
  taskControllers.push(ctrl)
  return ctrl.signal
}

/** 中止全部在飞的轮询；已完成的会被忽略。 */
function cancelAll(reason = '任务已取消') {
  const pending = taskControllers
  taskControllers = []
  for (const ctrl of pending) ctrl.abort(abortError(reason))
}

/** 轮询后台任务直到终态（done 返回 result，failed/超时/结果缺失抛错）。 */
async function pollTask<T>(
  taskId: string,
  timeoutMs: number,
  what: string,
  signal?: AbortSignal,
  intervalMs = 400,
): Promise<T> {
  const start = Date.now()
  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (signal?.aborted) throw abortError(`${what}已取消`)
    // 等待段也必须可中断：否则 abort 之后仍要等满一个 interval 才退出
    const state = await fetchTask(taskId, signal)
    if (signal?.aborted) throw abortError(`${what}已取消`)
    if (state.status === 'done' && state.result) return state.result as T
    // done 但 result 为空：不能继续等（会一直空转到超时），直接报错更易排查
    if (state.status === 'done') throw new Error(`${what}结果为空`)
    if (state.status === 'failed') throw new Error(state.error || `${what}失败`)
    if (Date.now() - start > timeoutMs) throw new Error(`${what}超时（${timeoutMs / 1000}s）`)
    if (await sleep(intervalMs, signal)) throw abortError(`${what}已取消`)
  }
}

export const useBacktestStore = defineStore('backtest', () => {
  // ── 策略 ─────────────────────────────────────────────────────────────────
  const strategies = ref<StrategySchema[]>([])
  const strategiesLoaded = ref(false)

  async function loadStrategies() {
    if (strategiesLoaded.value) return
    const resp = await fetchStrategies()
    strategies.value = resp.strategies
    strategiesLoaded.value = true
  }

  // ── OHLCV 行情（前端始终持有，回测与 K 线共用） ───────────────────────────
  const ohlcv = ref<Bar[]>([])
  const barsSource = ref<string>('') // 来源描述，如 "SZ:000001 DAY×250"

  function setOhlcv(bars: Bar[], source: string) {
    ohlcv.value = bars
    barsSource.value = source
  }

  const hasBars = computed(() => ohlcv.value.length >= 2)

  // ── 回测结果 ──────────────────────────────────────────────────────────────
  const result = ref<BacktestResult | null>(null)
  const running = ref(false)
  const error = ref<string>('')

  /** 运行同步回测（内联 OHLCV）。 */
  async function run(req: Omit<BacktestRequest, 'ohlcv'>) {
    if (!hasBars.value) {
      error.value = '请先取行情数据或粘贴 OHLCV'
      return
    }
    running.value = true
    error.value = ''
    try {
      const fullReq: BacktestRequest = { ...req, ohlcv: ohlcv.value }
      result.value = await runBacktest(fullReq)
    } catch (e) {
      error.value = formatError(e)
      result.value = null
    } finally {
      running.value = false
    }
  }

  function clearResult() {
    result.value = null
    error.value = ''
  }

  // ── 附加分析：Walk-Forward / 一条龙评估（v1.27） ─────────────────────────
  const wfResult = ref<WalkForwardResult | null>(null)
  const wfRunning = ref(false)
  const wfError = ref<string>('')
  const evaluateResult = ref<EvaluateReport | null>(null)
  const evaluateRunning = ref(false)
  const evaluateError = ref<string>('')

  /** 提交 WF 样本外验证后台任务并轮询（与主回测共用同一份内联 OHLCV）。 */
  async function runWalkforward(req: Omit<BacktestRequest, 'ohlcv'>, nWindows = 7) {
    if (!hasBars.value) return
    const signal = newTaskSignal()
    wfRunning.value = true
    wfError.value = ''
    wfResult.value = null
    try {
      const { task_id } = await submitWalkforwardTask({ ...req, ohlcv: ohlcv.value }, nWindows)
      const body = await pollTask<{ walkforward: WalkForwardResult }>(
        task_id,
        180_000,
        'WF 验证',
        signal,
      )
      wfResult.value = body.walkforward
    } catch (e) {
      if (isAbortError(e)) return // 页面切走导致的取消，不记错误
      wfError.value = formatError(e)
      wfResult.value = null
    } finally {
      wfRunning.value = false
    }
  }

  /** 提交一条龙评估后台任务并轮询（回测+WF+适配性+评分+基准对比）。 */
  async function runEvaluate(req: Omit<BacktestRequest, 'ohlcv'>) {
    if (!hasBars.value) return
    const signal = newTaskSignal()
    evaluateRunning.value = true
    evaluateError.value = ''
    evaluateResult.value = null
    try {
      const { task_id } = await submitEvaluateTask({ ...req, ohlcv: ohlcv.value })
      evaluateResult.value = await pollTask<EvaluateReport>(
        task_id,
        300_000,
        '一条龙评估',
        signal,
      )
    } catch (e) {
      if (isAbortError(e)) return
      evaluateError.value = formatError(e)
      evaluateResult.value = null
    } finally {
      evaluateRunning.value = false
    }
  }

  function clearExtraAnalysis() {
    wfResult.value = null
    wfError.value = ''
    evaluateResult.value = null
    evaluateError.value = ''
  }

  // ── 组合回测（Phase 3） ───────────────────────────────────────────────────
  const portfolioResult = ref<PortfolioResult | null>(null)
  const portfolioRunning = ref(false)

  /** 提交组合回测后台任务并轮询直到完成。 */
  async function runPortfolio(req: PortfolioBacktestRequest) {
    const signal = newTaskSignal()
    portfolioRunning.value = true
    error.value = ''
    portfolioResult.value = null
    try {
      const { task_id } = await submitPortfolioTask(req)
      portfolioResult.value = await pollTask<PortfolioResult>(
        task_id,
        120_000,
        '组合回测',
        signal,
        300,
      )
    } catch (e) {
      if (isAbortError(e)) return
      error.value = formatError(e)
      portfolioResult.value = null
    } finally {
      portfolioRunning.value = false
    }
  }

  function clearPortfolio() {
    portfolioResult.value = null
    error.value = ''
  }

  // ── 组合附加分析：组合级 Walk-Forward / 一条龙评估 ────────────────────────
  const portfolioWfResult = ref<WalkForwardResult | null>(null)
  const portfolioWfRunning = ref(false)
  const portfolioWfError = ref<string>('')
  const portfolioEvaluateResult = ref<EvaluateReport | null>(null)
  const portfolioEvaluateRunning = ref(false)
  const portfolioEvaluateError = ref<string>('')

  /** 提交组合级 WF 样本外验证后台任务并轮询（N 标的 × N 窗，比单标的慢）。 */
  async function runPortfolioWalkforward(req: PortfolioBacktestRequest, nWindows = 7) {
    const signal = newTaskSignal()
    portfolioWfRunning.value = true
    portfolioWfError.value = ''
    portfolioWfResult.value = null
    try {
      const { task_id } = await submitPortfolioWalkforwardTask(req, nWindows)
      const body = await pollTask<{ walkforward: WalkForwardResult }>(
        task_id,
        300_000,
        '组合 WF 验证',
        signal,
      )
      portfolioWfResult.value = body.walkforward
    } catch (e) {
      if (isAbortError(e)) return
      portfolioWfError.value = formatError(e)
      portfolioWfResult.value = null
    } finally {
      portfolioWfRunning.value = false
    }
  }

  /** 提交组合级一条龙评估后台任务并轮询（组合回测+WF+适配性+评分+基准对比）。 */
  async function runPortfolioEvaluate(req: PortfolioBacktestRequest) {
    const signal = newTaskSignal()
    portfolioEvaluateRunning.value = true
    portfolioEvaluateError.value = ''
    portfolioEvaluateResult.value = null
    try {
      const { task_id } = await submitPortfolioEvaluateTask(req)
      portfolioEvaluateResult.value = await pollTask<EvaluateReport>(
        task_id,
        600_000,
        '组合一条龙评估',
        signal,
      )
    } catch (e) {
      if (isAbortError(e)) return
      portfolioEvaluateError.value = formatError(e)
      portfolioEvaluateResult.value = null
    } finally {
      portfolioEvaluateRunning.value = false
    }
  }

  function clearPortfolioExtraAnalysis() {
    portfolioWfResult.value = null
    portfolioWfError.value = ''
    portfolioEvaluateResult.value = null
    portfolioEvaluateError.value = ''
  }

  // ── 多策略组合回测（资金分仓） ─────────────────────────────────────────
  const multiStrategyResult = ref<PortfolioResult | null>(null)
  const multiStrategyRunning = ref(false)

  /** 提交多策略组合回测后台任务并轮询直到完成。
   * 结果结构同 PortfolioResult（复用组合页图表组件）。 */
  async function runMultiStrategy(req: MultiStrategyBacktestRequest) {
    const signal = newTaskSignal()
    multiStrategyRunning.value = true
    error.value = ''
    multiStrategyResult.value = null
    // 新一次组合回测开始时清掉上一轮的附加分析（WF/一条龙面板随主结果一起刷新）
    clearMultiStrategyExtraAnalysis()
    try {
      const { task_id } = await submitMultiStrategyTask(req)
      multiStrategyResult.value = await pollTask<PortfolioResult>(
        task_id,
        180_000,
        '多策略组合回测',
        signal,
      )
    } catch (e) {
      if (isAbortError(e)) return
      error.value = formatError(e)
      multiStrategyResult.value = null
    } finally {
      multiStrategyRunning.value = false
    }
  }

  function clearMultiStrategy() {
    multiStrategyResult.value = null
    clearMultiStrategyExtraAnalysis()
    error.value = ''
  }

  // ── 多策略组合附加分析：组合级 Walk-Forward / 一条龙评估 ──────────────────
  const multiWfResult = ref<WalkForwardResult | null>(null)
  const multiWfRunning = ref(false)
  const multiWfError = ref<string>('')
  const multiEvaluateResult = ref<EvaluateReport | null>(null)
  const multiEvaluateRunning = ref(false)
  const multiEvaluateError = ref<string>('')

  /** 提交多策略组合级 WF 样本外验证后台任务并轮询（N 槽位 × N 窗，较慢）。 */
  async function runMultiStrategyWalkforward(req: MultiStrategyBacktestRequest, nWindows = 7) {
    const signal = newTaskSignal()
    multiWfRunning.value = true
    multiWfError.value = ''
    multiWfResult.value = null
    try {
      const { task_id } = await submitMultiStrategyWalkforwardTask(req, nWindows)
      const body = await pollTask<{ walkforward: WalkForwardResult }>(
        task_id,
        300_000,
        '组合 WF 验证',
        signal,
      )
      multiWfResult.value = body.walkforward
    } catch (e) {
      if (isAbortError(e)) return
      multiWfError.value = formatError(e)
      multiWfResult.value = null
    } finally {
      multiWfRunning.value = false
    }
  }

  /** 提交多策略组合级一条龙评估后台任务并轮询（组合回测+WF+适配性+评分+基准对比）。 */
  async function runMultiStrategyEvaluate(req: MultiStrategyBacktestRequest) {
    const signal = newTaskSignal()
    multiEvaluateRunning.value = true
    multiEvaluateError.value = ''
    multiEvaluateResult.value = null
    try {
      const { task_id } = await submitMultiStrategyEvaluateTask(req)
      multiEvaluateResult.value = await pollTask<EvaluateReport>(
        task_id,
        600_000,
        '组合一条龙评估',
        signal,
      )
    } catch (e) {
      if (isAbortError(e)) return
      multiEvaluateError.value = formatError(e)
      multiEvaluateResult.value = null
    } finally {
      multiEvaluateRunning.value = false
    }
  }

  function clearMultiStrategyExtraAnalysis() {
    multiWfResult.value = null
    multiWfError.value = ''
    multiEvaluateResult.value = null
    multiEvaluateError.value = ''
  }

  // ── 参数网格寻优（Phase 4） ─────────────────────────────────────────────
  const optimizeResult = ref<OptimizeResult | null>(null)
  const optimizeRunning = ref(false)

  /** 寻优实际使用的标的上下文（取行情成功那一刻冻结）。
   * 放在 store 而非组件里，是为了在用户切走再回 /optimize 时，「查看」按钮仍能拼出正确 URL
   * —— 组件 ref 在卸载后丢失，而 store 与 optimizeResult 同生命周期保留。
   * 由 OptimizeView 在 loadBars() 成功后通过 setOptimizeContext() 写入。 */
  const optimizeContext = ref<{
    code: string
    category: Category
    startDate: string
    endDate: string
    /** SymbolPicker 市场：'A' = A 股，'HK'/'US' = 港美股（回测页据此还原市场选项）。 */
    market: string
  } | null>(null)

  function setOptimizeContext(ctx: {
    code: string
    category: Category
    startDate: string
    endDate: string
    market?: string
  }) {
    optimizeContext.value = { market: 'A', ...ctx }
  }

  /** 提交寻优后台任务并轮询直到完成。 */
  async function runOptimize(req: OptimizeBacktestRequest) {
    const signal = newTaskSignal()
    optimizeRunning.value = true
    error.value = ''
    optimizeResult.value = null
    try {
      const { task_id } = await submitOptimizeTask(req)
      optimizeResult.value = await pollTask<OptimizeResult>(task_id, 180_000, '寻优', signal)
    } catch (e) {
      if (isAbortError(e)) return
      error.value = formatError(e)
      optimizeResult.value = null
    } finally {
      optimizeRunning.value = false
    }
  }

  // ── 一键寻优所有策略（Phase 6） ─────────────────────────────────────────
  const optimizeAllResult = ref<OptimizeAllResult | null>(null)
  const optimizeAllRunning = ref(false)

  /** 提交「一键寻优所有策略」后台任务并轮询直到完成。 */
  async function runOptimizeAll(req: OptimizeAllBacktestRequest) {
    const signal = newTaskSignal()
    optimizeAllRunning.value = true
    error.value = ''
    optimizeAllResult.value = null
    try {
      const { task_id } = await submitOptimizeAllTask(req)
      // 一键寻优全策略网格点更多，放宽超时到 300s
      optimizeAllResult.value = await pollTask<OptimizeAllResult>(
        task_id,
        300_000,
        '一键寻优',
        signal,
        500,
      )
    } catch (e) {
      if (isAbortError(e)) return
      error.value = formatError(e)
      optimizeAllResult.value = null
    } finally {
      optimizeAllRunning.value = false
    }
  }

  return {
    // state
    strategies,
    strategiesLoaded,
    ohlcv,
    barsSource,
    result,
    running,
    error,
    portfolioResult,
    portfolioRunning,
    portfolioWfResult,
    portfolioWfRunning,
    portfolioWfError,
    portfolioEvaluateResult,
    portfolioEvaluateRunning,
    portfolioEvaluateError,
    multiStrategyResult,
    multiStrategyRunning,
    multiWfResult,
    multiWfRunning,
    multiWfError,
    multiEvaluateResult,
    multiEvaluateRunning,
    multiEvaluateError,
    optimizeResult,
    optimizeRunning,
    optimizeContext,
    optimizeAllResult,
    optimizeAllRunning,
    wfResult,
    wfRunning,
    wfError,
    evaluateResult,
    evaluateRunning,
    evaluateError,
    // getters
    hasBars,
    // actions
    loadStrategies,
    setOhlcv,
    run,
    clearResult,
    runWalkforward,
    runEvaluate,
    clearExtraAnalysis,
    runPortfolio,
    clearPortfolio,
    runPortfolioWalkforward,
    runPortfolioEvaluate,
    clearPortfolioExtraAnalysis,
    runMultiStrategy,
    clearMultiStrategy,
    runMultiStrategyWalkforward,
    runMultiStrategyEvaluate,
    clearMultiStrategyExtraAnalysis,
    runOptimize,
    runOptimizeAll,
    setOptimizeContext,
    // 中止：页面 onBeforeUnmount 调用，取消全部在飞的任务轮询
    cancelAll,
  }
})
