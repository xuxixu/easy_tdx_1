/**
 * usOptions.ts 期权口径自检（Node 内置 test runner，无 DOM 依赖）。
 *
 * 运行：node --test src/__tests__/usOptions.test.ts
 *
 * 覆盖：
 * 1. pcrVerdict 的四档边界——边界值归属是「更保守的一档」（0.5 算强多头、
 *    0.75 算偏多头、1.0 算均衡）。页面与右侧栏共用这个函数，改分档会同时
 *    改动两处展示，所以边界必须钉死。
 * 2. callSharePct 的比例条宽度，以及无成交量时退回 50（避免条长为 0 抖动）。
 * 3. fmtChainVol 的紧凑写法（134059 → "134.1k"）。
 * 4. 样例数据自洽性：pcr 必须等于 putVol/callVol，且 call+put 的占比自洽——
 *    mock 数据最容易出的错就是改了 callVol 却忘了同步 pcr。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  US_OPTION_CHAINS,
  callSharePct,
  fmtChainVol,
  pcrVerdict,
  summarizeChains,
} from '../data/usOptions.ts'

test('pcrVerdict：四档边界', () => {
  assert.equal(pcrVerdict(0.2).label, '强多头')
  assert.equal(pcrVerdict(0.5).label, '强多头', '0.5 归强多头（边界取更保守的一档）')
  assert.equal(pcrVerdict(0.51).label, '偏多头')
  assert.equal(pcrVerdict(0.75).label, '偏多头', '0.75 归偏多头')
  assert.equal(pcrVerdict(0.76).label, '均衡')
  assert.equal(pcrVerdict(1).label, '均衡', '1.0 归均衡')
  assert.equal(pcrVerdict(1.01).label, '偏空头')
})

test('pcrVerdict：tone 与 label 一一对应', () => {
  assert.equal(pcrVerdict(0.3).tone, 'strong-bull')
  assert.equal(pcrVerdict(0.6).tone, 'bull')
  assert.equal(pcrVerdict(0.9).tone, 'balanced')
  assert.equal(pcrVerdict(1.4).tone, 'bear')
})

test('pcrVerdict：NaN 不炸，返回缺失档', () => {
  assert.equal(pcrVerdict(Number.NaN).tone, 'balanced')
})

test('callSharePct：看涨占比 = call/(call+put)', () => {
  const chain = { callVol: 75, putVol: 25 } as never
  assert.equal(callSharePct(chain), 75)
})

test('callSharePct：无成交量退回 50，条长不为 0', () => {
  const chain = { callVol: 0, putVol: 0 } as never
  assert.equal(callSharePct(chain), 50)
})

test('fmtChainVol：紧凑 k 写法', () => {
  assert.equal(fmtChainVol(134059), '134.1k')
  assert.equal(fmtChainVol(2737), '2.7k')
  assert.equal(fmtChainVol(Number.NaN), '-')
})

test('样例数据自洽：pcr === putVol/callVol', () => {
  for (const c of US_OPTION_CHAINS) {
    const expect = c.putVol / c.callVol
    assert.ok(
      Math.abs(c.pcr - expect) < 0.005,
      `${c.ticker}: pcr=${c.pcr} 与 putVol/callVol=${expect.toFixed(4)} 不一致`,
    )
  }
})

test('样例数据自洽：热点不超过 3 个且成交量非空', () => {
  for (const c of US_OPTION_CHAINS) {
    assert.ok(c.hotCalls.length > 0 && c.hotCalls.length <= 3, `${c.ticker} 看涨热点数量异常`)
    assert.ok(c.hotPuts.length > 0 && c.hotPuts.length <= 3, `${c.ticker} 看跌热点数量异常`)
    for (const s of [...c.hotCalls, ...c.hotPuts]) {
      assert.ok(s.volume > 0, `${c.ticker} 行权价 ${s.strike} 成交量应为正`)
    }
  }
})

test('样例数据自洽：热点成交量不超过该侧总成交', () => {
  for (const c of US_OPTION_CHAINS) {
    for (const s of c.hotCalls) {
      assert.ok(s.volume <= c.callVol, `${c.ticker} 看涨热点 ${s.strike} 超过总成交`)
    }
    for (const s of c.hotPuts) {
      assert.ok(s.volume <= c.putVol, `${c.ticker} 看跌热点 ${s.strike} 超过总成交`)
    }
  }
})

test('summarizeChains：给出标的数与 PCR 区间', () => {
  const s = summarizeChains(US_OPTION_CHAINS)
  assert.match(s, new RegExp(`^${US_OPTION_CHAINS.length} 只`))
  assert.match(s, /PCR 区间 \d\.\d{2} ~ \d\.\d{2}/)
})

test('summarizeChains：空数组不报错', () => {
  assert.equal(summarizeChains([]), '暂无期权链数据')
})