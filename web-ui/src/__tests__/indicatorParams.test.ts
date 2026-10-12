/**
 * indicatorParams 存储自检：版本化存储 + 老形态迁移 + 自定义清洗。
 *
 * localStorage 打桩（Node 无 DOM）。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  DEFAULT_INDICATOR_PARAMS,
  loadCustoms,
  loadIndicatorConfig,
  loadIndicatorParams,
  newCustomId,
  sanitizeCandle,
  sanitizeCustoms,
  saveCustoms,
  saveIndicatorParams,
} from '../indicatorParams.ts'

const store = new Map<string, string>()

function installStorage() {
  const original = globalThis.localStorage
  globalThis.localStorage = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: () => null,
    length: 0,
  } as unknown as Storage
  store.clear()
  return () => {
    globalThis.localStorage = original
  }
}

test('空存储回默认', () => {
  const restore = installStorage()
  try {
    assert.deepEqual(loadIndicatorParams().maPeriods, [5, 10, 20, 60])
    assert.deepEqual(loadCustoms(), [])
  } finally {
    restore()
  }
})

test('老形态（裸 IndicatorParams）自动迁入', () => {
  const restore = installStorage()
  try {
    store.set(
      'easytdx.indicators',
      JSON.stringify({ ...DEFAULT_INDICATOR_PARAMS, maPeriods: [5, 10], subPane: 'kdj' }),
    )
    const cfg = loadIndicatorConfig()
    assert.deepEqual(cfg.params.maPeriods, [5, 10])
    assert.equal(cfg.params.subPane, 'kdj')
    assert.deepEqual(cfg.customs, [])
  } finally {
    restore()
  }
})

test('选择 id 透传（自定义 id 不被洗掉）', () => {
  const restore = installStorage()
  try {
    saveIndicatorParams({ ...DEFAULT_INDICATOR_PARAMS, overlays: ['ma', 'cabc123'], subPane: 'cxyz' })
    const p = loadIndicatorParams()
    assert.deepEqual(p.overlays, ['ma', 'cabc123'])
    assert.equal(p.subPane, 'cxyz')
  } finally {
    restore()
  }
})

test('自定义 roundtrip + 非法条目清洗', () => {
  const restore = installStorage()
  try {
    saveCustoms([
      { id: 'c1', name: '通道', kind: 'overlay', formula: 'MID: MA(C,20);' },
      { id: '', name: '坏', kind: 'overlay', formula: 'X: 1;' },
      { id: 'c2', name: '', kind: 'sub', formula: 'X: 1;' },
      { id: 'c3', name: '坏kind', kind: 'bogus', formula: 'X: 1;' } as unknown as {
        id: string
        name: string
        kind: 'overlay' | 'sub'
        formula: string
      },
    ])
    // save 保留参数
    assert.deepEqual(loadIndicatorParams().maPeriods, [5, 10, 20, 60])
    assert.deepEqual(loadCustoms(), [{ id: 'c1', name: '通道', kind: 'overlay', formula: 'MID: MA(C,20);', candle: [] }])
  } finally {
    restore()
  }
})

test('叠加K线列清洗 sanitizeCandle', () => {
  assert.deepEqual(sanitizeCandle(['XOPEN', 'XCLOSE', 'XHIGH', 'XLOW']), ['XOPEN', 'XCLOSE', 'XHIGH', 'XLOW'])
  assert.deepEqual(sanitizeCandle(['A', 'B']), [])
  assert.deepEqual(sanitizeCandle(['A', 'B', 'C', '']), [])
  assert.deepEqual(sanitizeCandle('XOPEN'), [])
  assert.deepEqual(
    sanitizeCustoms([{ id: 'c9', name: 'K', kind: 'overlay', formula: 'X: C;', candle: ['A', 'B', 'C', 'D'] }]),
    [{ id: 'c9', name: 'K', kind: 'overlay', formula: 'X: C;', candle: ['A', 'B', 'C', 'D'] }],
  )
})

test('save 参数保留自定义；sanitizeCustoms 去重', () => {
  const restore = installStorage()
  try {
    saveCustoms([{ id: 'c1', name: 'A', kind: 'sub', formula: 'X: C;' }])
    saveIndicatorParams({ ...DEFAULT_INDICATOR_PARAMS, kdjN: 14 })
    assert.equal(loadIndicatorParams().kdjN, 14)
    assert.equal(loadCustoms().length, 1)
    assert.deepEqual(
      sanitizeCustoms([
        { id: 'c1', name: 'A', kind: 'sub', formula: 'X: C;' },
        { id: 'c1', name: 'A2', kind: 'sub', formula: 'Y: C;' },
      ]).length,
      1,
    )
    assert.ok(newCustomId().startsWith('c'))
  } finally {
    restore()
  }
})
