// 指标参数配置（StockKline + 指标编辑器共用）。
//
// 默认值 = 国内通用口径（MA 5/10/20/60、BOLL 20/2、MACD 12/26/9、
// KDJ 9/3/3、RSI 6/12/24），与后端 MyTT 同口径。
// 用户修改后落 localStorage（key 见 STORAGE_KEY），所有 K 线图共用同一套。

import type { Overlay, SubPane } from './components/StockKline.vue'

export interface IndicatorParams {
  /** 主图叠加指标列表（可多选：MA+EMA+BOLL 同时显示）。空 = 主图不画指标线。 */
  overlays: Overlay[]
  /** 兼容字段：单值主图指标（老配置回读时迁入 overlays）。 */
  overlay: Overlay
  subPane: SubPane
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

const MA_COLORS = ['#f0a020', '#4a9eff', '#c084fc', '#22d3ee']
const RSI_COLORS = ['#f0a020', '#4a9eff', '#c084fc']

export function maColors(i: number): string {
  return MA_COLORS[i % MA_COLORS.length]
}

export function rsiColors(i: number): string {
  return RSI_COLORS[i % RSI_COLORS.length]
}

/** 读用户配置（损坏/缺失时回默认，不抛错）。 */
export function loadIndicatorParams(): IndicatorParams {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_INDICATOR_PARAMS }
    const parsed = JSON.parse(raw) as Partial<IndicatorParams>
    return sanitizeIndicatorParams(parsed)
  } catch {
    return { ...DEFAULT_INDICATOR_PARAMS }
  }
}

/** 写用户配置。 */
export function saveIndicatorParams(p: IndicatorParams): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p))
  } catch {
    // 持久化失败不影响本次会话
  }
}

/** 恢复默认。 */
export function resetIndicatorParams(): IndicatorParams {
  const d = { ...DEFAULT_INDICATOR_PARAMS }
  saveIndicatorParams(d)
  return d
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

/** 越界/非法值钳制回合法范围，保证图表不炸。 */
export function sanitizeIndicatorParams(p: Partial<IndicatorParams>): IndicatorParams {
  const d = DEFAULT_INDICATOR_PARAMS
  const maPeriods = Array.isArray(p.maPeriods) && p.maPeriods.length > 0
    ? [...new Set(p.maPeriods.map((v) => int(v, 0, 2, 250)).filter((v) => v > 0))].slice(0, 4)
    : [...d.maPeriods]
  const rsiPeriods = Array.isArray(p.rsiPeriods) && p.rsiPeriods.length > 0
    ? [...new Set(p.rsiPeriods.map((v) => int(v, 0, 2, 250)).filter((v) => v > 0))].slice(0, 4)
    : [...d.rsiPeriods]
  const validOverlays = ['ma', 'boll', 'ema'] as const
  const subPane: IndicatorParams['subPane'] =
    p.subPane === 'macd' || p.subPane === 'kdj' || p.subPane === 'rsi' || p.subPane === 'none'
      ? p.subPane
      : d.subPane
  // overlays 为多选列表；老配置（只有单个 overlay）自动迁入，缺失则用默认
  const rawOverlays = Array.isArray(p.overlays) ? p.overlays : undefined
  const single = p.overlay as Overlay | 'none' | undefined
  const overlays: Overlay[] =
    rawOverlays !== undefined
      ? ([...new Set(rawOverlays.filter((o) => validOverlays.includes(o as never)))] as Overlay[])
      : single && single !== 'none' && validOverlays.includes(single as never)
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