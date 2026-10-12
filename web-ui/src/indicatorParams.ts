// 指标配置（技术指标管理 + 各 K 线图共用）。
//
// 存储形态（localStorage，key 见 STORAGE_KEY，版本化）：
//   { version: 1, params: IndicatorParams, customs: CustomIndicator[] }
// 老形态（裸 IndicatorParams，无 version）自动迁入。
//
// - params：六组预置指标的周期/倍数 + 主图叠加选择（overlays，可含自定义
//   id）+ 副图选择（subPane，指标 id 或 'none'）。
// - customs：用户自定义指标（公式文本，见 CustomIndicator）。
// 默认值 = 国内通用口径（MA 5/10/20/60、BOLL 20/2、MACD 12/26/9、
// KDJ 9/3/3、RSI 6/12/24）。这些预置**以通达信公式文本**发给后端
// /formula/compute 求值（见 presetFormulas.ts），因此图表走的是通达信方言，
// 与 TA-Lib 原生指标层（easy_tdx.ta.talib_ind）有意不同的一处是 MACD 柱——
// 公式侧 (DIF-DEA)×2（国内口径），TA-Lib 侧不乘 2；其余走公式原语
// （MA/EMA/SMA/STD/最值），前缀暖机点为 null（不断线、不编造）。
// 详见 docs/cli-indicators.md。

export interface IndicatorParams {
  /** 主图叠加指标 id 列表（预置 ma/ema/boll + 自定义 id，可多选）。空 = 主图不画指标线。 */
  overlays: string[]
  /** 兼容字段：单值主图指标 id（老配置回读时迁入 overlays）。 */
  overlay: string
  /** 副图指标 id（预置 macd/kdj/rsi + 自定义 id，'none' = 不画副图）。 */
  subPane: string
  /** MA 周期列表（1-4 个，默认 5/10/20/60）。 */
  maPeriods: number[]
  /** EMA 周期对（默认 12/26）。 */
  emaFast: number
  emaSlow: number
  /** BOLL 周期与倍数（默认 20/2）。 */
  bollN: number
  bollP: number
  /** MACD 快/慢/信号（默认 12/26/9）。 */
  macdFast: number
  macdSlow: number
  macdSignal: number
  /** KDJ 周期 N（默认 9；K/D 平滑固定 3/1 国内口径）。 */
  kdjN: number
  /** RSI 周期列表（默认 6/12/24）。 */
  rsiPeriods: number[]
}

/** 用户自定义指标（公式文本走后端公式引擎计算，与预置同路径）。 */
export interface CustomIndicator {
  /** 自定义 id（`c` + 时间戳36进制，与预置 id 不重叠）。 */
  id: string
  /** 显示名（图例/chips，最多 20 字）。 */
  name: string
  kind: 'overlay' | 'sub'
  /** 通达信公式文本（输出列即图例项）。 */
  formula: string
  /** 叠加 K 线列（主图“叠加K线显示”）：4 个数值输出列名[开,高,低,收]，空 = 画线。 */
  candle: string[]
}

export const DEFAULT_INDICATOR_PARAMS: IndicatorParams = {
  overlays: ['ma'],
  overlay: 'ma',
  subPane: 'macd',
  maPeriods: [5, 10, 20, 60],
  emaFast: 12,
  emaSlow: 26,
  bollN: 20,
  bollP: 2,
  macdFast: 12,
  macdSlow: 26,
  macdSignal: 9,
  kdjN: 9,
  rsiPeriods: [6, 12, 24],
}

const STORAGE_KEY = 'easytdx.indicators'
const STORE_VERSION = 1
const MAX_CUSTOMS = 100

const MA_COLORS = ['#f0a020', '#4a9eff', '#c084fc', '#22d3ee']
const RSI_COLORS = ['#f0a020', '#4a9eff', '#c084fc']

export function maColors(i: number): string {
  return MA_COLORS[i % MA_COLORS.length]
}

