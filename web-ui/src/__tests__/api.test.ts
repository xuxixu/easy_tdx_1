/**
 * api.ts 行为自检（Node 内置 test runner，fetch 打桩，无 DOM 依赖）。
 *
 * 运行：node --test src/__tests__/api.test.ts
 *
 * 覆盖：
 * 1. fetchRankList 的 market 归一化——北交所(market=2)必须映射为 'BJ'
 *    （与 fetchBoardMembers 同口径；错标 'SZ' 会导致榜单点开个股用错市场拉行情）。
 * 1b. fetchBoardMembers 的扩展板块归一化——美股板块成员(market=74)必须映射为
 *    'US'、港股(31)为 'HK'，不能按 A 股口径全标 'SZ'（否则点开成分股报
 *    "A股代码应为6位数字"）。
 * 2. runLlmChatWithPolling 的可选 AbortSignal——signal 中止后循环立即以
 *    AbortError 退出，不再继续轮询（弹窗卸载清理依赖此行为）。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'

import { deleteTask, fetchBoardMembers, fetchKlineOption, fetchRankList, runLlmChatWithPolling, validateFormula } from '../api.ts'
import type { TaskState } from '../types.ts'

/** 临时替换 globalThis.fetch，返回可编程响应序列。 */
function stubFetch(handler: (url: string, init?: RequestInit) => unknown): {
  calls: string[]
  restore: () => void
} {
  const calls: string[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input instanceof URL ? input : input)
    calls.push(url)
    const body = handler(url, init)
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof fetch
  return {
    calls,
    restore: () => {
      globalThis.fetch = original
    },
  }
}

// ── 1. fetchRankList 北交所映射 ───────────────────────────────────────────────

test('fetchRankList: market=2（北交所）归一化为 BJ', async () => {
  const stub = stubFetch(() => ({
    data: [
      { close: 10.5, pre_close: 9.55, market: 2, code: '920002', name: '测试北交所' },
      { close: 8.0, pre_close: 8.8, market: 0, code: '000001', name: '平安银行' },
      { close: 20.0, pre_close: 19.0, market: 1, code: '600519', name: '贵州茅台' },
    ],
  }))
  try {
    const rows = await fetchRankList('DESC', 3)
    assert.equal(rows[0].market, 'BJ', 'market=2 应映射为 BJ（旧码错标 SZ）')
    assert.equal(rows[1].market, 'SZ', 'market=0 应映射为 SZ')
    assert.equal(rows[2].market, 'SH', 'market=1 应映射为 SH')
    // 顺带核对涨跌幅口径：close/pre-1
    assert.ok(Math.abs((rows[0].change_pct ?? 0) - ((10.5 / 9.55 - 1) * 100)) < 1e-6)
  } finally {
    stub.restore()
  }
})

// ── 1b. fetchBoardMembers 扩展板块映射 ─────────────────────────────────────────

test('fetchBoardMembers: 美股/港股板块成员按扩展口径归一，不误标 SZ', async () => {
  const stub = stubFetch(() => ({
    data: [
      { close: 15.04, pre_close: 13.27, market: 74, code: 'PHOS', name: 'First Phosphate' },
    ],
  }))
  try {
    const us = await fetchBoardMembers('US0003', 10)
    assert.equal(us[0].market, 'US', 'market=74 应映射为 US（旧码错标 SZ）')
  } finally {
    stub.restore()
  }
  const stub2 = stubFetch(() => ({
    data: [{ close: 10, pre_close: 9, market: 31, code: '00700', name: '腾讯控股' }],
  }))
  try {
    const hk = await fetchBoardMembers('HK0100', 10)
    assert.equal(hk[0].market, 'HK', 'market=31 应映射为 HK')
  } finally {
    stub2.restore()
  }
  const stub3 = stubFetch(() => ({
    data: [{ close: 10, pre_close: 9, market: 1, code: '600519', name: '贵州茅台' }],
  }))
  try {
    const ashare = await fetchBoardMembers('881001', 10)
    assert.equal(ashare[0].market, 'SH', 'A 股板块保持原口径：market=1 → SH')
  } finally {
    stub3.restore()
  }
})

// ── 1c. deleteTask 与自定义类型接口 ────────────────────────────────────────────

