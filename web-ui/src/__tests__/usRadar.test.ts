/**
 * usRadar.ts 口径与快照结构自检（Node 内置 test runner，无 DOM 依赖）。
 *
 * 运行：node --test src/__tests__/usRadar.test.ts
 *
 * 覆盖：
 * 1. fmtPct / fmtNum / dirCls 的空值与符号处理——这些是整页所有数字的出口，
 *    边界错了满屏都会跟着错。
 * 2. pcrVerdict 四档边界：页面与焦点个股卡共用同一函数，分档必须一致。
 * 3. driverVerdict 的前缀兜底：快照里的判定值带括号后缀，逐条查表会漏，
 *    这条兜底规则正是为此存在（见函数注释）。
 * 4. 快照本身的结构：顶层 24 个分区缺一不可。
 * 5. 缺源契约：任何写成 null 的分区都必须登记原因——这是页面区分
 *    「数据源不可用」与「今天没数据」的唯一依据（见下方用例注释）。
 *
 * 注意：这里断言的是**不变量**而非具体数值。快照既可能来自实算构建
 * （scripts/build_us_radar.py，行情随日期变化），也可能来自历史静态版本，
 * 用例对两者都成立——写死 299 只这类数字，会让每天重建数据后测试就红。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

import {
  dirCls,
  driverVerdict,
  fmtNum,
  fmtPct,
  pcrVerdict,
  fetchUsRadar,
  fetchUsRadarVersion,
  triggerUsRadarRebuild,
} from '../data/usRadar.ts'

const HERE = dirname(fileURLToPath(import.meta.url))
const SNAPSHOT = resolve(HERE, '../../public/data/us-radar.json')
const data = JSON.parse(readFileSync(SNAPSHOT, 'utf8'))

test('fmtPct：带号、空值、位数', () => {
  assert.equal(fmtPct(1.234), '+1.23%')
  assert.equal(fmtPct(-1.234), '-1.23%')
  assert.equal(fmtPct(0), '0.00%', '0 不加正号')
  assert.equal(fmtPct(1234, 1), '+1234.0%')
  assert.equal(fmtPct(null), '—')
  assert.equal(fmtPct(undefined), '—')
  assert.equal(fmtPct(Number.NaN), '—')
})

test('fmtNum：空值与位数', () => {
  assert.equal(fmtNum(1.234), '1.23')
  assert.equal(fmtNum(1.234, 0), '1')
  assert.equal(fmtNum(null), '—')
})

test('dirCls：0 与缺失值都走弱化色，不参与涨跌', () => {
  assert.equal(dirCls(1), 'rd-up')
  assert.equal(dirCls(-1), 'rd-down')
  assert.equal(dirCls(0), 'rd-flat', '持平不该上红/绿')
  assert.equal(dirCls(null), 'rd-dim')
})

test('pcrVerdict：四档边界，边界值归入更保守的一档', () => {
  assert.equal(pcrVerdict(0.2).label, '强多头')
  assert.equal(pcrVerdict(0.5).label, '强多头', '0.5 算强多头')
  assert.equal(pcrVerdict(0.51).label, '偏多头')
  assert.equal(pcrVerdict(0.75).label, '偏多头', '0.75 算偏多头')
  assert.equal(pcrVerdict(0.76).label, '均衡')
  assert.equal(pcrVerdict(1).label, '均衡', '1.0 算均衡')
  assert.equal(pcrVerdict(1.01).label, '偏空头')
  assert.equal(pcrVerdict(Number.NaN).label, '数据缺失')
})

test('driverVerdict：原表命中优先，带括号后缀走前缀兜底', () => {
  // 原站字典里的原值
  assert.equal(driverVerdict('实质性').label, '实质性')
  assert.equal(driverVerdict('情绪/轮动').label, '情绪/轮动')
  // 快照里实际出现、但不在原表中的值
  assert.equal(driverVerdict('实质性(指引上调)').label, '实质性')
  assert.equal(driverVerdict('情绪扩散(间接)').label, '情绪为主')
  assert.equal(driverVerdict('情绪性(持续性存疑)').label, '情绪为主')
  assert.equal(driverVerdict('未知判定').label, '未知判定', '无法归类时原样透出')
})

test('driverVerdict：快照里的每个判定值都能归到某一类（有颜色）', () => {
  // items 可能为空（实算构建无事件源时不生成归因条目），此时本条断言空转但仍成立
  for (const it of data.drivers.items ?? []) {
    const v = driverVerdict(it.verdict)
    assert.ok(v.color.startsWith('var(--'), `${it.ticker} 的判定 ${it.verdict} 没有落到色板`)
  }
})

test('快照：24 个顶层分区齐全', () => {
  const expected = [
    'meta', 'regime', 'index', 'tnx', 'macro', 'sectors', 'themes', 'anomalies',
    'news', 'watchlist', 'options', 'focus', 'daily', 'left', 'exits',
    'theme_trend', 'quality', 'crowding', 'subsectors', 'divergence', 'drivers',
    'geo_oil', 'congress', 'review',
  ]
  for (const k of expected) {
    assert.ok(k in data, `快照缺少分区 ${k}`)
  }
})

test('快照：页头/页脚依赖的 meta 字段非空', () => {
  for (const k of ['asOf', 'builtAt', 'delay', 'universe']) {
    assert.equal(typeof data.meta[k], 'string')
    assert.ok(data.meta[k].length > 0, `meta.${k} 为空`)
  }
})

test('快照：观测池非空且每行都能算出 close（不能整列为 null）', () => {
  assert.ok(data.watchlist.length > 100, '观测池过小，构建可能整体失败')
  for (const w of data.watchlist) {
    assert.equal(typeof w.close, 'number', `${w.ticker} 没有 close`)
    assert.ok(w.close > 0, `${w.ticker} 的 close 非正：${w.close}`)
  }
})

test('快照：期权链要么完整、要么为 null 并登记原因（不许半残）', () => {
  if (data.options === null) {
    assert.ok(
      typeof data.meta.degraded?.options === 'string',
      'options 为 null 却没有在 meta.degraded 里说明原因',
    )
    return
  }
  assert.equal(data.options.chains.length, 7)
  // 每条链的 pcr 必须与 call/put 自洽（改了 callVol 忘了同步 pcr 是最常见的错）
  for (const c of data.options.chains) {
    const expect = c.put_vol / c.call_vol
    assert.ok(Math.abs(c.pcr_vol - expect) < 0.005, `${c.ticker} 的 pcr_vol 与 call/put 不自洽`)
    assert.ok(c.hot_calls.length > 0 && c.hot_puts.length > 0, `${c.ticker} 缺热点行权价`)
  }
})

/**
 * 缺源契约：任何被写成 null 的分区，都必须在 meta.degraded 里登记原因。
 *
 * 这条是本次接入实算数据源后最关键的不变量——它是「数据源不可用」与
 * 「今天恰好没数据」在页面上的唯一区别。少登记一个键，页面就会显示一个
 * 没有解释的空白，读者无从判断是该等数据还是该放弃这个指标。
 */