export function rsiColors(i: number): string {
  return RSI_COLORS[i % RSI_COLORS.length]
}

interface StoredConfig {
  version: number
  params: IndicatorParams
  customs: CustomIndicator[]
}

/** 读裸存储（损坏/缺失回 null，由上层回默认，不抛错）。 */
function readStore(): StoredConfig | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<StoredConfig> & Partial<IndicatorParams>
    if (parsed.version === STORE_VERSION && parsed.params) {
      return {
        version: STORE_VERSION,
        params: sanitizeIndicatorParams(parsed.params),
        customs: sanitizeCustoms(parsed.customs),
      }
    }
    // 老形态：裸 IndicatorParams
    return {
      version: STORE_VERSION,
      params: sanitizeIndicatorParams(parsed),
      customs: [],
    }
  } catch {
    return null
  }
}

/** 读用户参数（损坏/缺失时回默认，不抛错）。 */
export function loadIndicatorParams(): IndicatorParams {
  return readStore()?.params ?? { ...DEFAULT_INDICATOR_PARAMS }
}

/** 读完整配置（参数 + 自定义指标）。 */
export function loadIndicatorConfig(): { params: IndicatorParams; customs: CustomIndicator[] } {
  const s = readStore()
  if (!s) return { params: { ...DEFAULT_INDICATOR_PARAMS }, customs: [] }
  return { params: s.params, customs: s.customs }
}

/** 读自定义指标列表。 */
export function loadCustoms(): CustomIndicator[] {
  return readStore()?.customs ?? []
}

/** 写用户配置（保留现有自定义指标；并通知订阅者同步刷新）。 */
export function saveIndicatorParams(p: IndicatorParams): void {
  writeStore(p, loadCustoms())
}

/** 写自定义指标列表（保留现有参数；并通知订阅者同步刷新）。 */
export function saveCustoms(customs: CustomIndicator[]): void {
  writeStore(loadIndicatorParams(), customs)
}

function writeStore(p: IndicatorParams, customs: CustomIndicator[]): void {
  try {
    const clean: StoredConfig = {
      version: STORE_VERSION,
      params: sanitizeIndicatorParams(p),
      customs: sanitizeCustoms(customs),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(clean))
  } catch {
    // 持久化失败不影响本次会话
  }
  notifyIndicatorParams()
}

type IndicatorParamsListener = (p: IndicatorParams) => void

const listeners = new Set<IndicatorParamsListener>()

/**
 * 订阅全局指标配置变更（写入后，已挂载的 K 线面板/弹窗
 * 用它把本地副本换成最新配置）。返回取消订阅函数，组件卸载时调用。
 */
export function subscribeIndicatorParams(fn: IndicatorParamsListener): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

/** 广播最新配置（刚落盘的重读一份，保证各订阅者拿到独立副本）。 */
function notifyIndicatorParams(): void {
  const fresh = loadIndicatorParams()
  for (const fn of listeners) {
    try {
      fn(fresh)
    } catch {
      // 单个监听器异常不影响其他订阅者
    }
  }
}

/** 恢复默认（仅参数+选择；自定义指标保留，不误删用户公式）。 */
export function resetIndicatorParams(): IndicatorParams {
  const d = { ...DEFAULT_INDICATOR_PARAMS }
  saveIndicatorParams(d)
  return d
}

/** 新自定义 id（`c` 前缀，与预置 id 不重叠）。 */
export function newCustomId(): string {
  return `c${Date.now().toString(36)}`
}

