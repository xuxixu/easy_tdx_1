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
  pickHourTicks,
  toHhmm,
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

test('usSession：北京时间口径下夏令/冬令盘中窗口自动偏移 1 小时', () => {
  // 看板自动刷新门控用 usSession(now)==='open'，必须随夏令/冬令自动切换。
  // 北京 = UTC+8。取夏令（7月周三）与冬令（1月周三）同一北京时刻对照。
  const summerEve = (hhmm: string) => new Date(`2026-07-15T${hhmm}:00+08:00`)
  const summerNextDay = (hhmm: string) => new Date(`2026-07-16T${hhmm}:00+08:00`)
  const winterEve = (hhmm: string) => new Date(`2026-01-14T${hhmm}:00+08:00`)
  const winterNextDay = (hhmm: string) => new Date(`2026-01-15T${hhmm}:00+08:00`)
  // 夏令 21:30 开盘：21:29 盘前、21:30 起盘中；次日凌晨收盘前仍盘中、收盘后转盘后
  assert.equal(usSession(summerEve('21:29')), 'pre', '夏令 21:29 未开盘')
  assert.equal(usSession(summerEve('21:30')), 'open', '夏令 21:30 开盘')
  assert.equal(usSession(summerNextDay('03:59')), 'open', '夏令次日 03:59 仍盘中')
  assert.equal(usSession(summerNextDay('04:01')), 'after', '夏令次日 04:01 转盘后')
  // 冬令整体 +1h：同一 21:30 仍是盘前，22:30 才开盘；收盘也顺延到 05:01
  assert.equal(usSession(winterEve('21:30')), 'pre', '冬令 21:30 仍在盘前')
  assert.equal(usSession(winterEve('22:30')), 'open', '冬令 22:30 开盘')
  assert.equal(usSession(winterNextDay('04:59')), 'open', '冬令次日 04:59 仍盘中')
  assert.equal(usSession(winterNextDay('05:01')), 'after', '冬令次日 05:01 转盘后')
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
// ── toHhmm：分时时间归一化 ────────────────────────────────────────────────────

test('toHhmm：三种常见写法都归一到 HH:MM', () => {
  // 扩展栈分时（无日期）
  assert.equal(toHhmm('21:30:00'), '21:30')
  // 已是 HH:MM
  assert.equal(toHhmm('21:30'), '21:30')
  // 带日期（A 股路径可能长这样）
  assert.equal(toHhmm('2026-10-16 21:30:00'), '21:30')
})

test('toHhmm：个位数小时补零', () => {
  assert.equal(toHhmm('9:05'), '09:05')
  assert.equal(toHhmm('9:05:00'), '09:05')
})

test('toHhmm：解析不出返回空串（调用方应跳过该点）', () => {
  assert.equal(toHhmm(''), '')
  assert.equal(toHhmm('--'), '')
  assert.equal(toHhmm('not-a-time'), '')
})

test('toHhmm 与 inUsSessionFilter 联动：带日期的分时也能正确分时段', () => {
  // 这是回归重点：直接 slice(0,5) 对带日期的串会得到 "2026-"，全部判 false，
  // 表现为「切到任何时段都是空图」。
  const dates = ['2026-10-16 21:35:00', '2026-10-17 03:59:00', '2026-10-16 17:00:00']
  const inOpen = dates.filter((d) => inUsSessionFilter(toHhmm(d), 'open'))
  const inPre = dates.filter((d) => inUsSessionFilter(toHhmm(d), 'pre'))
  assert.deepEqual(inOpen, ['2026-10-16 21:35:00', '2026-10-17 03:59:00'])
  assert.deepEqual(inPre, ['2026-10-16 17:00:00'])
})

// ── pickHourTicks：分时图 x 轴刻度 ────────────────────────────────────────────

/** 造一段从 hh:mm 起、步长 1 分钟、共 n 个点的 HH:MM 序列（跨零点自动回绕）。 */
function minuteSeries(startHhmm: string, n: number): string[] {
  const [h0, m0] = startHhmm.split(':').map(Number)
  return Array.from({ length: n }, (_, i) => {
    const t = h0 * 60 + m0 + i
    const h = Math.floor(t / 60) % 24
    return `${String(h).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
  })
}

test('pickHourTicks：A 股 240 点（09:30-14:59）落在整点，首尾必留', () => {
  // A 股上午 120 点 + 下午 120 点（午休不产生点）；弹窗级别的绘图区宽度。
  const times = [...minuteSeries('09:30', 120), ...minuteSeries('13:00', 120)]
  const ticks = pickHourTicks(times, { plotWidth: 992, labelWidth: 36 })
  assert.deepEqual(
    ticks.map((i) => times[i]),
    ['09:30', '10:00', '11:00', '13:00', '14:00', '14:59'],
  )
})

test('pickHourTicks：美股跨零点（22:30-04:59）首档与次档只差半小时时不会叠字', () => {
  const times = minuteSeries('22:30', 390)
  assert.equal(times[times.length - 1], '04:59')

  // 看板面板（~530px 绘图区）：7 档候选里 22:30/23:00 只隔 21px → 丢掉 23:00。
  const narrow = pickHourTicks(times, { plotWidth: 532, labelWidth: 36 })
  assert.deepEqual(
    narrow.map((i) => times[i]),
    ['22:30', '00:00', '02:00', '03:00', '04:00', '04:59'],
  )
  assert.equal(narrow[0], 0, '首点（开盘）必须有刻度')
  assert.equal(narrow[narrow.length - 1], times.length - 1, '末点（最新价）必须有刻度')

  // 弹窗（~990px 绘图区）：间距够，整点铺满 7 档。
  const wide = pickHourTicks(times, { plotWidth: 992, labelWidth: 36 })
  assert.deepEqual(
    wide.map((i) => times[i]),
    ['22:30', '23:00', '00:00', '02:00', '03:00', '04:00', '04:59'],
  )
})

test('pickHourTicks：港股午休断档也不会给出不存在的时刻', () => {
  const times = [...minuteSeries('09:30', 150), ...minuteSeries('13:00', 180)]
  const labels = pickHourTicks(times, { plotWidth: 992, labelWidth: 36 }).map((i) => times[i])
  // 午休 12:00-13:00 没有点，刻度自然跳过 12:00。
  assert.deepEqual(labels, ['09:30', '10:00', '11:00', '13:00', '14:00', '15:00', '15:59'])
  assert.ok(!labels.some((t) => t.startsWith('12:')), '午休时段不应有刻度')
})

test('pickHourTicks：窄卡片（观测雷达 ~100px 绘图区）只留 3 档且不重叠', () => {
  // 走势卡内宽 207px、grid 左右边距 108px → 绘图区约 99px，字号降到 9px。
  const us = minuteSeries('22:30', 390)
  assert.deepEqual(
    pickHourTicks(us, { plotWidth: 99, labelWidth: 27 }).map((i) => us[i]),
    ['22:30', '02:00', '04:59'],
  )
  const hk = [...minuteSeries('09:30', 150), ...minuteSeries('13:00', 180)]
  assert.deepEqual(
    pickHourTicks(hk, { plotWidth: 99, labelWidth: 27 }).map((i) => hk[i]),
    ['09:30', '13:00', '15:59'],
  )
})

test('pickHourTicks：maxTicks=2 只留首尾（极小面板）', () => {
  const times = minuteSeries('22:30', 390)
  assert.deepEqual(pickHourTicks(times, { plotWidth: 99, labelWidth: 27, maxTicks: 2 }), [
    0,
    times.length - 1,
  ])
})

test('pickHourTicks：空序列与单点', () => {
  assert.deepEqual(pickHourTicks([], { plotWidth: 992, labelWidth: 36 }), [])
  assert.deepEqual(pickHourTicks(['09:30'], { plotWidth: 992, labelWidth: 36 }), [0])
})
