/**
 * 指数指标配置（indexIndicators）行为自检（Node 内置 test runner，localStorage 打桩）。
 *
 * 运行：node --test src/__tests__/indexIndicators.test.ts
 *
 * 覆盖：
 * 1. 无配置时返回各市场默认指数（主流口径）。
 * 2. 自定义配置生效：新增/停用/排序后 enabledIndices 只返回启用项。
 * 3. 非法配置（缺 code、非法 overlay、类型不符）被清洗，损坏 JSON 回默认。
 * 4. 空列表回退默认（指数条不会全空）。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'

/** localStorage 最小打桩（模块读配置走它）。 */
class MemoryStorage {
  private map = new Map<string, string>()
  getItem(k: string): string | null {
    return this.map.has(k) ? (this.map.get(k) as string) : null
  }
  setItem(k: string, v: string): void {
    this.map.set(k, String(v))
  }
  removeItem(k: string): void {
    this.map.delete(k)
  }
  clear(): void {
    this.map.clear()
  }
}

const g = globalThis as unknown as { localStorage?: MemoryStorage }
g.localStorage = new MemoryStorage()

const mod = await import('../indexIndicators.ts')

test('默认：各市场均有主流指数', () => {
  const def = mod.defaultIndexIndicators()
  for (const k of ['SH', 'SZ', 'BJ', 'HK', 'US']) {
    assert.ok(def[k].length > 0, `${k} 默认指数为空`)
  }
  // 美股用真指数
  const usCodes = def.US.map((x) => x.code)
  for (const c of ['DJI', 'IXIC', 'SPX', 'NDX']) {
    assert.ok(usCodes.includes(c), `美股默认应含 ${c}`)
  }
  // 港股三指数
  assert.deepEqual(def.HK.map((x) => x.code), ['HSI', 'HSCEI', 'HSTECH'])
})

test('无配置时 enabledIndices 返回默认（上限 6）', () => {
  const list = mod.enabledIndices('SH')
  assert.ok(list.length > 0)
  assert.ok(list.length <= 6, '指数条上限 6 条')
  assert.equal(list[0].code, '000001')
})

test('自定义配置：停用 + 排序生效，且只返回启用项', () => {
  const cfg = mod.defaultIndexIndicators()
  // 停用除首个外的全部 → 只剩 1 条
  cfg.SH.forEach((x, i) => {
    x.enabled = i === 2 // 只留沪深300
  })
  mod.saveIndexIndicators(cfg)
  const list = mod.enabledIndices('SH')
  assert.equal(list.length, 1)
  assert.equal(list[0].code, '000300')

  // 排序：把末位（科创50）提到最前
  const cfg2 = mod.defaultIndexIndicators()
  const last = cfg2.SH[cfg2.SH.length - 1]
  last.sort = -1
  mod.saveIndexIndicators(cfg2)
  const first = mod.enabledIndices('SH')[0]
  assert.equal(first.code, last.code, 'sort 最小的项应排最前')
  assert.equal(first.code, '000688', '默认 SH 末位是科创50')
})

test('配置被清洗：非法项剔除、非法 overlay 过滤', () => {
  const dirty = {
    SH: [
      { market: 'SH', code: '000001', name: '上证', enabled: true, overlays: ['ma', 'bogus', 'ema'] },
      { market: 'SH', code: '', name: '缺代码' }, // 应剔除
      { market: 'SH', name: '缺 code 字段' }, // 应剔除
      null,
    ],
  }
  mod.saveIndexIndicators(dirty)
  const list = mod.enabledIndices('SH')
  assert.equal(list.length, 1, '非法项应被剔除')
  assert.deepEqual(list[0].overlays, ['ma', 'ema'], '非法 overlay 应过滤')
})

test('空列表回退默认（指数条不会全空）', () => {
  mod.saveIndexIndicators({ SH: [] })
  const list = mod.enabledIndices('SH')
  assert.ok(list.length > 0, '空配置应回退默认而非空白')
})

test('resetIndexIndicators 恢复默认', () => {
  const cfg = mod.defaultIndexIndicators()
  cfg.US.forEach((x) => (x.enabled = false))
  mod.saveIndexIndicators(cfg)
  const back = mod.resetIndexIndicators()
  assert.equal(back.US.length, mod.defaultIndexIndicators().US.length)
  assert.ok(back.US.some((x) => x.enabled))
})