/** 清洗自定义列表（非法条目丢弃，最多 MAX_CUSTOMS 条）。 */
export function sanitizeCustoms(list: unknown): CustomIndicator[] {
  if (!Array.isArray(list)) return []
  const out: CustomIndicator[] = []
  for (const it of list) {
    if (out.length >= MAX_CUSTOMS) break
    if (typeof it !== 'object' || it === null) continue
    const r = it as Record<string, unknown>
    const id = typeof r.id === 'string' ? r.id.trim() : ''
    const name = typeof r.name === 'string' ? r.name.trim().slice(0, 20) : ''
    const kind = r.kind === 'sub' ? 'sub' : r.kind === 'overlay' ? 'overlay' : null
    const formula = typeof r.formula === 'string' ? r.formula.slice(0, 8000) : ''
    if (!id || !name || !kind || !formula.trim()) continue
    if (out.some((x) => x.id === id)) continue
    out.push({ id, name, kind, formula, candle: sanitizeCandle(r.candle) })
  }
  return out
}

/** 清洗叠加 K 线列（4 个非空列名[开,高,低,收]，否则空）。 */
export function sanitizeCandle(v: unknown): string[] {
  if (!Array.isArray(v) || v.length !== 4) return []
  const cols = v.map((o) => (typeof o === 'string' ? o.trim().slice(0, 64) : ''))
  return cols.every((c) => c !== '') ? cols : []
}

function int(v: unknown, fallback: number, min: number, max: number): number {
  const n = Math.round(Number(v))
  if (!Number.isFinite(n)) return fallback
  return Math.min(max, Math.max(min, n))
}

function num(v: unknown, fallback: number, min: number, max: number): number {
  const n = Number(v)
  if (!Number.isFinite(n)) return fallback
  return Math.min(max, Math.max(min, n))
}

function cleanIds(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return [...new Set(
    v.filter((o): o is string => typeof o === 'string').map((o) => o.trim()).filter((o) => o !== '' && o !== 'none'),
  )]
}

/** 越界/非法值钳制回合法范围，保证图表不炸。 */
export function sanitizeIndicatorParams(p: Partial<IndicatorParams>): IndicatorParams {
  const d = DEFAULT_INDICATOR_PARAMS
  const maPeriods = Array.isArray(p.maPeriods) && p.maPeriods.length > 0
    ? [...new Set(p.maPeriods.map((v) => int(v, 0, 2, 250)).filter((v) => v > 0))].slice(0, 4)
    : [...d.maPeriods]
  const rsiPeriods = Array.isArray(p.rsiPeriods) && p.rsiPeriods.length > 0
    ? [...new Set(p.rsiPeriods.map((v) => int(v, 0, 2, 250)).filter((v) => v > 0))].slice(0, 4)
    : [...d.rsiPeriods]
  const subPane = typeof p.subPane === 'string' && p.subPane.trim() !== '' ? p.subPane.trim() : d.subPane
  // overlays 为指标 id 多选列表（含自定义 id）；老配置（只有单个 overlay）自动迁入
  const rawOverlays = cleanIds(p.overlays)
  const single = typeof p.overlay === 'string' ? p.overlay.trim() : ''
  const overlays = rawOverlays.length > 0
    ? rawOverlays
    : single !== '' && single !== 'none'
      ? [single]
      : [...d.overlays]
  return {
    overlays,
    overlay: overlays[0] ?? 'ma',
    subPane,
    maPeriods: maPeriods.length > 0 ? maPeriods : [...d.maPeriods],
    emaFast: int(p.emaFast, d.emaFast, 2, 250),
    emaSlow: int(p.emaSlow, d.emaSlow, 2, 250),
    bollN: int(p.bollN, d.bollN, 2, 250),
    bollP: num(p.bollP, d.bollP, 0.5, 5),
    macdFast: int(p.macdFast, d.macdFast, 2, 250),
    macdSlow: int(p.macdSlow, d.macdSlow, 2, 250),
    macdSignal: int(p.macdSignal, d.macdSignal, 2, 250),
    kdjN: int(p.kdjN, d.kdjN, 2, 250),
    rsiPeriods: rsiPeriods.length > 0 ? rsiPeriods : [...d.rsiPeriods],
  }
}
