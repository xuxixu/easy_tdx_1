// 实时行情 SSE 状态（Pinia，全局单连接）。
// App.vue 挂载时 connect()，所有视图共享同一份 quotes 快照。
// 断线指数退避重连（上限 30s），状态徽标挂在侧边栏底部。

import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'

import type { SecurityQuote, SseMessage } from '../types'

/**
 * - `connecting` 首次建连
 * - `open`       已连上
 * - `retrying`   已断线、正在退避等待重连（徽标应与 `closed` 区分开：
 *                用户需要知道「服务挂了」和「正在自动重连」是两回事）
 * - `closed`     已断开且不再自动重连
 */
export type SseStatus = 'connecting' | 'open' | 'retrying' | 'closed'

const STREAM_URL = '/api/v1/stream/quotes'
const MAX_RETRY_DELAY = 30_000

/**
 * 连续失败上限：约 10 分钟后退避到达 30s 并累积约 20 次，此后停止自动重连。
 * 旧实现无上限：后端长时间不可用时，**每个标签页**都每 30s 建一条 SSE 永不
 * 停止，多开几个页就是持续的无意义请求。页面重新可见时自动恢复。
 */
const MAX_RETRY_ATTEMPTS = 20

/**
 * 行情快照缓存上限。`quotes` 只增不删（全市场订阅/长时间轮看会持续膨胀），
 * 超出后按 Map 的插入顺序淘汰最早写入的条目。
 */
const MAX_QUOTES = 5_000

export const useQuoteStore = defineStore('quotes', () => {
  /** symbol（SH600000）→ 最新行情快照。 */
  const quotes = reactive(new Map<string, SecurityQuote>())
  const status = ref<SseStatus>('closed')
  /** 是否已用尽重连次数（徽标可据此提示用户手动刷新）。 */
  const retryExhausted = ref(false)
  const lastTs = ref('')
  let es: EventSource | null = null
  let retryTimer: number | null = null
  let retryCount = 0

  const quoteCount = computed(() => quotes.size)

  /** 超过上限时按插入顺序淘汰最早的条目，避免 Map 无界增长。 */
  function evictQuotes() {
    if (quotes.size <= MAX_QUOTES) return
    const excess = quotes.size - MAX_QUOTES
    let removed = 0
    for (const key of quotes.keys()) {
      if (removed >= excess) break
      quotes.delete(key)
      removed += 1
    }
  }

  function handleMsg(ev: MessageEvent<string>) {
    try {
      const msg = JSON.parse(ev.data) as SseMessage
      if (msg.type === 'quotes_updated' && msg.quotes) {
        for (const q of msg.quotes) quotes.set(q.symbol, q)
        evictQuotes()
        if (msg.ts) lastTs.value = msg.ts
      }
      status.value = 'open'
      retryCount = 0
      retryExhausted.value = false
    } catch {
      // 非 JSON 帧（服务端注释/心跳），忽略
    }
  }

  function connect() {
    if (es) return
    status.value = 'connecting'
    es = new EventSource(STREAM_URL)
    es.onmessage = handleMsg
    es.onopen = () => {
      status.value = 'open'
      retryCount = 0
      retryExhausted.value = false
    }
    es.onerror = () => {
      // EventSource 断开后进入 readyState=CONNECTING 自行重试；但若服务已停，
      // 会无限静默重试——这里手动接管：关闭后按退避重连，同时更新状态徽标。
      close(false)
      retryCount += 1
      if (retryCount > MAX_RETRY_ATTEMPTS) {
        status.value = 'closed'
        retryExhausted.value = true
        return
      }
      // 指数退避 + 抖动：多标签页同时掉线时错开重连，避免同一秒打爆后端
      const base = Math.min(1000 * 2 ** (retryCount - 1), MAX_RETRY_DELAY)
      const delay = Math.round(base * (0.5 + Math.random() * 0.5))
      status.value = 'retrying'
      retryTimer = window.setTimeout(connect, delay)
    }
  }

  function close(markClosed = true) {
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
    es?.close()
    es = null
    if (markClosed) status.value = 'closed'
  }

  /** 取单只行情（无数据时返回 undefined）。 */
  function getQuote(symbol: string): SecurityQuote | undefined {
    return quotes.get(symbol)
  }

  /**
   * 用一次 REST 快照补种行情，只填 SSE 还没有的 symbol。
   *
   * SSE 空闲期（休市）推送间隔 60s（quote_streamer.idle_interval），页面刚打开会
   * 一直显示 “—”。指数条这类一次性展示的报价不该等一整轮推送，故在挂载时主动
   * 拉一次兜底；已有（可能更新鲜）的 SSE 值不覆盖。
   */
  function seedQuotes(list: SecurityQuote[]) {
    for (const q of list) {
      if (!q.symbol) continue
      if (!quotes.has(q.symbol)) quotes.set(q.symbol, q)
    }
  }

  // 退避用尽后不再自动重连（避免永久打空请求）；页面重新可见时恢复一次。
  // setup store 只执行一次，故该监听只注册一次。
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && retryExhausted.value) {
        retryCount = 0
        retryExhausted.value = false
        connect()
      }
    })
  }

  return {
    quotes,
    status,
    retryExhausted,
    lastTs,
    quoteCount,
    connect,
    close,
    getQuote,
    seedQuotes,
  }
})
