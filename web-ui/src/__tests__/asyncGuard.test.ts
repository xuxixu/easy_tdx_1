/**
 * 异步竞态守卫（asyncGuard）行为自检（Node 内置 test runner）。
 *
 * 运行：node --test src/__tests__/asyncGuard.test.ts
 *
 * 覆盖：
 * 1. createSeqGuard：next 递增、只有最新序号不算过期。
 * 2. 典型竞态场景：慢的旧请求晚于新请求返回时必须被判为过期（这是本项目
 *    在 StockDialog / BoardDialog / AShareKlinePanel 等处反复踩的坑）。
 * 3. 两组互不相关的请求用两个守卫，切换 A 不会误伤 B。
 * 4. sleep 可被 AbortSignal 立即唤醒（轮询的等待段必须可中断）。
 * 5. abortError / isAbortError 的协作。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'

// 显式 .ts 扩展名：Node 的类型剥离（node --test）不做无扩展名解析
import { abortError, createSeqGuard, isAbortError, sleep } from '../utils/asyncGuard.ts'

test('createSeqGuard：next 递增，只有最新序号不过期', () => {
  const guard = createSeqGuard()
  const first = guard.next()
  assert.equal(guard.stale(first), false)

  const second = guard.next()
  assert.equal(guard.stale(first), true) // 旧序号立即失效
  assert.equal(guard.stale(second), false)

  const third = guard.next()
  assert.equal(guard.stale(second), true)
  assert.equal(guard.stale(third), false)
  assert.equal(guard.current(), third)
})

test('序号守卫：慢的旧请求晚返回时被判定为过期', async () => {
  // 模拟：先发 A（慢 20ms）再发 B（快 1ms），B 先返回、A 后返回。
  // 旧实现（只在外层 await 后比对）会让 A 覆盖 B；正确实现应在写入前丢弃 A。
  const guard = createSeqGuard()
  const written: string[] = []

  async function load(name: string, delayMs: number) {
    const my = guard.next()
    await sleep(delayMs)
    if (guard.stale(my)) return // 守卫：过期即丢弃，不写状态
    written.push(name)
  }

  await Promise.all([load('A-old', 20), load('B-new', 1)])
  assert.deepEqual(written, ['B-new'], '旧请求不得覆盖新请求的结果')
})

test('序号守卫：两组不相关请求应各用一个守卫，互不误伤', async () => {
  const chartGuard = createSeqGuard()
  const memberGuard = createSeqGuard()

  // 切换板块（chart 组）不应作废成分股列表（member 组）的在飞请求
  const chartSeq = chartGuard.next()
  const memberSeq = memberGuard.next()
  chartGuard.next() // 用户又切了一次板块

  assert.equal(chartGuard.stale(chartSeq), true, '图表旧请求应作废')
  assert.equal(memberGuard.stale(memberSeq), false, '成分股请求不应被波及')
})

test('sleep：正常等待返回 false', async () => {
  const aborted = await sleep(5)
  assert.equal(aborted, false)
})

test('sleep：被 abort 时立即返回 true（不空等满 interval）', async () => {
  const ctrl = new AbortController()
  const started = Date.now()
  const p = sleep(5_000, ctrl.signal)
  ctrl.abort()
  const aborted = await p
  const elapsed = Date.now() - started
  assert.equal(aborted, true)
  assert.ok(elapsed < 1_000, `应在中止后立即返回，实际耗时 ${elapsed}ms`)
})

test('sleep：signal 已处于 aborted 状态时同步返回 true', async () => {
  const ctrl = new AbortController()
  ctrl.abort()
  assert.equal(await sleep(5_000, ctrl.signal), true)
})

test('abortError / isAbortError：中止错误可被识别并静默', () => {
  const err = abortError('已取消')
  assert.equal(err.name, 'AbortError')
  assert.equal(isAbortError(err), true)

  // 普通业务错误不得被当成中止吞掉
  assert.equal(isAbortError(new Error('boom')), false)
  assert.equal(isAbortError(null), false)
  assert.equal(isAbortError('AbortError'), false)
})

test('abortError：AbortController.abort 触发的 fetch 错误也按 name 识别', () => {
  // fetch 被 abort 时抛的同样是 DOMException(name=AbortError)
  const ctrl = new AbortController()
  ctrl.abort()
  assert.equal(isAbortError(ctrl.signal.reason), true)
})
