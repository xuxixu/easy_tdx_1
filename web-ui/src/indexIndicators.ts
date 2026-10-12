// 指数指标配置（系统 → 指数设置）。
//
// 每个市场可配置一列指数指标（看板顶部指数条 / 大盘日历共用），支持：
// - 新增 / 修改 / 删除任意指数（市场 + 代码 + 名称）
// - 排序、启用开关
// - 每条指数可叠加多种技术指标（MA/EMA/BOLL…），叠加项在指数条迷你图上标注
//
// 默认值取各市场主流指数（沪/深/北/港/美），可在页面里增删改；
// 配置落 localStorage（key 见 STORAGE_KEY），损坏/越界时回落到默认。
import { A_SHARE_MARKETS, isAShare, marketLabel, type AShareMarket, type Market } from './market.ts'

export type IndexIndicatorKind = 'ma' | 'ema' | 'boll'

/** 可叠加的技术指标（迷你图只画趋势线，不占用额外空间）。 */
export const INDEX_OVERLAY_OPTIONS: Array<{
  value: IndexIndicatorKind
  label: string
  periods?: number[]
  hint: string
}> = [
  { value: 'ma', label: 'MA', periods: [5, 10, 20], hint: '5/10/20 日均线' },
  { value: 'ema', label: 'EMA', periods: [12, 26], hint: '12/26 日指数均线' },
  { value: 'boll', label: 'BOLL', periods: [20], hint: '20 日布林带中轨' },
]

export interface IndexIndicatorItem {
  market: string
  code: string
  name: string
  enabled: boolean
  /** 叠加的技术指标（可多选，空 = 只画价格）。 */
  overlays: IndexIndicatorKind[]
  sort: number
}

/** 各市场默认指数（主流口径，可在设置页增删改）。 */
export function defaultIndexIndicators(): Record<string, IndexIndicatorItem[]> {
  return {
    SH: [
      { market: 'SH', code: '000001', name: '上证指数', enabled: true, overlays: ['ma'], sort: 0 },
      { market: 'SZ', code: '399001', name: '深证成指', enabled: true, overlays: ['ma'], sort: 1 },
      { market: 'SH', code: '000300', name: '沪深300', enabled: true, overlays: [], sort: 2 },
      { market: 'SZ', code: '399006', name: '创业板指', enabled: true, overlays: [], sort: 3 },
      { market: 'SH', code: '000688', name: '科创50', enabled: true, overlays: [], sort: 4 },
    ],
    SZ: [
      { market: 'SZ', code: '399001', name: '深证成指', enabled: true, overlays: ['ma'], sort: 0 },
      { market: 'SH', code: '000001', name: '上证指数', enabled: true, overlays: ['ma'], sort: 1 },
      { market: 'SZ', code: '399006', name: '创业板指', enabled: true, overlays: [], sort: 2 },
    ],
    BJ: [
      { market: 'BJ', code: '899050', name: '北证50', enabled: true, overlays: ['ma'], sort: 0 },
      { market: 'SH', code: '000001', name: '上证指数', enabled: true, overlays: [], sort: 1 },
      { market: 'SZ', code: '399001', name: '深证成指', enabled: true, overlays: [], sort: 2 },
    ],
    HK: [
      { market: 'HK', code: 'HSI', name: '恒生指数', enabled: true, overlays: ['ma'], sort: 0 },
      { market: 'HK', code: 'HSCEI', name: '国企指数', enabled: true, overlays: [], sort: 1 },
      { market: 'HK', code: 'HSTECH', name: '恒生科技指数', enabled: true, overlays: [], sort: 2 },
    ],
    US: [
      { market: 'US', code: 'DJI', name: '道琼斯指数', enabled: true, overlays: ['ma'], sort: 0 },
      { market: 'US', code: 'IXIC', name: '纳斯达克综合指数', enabled: true, overlays: ['ema'], sort: 1 },
      { market: 'US', code: 'SPX', name: '标普500指数', enabled: true, overlays: [], sort: 2 },
      { market: 'US', code: 'NDX', name: '纳斯达克100指数', enabled: true, overlays: [], sort: 3 },
    ],
  }
}

const STORAGE_KEY = 'easytdx.indexIndicators'

const VALID_OVERLAYS = INDEX_OVERLAY_OPTIONS.map((o) => o.value)

function sanitizeItem(raw: unknown): IndexIndicatorItem | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const code = String(r.market ?? '').trim().toUpperCase()
  const symbol = String(r.code ?? '').trim().toUpperCase()
  if (!code || !symbol) return null
  const overlays = Array.isArray(r.overlays)
    ? (r.overlays.filter((o) => VALID_OVERLAYS.includes(o as IndexIndicatorKind)) as IndexIndicatorKind[])
    : []
  return {
    market: code,
    code: symbol,
    name: String(r.name ?? symbol).slice(0, 24),
    enabled: r.enabled !== false,
    overlays: [...new Set(overlays)],
    sort: Number.isFinite(Number(r.sort)) ? Number(r.sort) : 0,
  }
}

/** 读配置（损坏/缺失 → 默认），保证每市场至少一条启用项。 */
export function loadIndexIndicators(): Record<string, IndexIndicatorItem[]> {
  let parsed: Record<string, unknown> = {}
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) parsed = JSON.parse(raw) as Record<string, unknown>
  } catch {
    parsed = {}
  }
  const def = defaultIndexIndicators()
  const out: Record<string, IndexIndicatorItem[]> = {}
  for (const key of [...A_SHARE_MARKETS, 'HK', 'US'] as string[]) {
    const list = Array.isArray(parsed[key]) ? (parsed[key] as unknown[]) : null
    const items = (list ?? (def[key] ?? []))
      .map(sanitizeItem)
      .filter((x): x is IndexIndicatorItem => x !== null)
      .sort((a, b) => a.sort - b.sort)
      .map((x, i) => ({ ...x, sort: i }))
    // 空列表回退默认（否则指数条会全空）
    out[key] = items.length > 0 ? items : (def[key] ?? []).map((x, i) => ({ ...x, sort: i }))
  }
  return out
}

/** 写配置（失败不影响本次会话）。 */
export function saveIndexIndicators(cfg: Record<string, IndexIndicatorItem[]>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg))
  } catch {
    // 持久化失败不抛
  }
}

/** 恢复默认。 */
export function resetIndexIndicators(): Record<string, IndexIndicatorItem[]> {
  const d = defaultIndexIndicators()
  saveIndexIndicators(d)
  return d
}

/** 某市场启用的指数（按序），供看板指数条 / 大盘日历使用。 */
export function enabledIndices(market: Market | string): IndexIndicatorItem[] {
  const cfg = loadIndexIndicators()
  const list = cfg[market] ?? []
  const on = list.filter((x) => x.enabled)
  return (on.length > 0 ? on : list).slice(0, 6)
}

/** 市场中文名（设置页下拉用）。 */
export function marketOptionLabel(m: string): string {
  if (isAShare(m)) return marketLabel(m as AShareMarket)
  return marketLabel(m as Market)
}