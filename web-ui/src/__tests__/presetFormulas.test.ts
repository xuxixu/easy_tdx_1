import { test } from 'node:test'
import assert from 'node:assert/strict'

import { DEFAULT_INDICATOR_PARAMS } from '../indicatorParams.ts'
import { PRESETS, presetById } from '../presetFormulas.ts'

test('六预置齐全：id/主副图归属/锁定', () => {
  assert.equal(
    PRESETS.map((p) => `${p.id}:${p.kind}`).join(','),
    'ma:overlay,ema:overlay,boll:overlay,macd:sub,kdj:sub,rsi:sub',
  )
  assert.ok(PRESETS.every((p) => p.locked === true))
  assert.ok(presetById('bogus') === undefined)
})

test('MA 公式：多周期各一行输出', () => {
  const text = presetById('ma')!.buildFormula({
    ...DEFAULT_INDICATOR_PARAMS,
    maPeriods: [5, 20],
  })
  assert.match(text, /MA5: MA\(C,5\);/)
  assert.match(text, /MA20: MA\(C,20\);/)
  assert.equal(text.split('\n').length, 2)
})

test('MACD 公式：DIF/DEA 经中间变量 + HIST', () => {
  const text = presetById('macd')!.buildFormula(DEFAULT_INDICATOR_PARAMS)
  assert.match(text, /DIF: EMA\(C,12\)-EMA\(C,26\);/)
  assert.match(text, /DEA: EMA\(DIF,9\);/)
  assert.match(text, /MACD_HIST: \(DIF-DEA\)\*2;/)
})

test('BOLL 公式：倍数插值 + 中轨复用', () => {
  const text = presetById('boll')!.buildFormula({ ...DEFAULT_INDICATOR_PARAMS, bollP: 2.5 })
  assert.match(text, /BOLL_MID: MA\(C,20\);/)
  assert.match(text, /BOLL_UPPER: BOLL_MID\+2\.5\*STD\(C,20\);/)
  assert.match(text, /BOLL_LOWER: BOLL_MID-2\.5\*STD\(C,20\);/)
})

test('KDJ 公式：RSV 中间变量 + K/D/J', () => {
  const text = presetById('kdj')!.buildFormula(DEFAULT_INDICATOR_PARAMS)
  assert.ok(text.includes('RSV := (C-LLV(L,9))/(HHV(H,9)-LLV(L,9))*100;'))
  assert.match(text, /K: SMA\(RSV,3,1\);/)
  assert.match(text, /J: 3\*K-2\*D;/)
})

test('RSI 公式：UD 中间变量 + 多周期', () => {
  const text = presetById('rsi')!.buildFormula({ ...DEFAULT_INDICATOR_PARAMS, rsiPeriods: [6, 12] })
  assert.match(text, /UD := C-REF\(C,1\);/)
  assert.ok(text.includes('RSI6: SMA(MAX(UD,0),6,1)/SMA(ABS(UD),6,1)*100;'))
  assert.ok(text.includes('RSI12: SMA(MAX(UD,0),12,1)/SMA(ABS(UD),12,1)*100;'))
})

test('图例颜色虚线bar映射与旧口径一致', () => {  const boll = presetById('boll')!
  assert.equal(boll.displayName('BOLL_MID'), 'BOLL中轨')
  assert.equal(boll.displayName('BOLL_UPPER'), 'BOLL上轨')
  assert.equal(boll.dashedFor('BOLL_MID'), false)
  assert.equal(boll.dashedFor('BOLL_UPPER'), true)
  const macd = presetById('macd')!
  assert.equal(macd.displayName('MACD_HIST'), 'MACD')
  assert.equal(macd.isBar('MACD_HIST'), true)
  assert.equal(macd.isBar('DIF'), false)
  assert.equal(presetById('kdj')!.colorFor('J', 2), '#c084fc')
  assert.deepEqual(presetById('kdj')!.columns(DEFAULT_INDICATOR_PARAMS), ['K', 'D', 'J'])
})

test('columns 与 buildFormula 输出列一致（服务端序列化用）', () => {
  const p = { ...DEFAULT_INDICATOR_PARAMS, maPeriods: [5, 20], rsiPeriods: [6] }
  assert.deepEqual(presetById('ma')!.columns(p), ['MA5', 'MA20'])
  assert.deepEqual(presetById('ema')!.columns(p), ['EMA12', 'EMA26'])
  assert.deepEqual(presetById('boll')!.columns(p), ['BOLL_MID', 'BOLL_UPPER', 'BOLL_LOWER'])
  assert.deepEqual(presetById('macd')!.columns(p), ['DIF', 'DEA', 'MACD_HIST'])
  assert.deepEqual(presetById('rsi')!.columns(p), ['RSI6'])
})