test('快照：每个 null 分区都在 meta.degraded 里登记了原因', () => {
  const nullable = ['news', 'options', 'quality', 'geo_oil', 'congress']
  for (const k of nullable) {
    if (data[k] !== null) continue
    const reason = data.meta.degraded?.[k]
    assert.equal(typeof reason, 'string', `分区 ${k} 为 null 但 meta.degraded.${k} 缺失`)
    assert.ok(reason.length > 8, `${k} 的缺失原因过于简略：${reason}`)
  }
})

test('快照：meta.degraded 的每个键都能在前端找到对应渲染分支', () => {
  // 前端只对这几个分区做 null 分支；多出来的键说明前后端没对齐，
  // 页面上会既不渲染内容、也不给原因。
  const handled = new Set([
    'news', 'options', 'quality', 'geo_oil', 'congress',
    'index', 'crowding.inst', 'drivers.items',
  ])
  for (const k of Object.keys(data.meta.degraded ?? {})) {
    assert.ok(handled.has(k), `meta.degraded 里的 ${k} 没有对应的前端处理分支`)
  }
})

test('快照：板块与成分的行数一致（总表能按代码索引到）', () => {
  const pool = new Set(data.watchlist.map((w: { ticker: string }) => w.ticker))
  for (const s of data.sectors) {
    for (const c of s.constituents) {
      assert.ok(pool.has(c.ticker), `${s.ticker} 的成分 ${c.ticker} 不在总表里`)
    }
  }
})