test('deleteTask: DELETE 方法打到 /backtest/tasks/{id}', async () => {
  const seen: Array<{ url: string; method: string }> = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push({ url: String(input instanceof URL ? input : input), method: init?.method ?? 'GET' })
    return new Response(JSON.stringify({ ok: true, task_id: 'abc' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof fetch
  try {
    const r = await deleteTask('abc')
    assert.equal(r.ok, true)
    assert.equal(seen.length, 1)
    assert.ok(seen[0].url.includes('/backtest/tasks/abc'))
    assert.equal(seen[0].method, 'DELETE')
  } finally {
    globalThis.fetch = original
  }
})

// ── 2. runLlmChatWithPolling 的 AbortSignal ──────────────────────────────────

const runningState: TaskState = { status: 'running' } as unknown as TaskState

test('runLlmChatWithPolling: signal 中止后立即退出并抛 AbortError', async () => {
  const stub = stubFetch((url) => {
    if (url.includes('/llm/chat/async')) return { task_id: 't1' }
    return runningState
  })
  try {
    const ctrl = new AbortController()
    const promise = runLlmChatWithPolling(
      'ping',
      null,
      () => ctrl.abort(), // 第一次轮询即中止
      5, // intervalMs
      30_000, // timeoutMs（远大于中止所需时间，确保超时兜底不先触发）
      ctrl.signal,
    )
    await assert.rejects(promise, (e: unknown) => (e as Error).name === 'AbortError')
    // 中止后不应继续轮询：任务查询次数应极少（≤3）
    const polls = stub.calls.filter((u) => u.includes('/llm/chat/tasks/')).length
    assert.ok(polls <= 3, `中止后应停止轮询，实际轮询 ${polls} 次`)
  } finally {
    stub.restore()
  }
})

test('runLlmChatWithPolling: 未中止时正常返回 done', async () => {
  let polls = 0
  const stub = stubFetch((url) => {
    if (url.includes('/llm/chat/async')) return { task_id: 't2' }
    polls += 1
    if (polls < 3) return runningState
    return { status: 'done', result: { reply: 'ok', model: 'm', provider: 'p' } }
  })
  try {
    const state = await runLlmChatWithPolling('ping', null, undefined, 1, 30_000)
    assert.equal(state.status, 'done')
    assert.equal((state.result as { reply?: string } | null)?.reply, 'ok')
  } finally {
    stub.restore()
  }
})

// ── 3. 通达信公式 ────────────────────────────────────────────────────────────

test('validateFormula: POST /formula/validate，透传 text', async () => {
  let seenBody = ''
  const original = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seenBody = String(init?.body ?? '')
    return new Response(
      JSON.stringify({ ok: true, signals: ['买入'], values: ['均线5'], error: null }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )
  }) as typeof fetch
  try {
    const r = await validateFormula('买入: CROSS(MA(C,5), MA(C,20)); 均线5: MA(C,5);')
    assert.equal(r.ok, true)
    assert.deepEqual(r.signals, ['买入'])
    assert.deepEqual(r.values, ['均线5'])
    const body = JSON.parse(seenBody) as { text?: string }
    assert.ok(body.text?.includes('CROSS'))
  } finally {
    globalThis.fetch = original
  }
})

test('fetchKlineOption: POST /chart/kline-option，K 线 + 条目 + 轴色', async () => {
  let seen: { url: string; body: string } | null = null
  const original = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen = { url: String(input instanceof URL ? input : input), body: String(init?.body ?? '') }
    return new Response(
      JSON.stringify({ option: { backgroundColor: 'transparent', series: [] }, count: 2 }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )
  }) as typeof fetch
  try {
    const r = await fetchKlineOption({
      bars: [
        { datetime: '2024-01-01', open: 10, high: 11, low: 9, close: 10.5, vol: 100 },
        { datetime: '2024-01-02', open: 10.5, high: 12, low: 10, close: 11.5, vol: 200 },
      ],
      items: [
        { id: 'ma', formula: 'MA5: MA(C,5);', pane: 'main', display: { MA5: 'MA5' }, colors: { MA5: '#f0a020' }, dashed: [], bar_cols: [] },
      ],
      axis_color: '#2a2e3a',
    })
    assert.equal(r.count, 2)
    assert.equal((r.option.backgroundColor as string), 'transparent')
    assert.ok(seen?.url.includes('/chart/kline-option'))
    const body = JSON.parse(seen?.body ?? '{}') as Record<string, unknown>
    assert.equal((body.bars as unknown[]).length, 2)
    assert.equal(body['axis_color'], '#2a2e3a')
  } finally {
    globalThis.fetch = original
  }
})
