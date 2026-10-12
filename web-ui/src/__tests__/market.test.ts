/**
 * market.ts 美股时段逻辑自检（Node 内置 test runner，无 DOM 依赖）。
 *
 * 运行：node --test src/__tests__/market.test.ts
 *
 * 覆盖：
 * 1. inUsSessionFilter 的四态边界——盘前/盘中/盘后/夜盘按北京时间（夏令）切分，
 *    收盘那根 04:00 必须归盘中（美东 16:00 收盘价），错归盘后会少最后一根 bar。
 * 2. 冬令整体 +1h 的偏移。
 * 3. isUsDst 的夏令起止边界（3 月第 2 个周日 / 11 月第 1 个周日）。
 * 4. usSession 四态在典型时刻的判定。
 * 5. 各市场指数条配置（美股第 4 卡必须是纳斯达克100真指数 NDX 而非 ETF 代理）。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  inUsSessionFilter,
  isUsDst,
  MARKET_DEFAULT_INDEX,
  MARKET_INDEX_STRIP,
  usSession,
} from '../market.ts'

test('inUsSessionFilter：盘前 16:00-21:30（夏令北京时间）', () => {
  assert.equal(inUsSessionFilter('16:00', 'pre'), true, '16:00 起点属于盘前')
  assert.equal(inUsSessionFilter('20:00', 'pre'), true)
  assert.equal(inUsSessionFilter('21:25', 'pre'), true)
  assert.equal(inUsSessionFilter('21:30', 'pre'), false, '21:30 是盘中起点')
  assert.equal(inUsSessionFilter('09:00', 'pre'), false)
})

test('inUsSessionFilter：盘中 21:30-04:00 跨零点闭合', () => {
  assert.equal(inUsSessionFilter('21:30', 'open'), true)
  assert.equal(inUsSessionFilter('23:59', 'open'), true)
  assert.equal(inUsSessionFilter('00:00', 'open'), true)
  assert.equal(inUsSessionFilter('03:55', 'open'), true)
  // 边界回归：04:00 是美东 16:00 收盘价，属于盘中，不是盘后
  assert.equal(inUsSessionFilter('04:00', 'open'), true, '收盘价那根必须留在盘中')
  assert.equal(inUsSessionFilter('04:00', 'after'), false, '收盘价不能同时算盘后')
  assert.equal(inUsSessionFilter('04:05', 'open'), false)
})

test('inUsSessionFilter：盘后 04:05-08:00', () => {
  assert.equal(inUsSessionFilter('05:00', 'after'), true)
  assert.equal(inUsSessionFilter('07:55', 'after'), true)
  assert.equal(inUsSessionFilter('08:00', 'after'), false, '08:00 是夜盘起点')
})

test('inUsSessionFilter：夜盘 08:00-16:00', () => {
  assert.equal(inUsSessionFilter('08:00', 'night'), true)
  assert.equal(inUsSessionFilter('12:00', 'night'), true)
  assert.equal(inUsSessionFilter('15:55', 'night'), true)
  assert.equal(inUsSessionFilter('16:00', 'night'), false, '16:00 是盘前起点')
})

test('inUsSessionFilter：all 恒真；冬令整体 +1h', () => {
  for (const t of ['00:00', '09:30', '21:30', '23:00']) {
    assert.equal(inUsSessionFilter(t, 'all'), true)
  }
  // 冬令北京 = ET+13h（夏令 +12h），故同一 ET 时段的北京窗口整体 +1h：
  //   盘前 ET 04:00-09:30 → 夏令北京 16:00-21:30 / 冬令北京 17:00-22:30
  assert.equal(inUsSessionFilter('17:00', 'pre', false), true, '冬令盘前起点 17:00')
  assert.equal(inUsSessionFilter('22:25', 'pre', false), true)
  assert.equal(inUsSessionFilter('22:30', 'pre', false), false, '冬令盘中起点 22:30')
  assert.equal(inUsSessionFilter('16:30', 'pre', false), false, '冬令 16:30 仍是夜盘')
  assert.equal(inUsSessionFilter('16:30', 'pre', true), true, '夏令 16:30 是盘前')
  assert.equal(inUsSessionFilter('16:30', 'night', false), true, '冬令 16:30 归夜盘')
  assert.equal(inUsSessionFilter('22:30', 'open', false), true, '冬令盘中起点 22:30')
  assert.equal(inUsSessionFilter('21:30', 'open', false), false)
})

test('inUsSessionFilter：非法输入返回 false', () => {
  assert.equal(inUsSessionFilter('', 'open'), false)
  assert.equal(inUsSessionFilter('abc', 'open'), false)
})

test('isUsDst：夏令起止边界', () => {
  // 2026 年 3 月第 2 个周日 = 3/8；11 月第 1 个周日 = 11/1
  assert.equal(isUsDst(new Date('2026-03-08T12:00:00Z')), true, '夏令首日')
  assert.equal(isUsDst(new Date('2026-03-07T12:00:00Z')), false, '夏令前一日')
  assert.equal(isUsDst(new Date('2026-11-01T12:00:00Z')), false, '夏令结束日')
  assert.equal(isUsDst(new Date('2026-10-31T12:00:00Z')), true)
  assert.equal(isUsDst(new Date('2026-07-01T12:00:00Z')), true)
  assert.equal(isUsDst(new Date('2026-01-15T12:00:00Z')), false)
})

test('usSession：四态判定（冬令 ET = UTC-5h，2026-01 周三）', () => {
  // ET 09:00（盘前）→ UTC 14:00
  assert.equal(usSession(new Date('2026-01-14T14:00:00Z')), 'pre', 'ET 09:00 盘前')
  // ET 10:00（盘中）→ UTC 15:00
  assert.equal(usSession(new Date('2026-01-14T15:00:00Z')), 'open', 'ET 10:00 盘中')
  // ET 16:30（盘后）→ UTC 21:30
  assert.equal(usSession(new Date('2026-01-14T21:30:00Z')), 'after', 'ET 16:30 盘后')
  // ET 23:00（夜盘）→ UTC 次日 04:00
  assert.equal(usSession(new Date('2026-01-15T04:00:00Z')), 'night', 'ET 23:00 夜盘')
  // 周六 → 恒夜盘
  assert.equal(usSession(new Date('2026-01-17T15:00:00Z')), 'night', '周末恒夜盘')
  // 夏令（2026-07 周三）ET = UTC-4h：ET 10:00 → UTC 14:00
  assert.equal(usSession(new Date('2026-07-15T14:00:00Z')), 'open', '夏令 ET 10:00 盘中')
  assert.equal(usSession(new Date('2026-07-15T12:00:00Z')), 'pre', '夏令 ET 08:00 盘前')
})

test('指数条：美股第 4 卡是纳斯达克100真指数（非 ETF 代理）', () => {
  const us = MARKET_INDEX_STRIP.US
  assert.equal(us.length, 4, '美股 4 张指数卡')
  assert.deepEqual(
    us.map((i) => i.code),
    ['DJI', 'IXIC', 'SPX', 'NDX'],
  )
  assert.equal(us[3].name, '纳斯达克100指数')
  // 纳斯达克100 放在标普500 之后
  assert.equal(us[2].code, 'SPX')
  assert.equal(us[3].code, 'NDX')
})

test('指数条：港股三指数齐全 + 各市场默认指数存在', () => {
  assert.deepEqual(
    MARKET_INDEX_STRIP.HK.map((i) => i.code),
    ['HSI', 'HSCEI', 'HSTECH'],
  )
  for (const key of ['SH', 'SZ', 'BJ', 'HK', 'US'] as const) {
    const def = MARKET_DEFAULT_INDEX[key]
    assert.ok(def && def.code, `${key} 默认指数缺失`)
    assert.ok(MARKET_INDEX_STRIP[key].length >= 1, `${key} 指数条为空`)
  }
})