test('快照：量能异动的每个代码都能在总表里查到（用于补齐周涨跌/距高点）', () => {
  const pool = new Set(data.watchlist.map((w: { ticker: string }) => w.ticker))
  for (const a of data.anomalies) {
    assert.ok(pool.has(a.ticker), `量能异动 ${a.ticker} 不在总表里`)
  }
})

test('快照：复盘两个窗口都有数据，且每条命中率都在 0-100', () => {
  for (const win of [data.review.signal_stats, data.review.signal_stats_ref]) {
    assert.ok(win.length > 0, '复盘窗口为空')
    for (const s of win) {
      for (const k of ['hit5', 'hit10']) {
        if (s[k] !== null && s[k] !== undefined) {
          assert.ok(s[k] >= 0 && s[k] <= 100, `${s.signal} 的 ${k}=${s[k]} 越界`)
        }
      }
    }
  }
})

// ── 定时重建：版本探测 / 手动触发的降级契约 ─────────────────────────────────

/** 临时替换 globalThis.fetch，用例结束必定还原（含抛异常路径）。 */
function withFetch(fn: typeof globalThis.fetch, body: () => Promise<void>) {
  const original = globalThis.fetch
  globalThis.fetch = fn
  return body().finally(() => {
    globalThis.fetch = original
  })
}

test('fetchUsRadarVersion：接口不可用时返回 null（降级为纯静态快照，不抛错）', async () => {
  await withFetch(
    (async () => {
      throw new TypeError('network down')
    }) as typeof globalThis.fetch,
    async () => {
      assert.equal(await fetchUsRadarVersion(), null)
    },
  )
  await withFetch(
    (async () => new Response('', { status: 503 })) as typeof globalThis.fetch,
    async () => {
      assert.equal(await fetchUsRadarVersion(), null)
    },
  )
})

test('fetchUsRadarVersion：返回版本与重建状态供前端判断是否重拉', async () => {
  const payload = {
    built_at: '2026-11-09',
    as_of: '2026-11-08 收盘',
    delay: '日线',
    source: 'akshare',
    rebuild: {
      enabled: true,
      running: false,
      builds: 2,
      failures: 0,
      built_at: '2026-11-09',
      as_of: '',
      last_error: '',
      last_success: null,
      interval_sec: 86400,
    },
  }
  await withFetch(
    (async () => new Response(JSON.stringify(payload), { status: 200 })) as typeof globalThis.fetch,
    async () => {
      const v = await fetchUsRadarVersion()
      assert.equal(v?.built_at, '2026-11-09')
      assert.equal(v?.rebuild.enabled, true)
      assert.equal(v?.rebuild.builds, 2)
    },
  )
})

test('triggerUsRadarRebuild：非 2xx 时抛出服务端原因', async () => {
  await withFetch(
    (async () =>
      new Response(JSON.stringify({ detail: '定时重建未启用' }), {
        status: 409,
      })) as typeof globalThis.fetch,
    async () => {
      await assert.rejects(() => triggerUsRadarRebuild(), /定时重建未启用/)
    },
  )
})

// ── 打开即读最新：取数一律绕过缓存 ──────────────────────────────────────────

test('fetchUsRadar：带 cache:no-store，避免打开页面拿到浏览器缓存的旧快照', async () => {
  let seen: RequestInit | undefined
  await withFetch(
    (async (_u: string | URL | Request, init?: RequestInit) => {
      seen = init
      return new Response(JSON.stringify({ meta: { asOf: 'x', builtAt: 'y' } }), {
        status: 200,
      })
    }) as typeof globalThis.fetch,
    async () => {
      await fetchUsRadar()
    },
  )
  assert.equal(seen?.cache, 'no-store')
})

test('fetchUsRadarVersion：同样 no-store，版本探测不能被缓存挡住', async () => {
  let seen: RequestInit | undefined
  await withFetch(
    (async (_u: string | URL | Request, init?: RequestInit) => {
      seen = init
      return new Response('', { status: 503 })
    }) as typeof globalThis.fetch,
    async () => {
      await fetchUsRadarVersion()
    },
  )
  assert.equal(seen?.cache, 'no-store')
})