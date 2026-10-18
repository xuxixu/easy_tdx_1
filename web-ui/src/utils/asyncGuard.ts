/**
 * 异步竞态守卫工具（序号守卫 + 中止原语）。
 *
 * ## 为什么需要序号守卫
 *
 * 行情面板里「切换标的 / 切换周期 / 改分时天数」都会重新发起请求，而这些
 * 请求的耗时差异极大：日K 要按页翻（单页 800 根，两年数据可能翻多页）、
 * 月K 通常一页就返回；外盘还走另一套扩展栈，延迟波动更大。慢的**旧**请求
 * 晚于快的**新**请求返回时，会把旧数据写进响应式状态 —— 页面标题已经是 B，
 * 图表画的却还是 A，且不报错。
 *
 * ## 常见错误写法（本项目踩过两次）
 *
 * ```ts
 * let seq = 0
 * async function loadCharts() {
 *   const my = ++seq
 *   await loadDaily()        // ← 内部已经 dailyBars.value = ... 了
 *   if (my !== seq) return   // ← 这行只能阻止后续步骤，撤不回已写入的数据
 * }
 * ```
 *
 * 守卫必须**下传**到真正发起请求并写入状态的函数，在每个 `await` 之后、
 * 每次赋值之前比对。只在外层 `await` 之后检查是无效的。
 *
 * 另一个坑：`watch(x, loadFn)` 会把 `(newVal, oldVal)` 作为前两个实参传给
 * `loadFn`，若 `loadFn` 的首参是序号就会被污染。必须写成
 * `watch(x, () => void loadFn())`。
 */

/** 序号守卫实例。 */
export interface SeqGuard {
  /**
   * 领取一个新序号，此前发出的所有序号立即失效。
   * 每次发起**新一轮**请求时调用一次。
   */
  next(): number
  /**
   * 该序号是否已过期。`true` 表示结果应丢弃、不得写入状态。
   * 每个 `await` 之后、每次赋值之前都要问一次。
   */
  stale(my: number): boolean
  /** 当前最新序号（调试用，业务代码极少需要）。 */
  current(): number
}

/**
 * 创建一个独立的序号守卫。
 *
 * 一个守卫对应**一组互相竞争的请求**（例如同一个图表的日K/分时/分钟K）。
 * 互不相关的两组数据应当各用一个守卫，否则切换 A 会误伤 B 的正常返回。
 */
export function createSeqGuard(): SeqGuard {
  let seq = 0
  return {
    next: () => ++seq,
    stale: (my: number) => my !== seq,
    current: () => seq,
  }
}

/**
 * 构造与 `fetch` 中止语义一致的 AbortError。
 *
 * 调用方可以按 `err.name === 'AbortError'` 识别并静默处理（用户主动取消
 * 不该弹红条）。消息带场景名，便于在日志里区分是哪一路轮询被取消。
 */
export function abortError(message = '请求已取消'): DOMException {
  return new DOMException(message, 'AbortError')
}

/** 判断错误是否为用户/组件主动中止（这类错误应静默，不要冒泡成错误提示）。 */
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

/** 把「普通错误」以外的中止错误静默掉：中止返回 null，其它原样抛出。 */
export function swallowAbort(err: unknown): null {
  if (isAbortError(err)) return null
  throw err
}

/**
 * 可被中止的 sleep。轮询循环的等待段必须可中断，否则调用方 abort 之后
 * 仍要等满整个 interval 才响应。
 *
 * @returns 正常等到返回 false；期间被 abort 返回 true（调用方应立即退出）。
 */
export function sleep(ms: number, signal?: AbortSignal): Promise<boolean> {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve(true)
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve(false)
    }, ms)
    function onAbort() {
      clearTimeout(timer)
      resolve(true)
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}
