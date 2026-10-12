// 预置技术指标的公式化定义（技术指标管理：六组预置 = 锁定的通达信公式）。
//
// 每条预置 = 参数 → 公式文本（与后端 test_formula.py::test_preset_* 锁定的
// 文本结构一致，参数不同、结构相同；改动任一侧请同步另一侧）。
// 计算走后端公式引擎（inline 模式，前端把已展示的 K 线随公式 POST），
// 前端 indicators.ts 本地计算已退役。

import { maColors, rsiColors, type IndicatorParams } from './indicatorParams.ts'

export type PresetKind = 'overlay' | 'sub'

export interface PresetDef {
  /** 与选择态 id 一一对应（预置 ma/ema/boll/macd/kdj/rsi + 自定义 id）。 */
  id: string
  name: string
  /** K 线标题栏 chips 上的短标签。 */
  short: string
  kind: PresetKind
  /** 预置锁定：公式文本不可改，只能调参。 */
  locked: true
  /** 参数 → 公式文本（输出列名即图例键，见 displayName）。 */
  buildFormula: (p: IndicatorParams) => string
  /** 参数 → 输出列名列表（与 buildFormula 的输出顺序一致，供服务端序列化）。 */
  columns: (p: IndicatorParams) => string[]
  /** 输出列 → 图例显示名。 */
  displayName: (col: string) => string
  /** 输出列 → 线色（index 为该列在公式输出中的序号）。 */
  colorFor: (col: string, index: number) => string
  /** 输出列 → 是否虚线。 */
  dashedFor: (col: string) => boolean
  /** 输出列 → 是否画 bar（副图）。 */
  isBar: (col: string) => boolean
}

function intList(text: string): number[] {
  return [...new Set(
    text
      .split(/[,，\s]+/)
      .map((s) => Math.round(Number(s)))
      .filter((n) => Number.isFinite(n) && n >= 2 && n <= 250),
  )].slice(0, 4)
}

export const PRESETS: PresetDef[] = [
  {
    id: 'ma',
    name: 'MA 均线',
    short: 'MA',
    kind: 'overlay',
    locked: true,
    buildFormula: (p) =>
      p.maPeriods.map((n) => `MA${n}: MA(C,${n});`).join('\n'),
    columns: (p) => p.maPeriods.map((n) => `MA${n}`),
    displayName: (col) => col,
    colorFor: (_col, i) => maColors(i),
    dashedFor: () => false,
    isBar: () => false,
  },
  {
    id: 'ema',
    name: 'EMA 指数平均',
    short: 'EMA',
    kind: 'overlay',
    locked: true,
    buildFormula: (p) => `EMA${p.emaFast}: EMA(C,${p.emaFast});\nEMA${p.emaSlow}: EMA(C,${p.emaSlow});`,
    columns: (p) => [`EMA${p.emaFast}`, `EMA${p.emaSlow}`],
    displayName: (col) => col,
    colorFor: (_col, i) => (i === 0 ? '#22d3ee' : '#c084fc'),
    dashedFor: () => false,
    isBar: () => false,
  },
  {
    id: 'boll',
    name: 'BOLL 布林带',
    short: 'BOLL',
    kind: 'overlay',
    locked: true,
    buildFormula: (p) =>
      `BOLL_MID: MA(C,${p.bollN});\n` +
      `BOLL_UPPER: BOLL_MID+${p.bollP}*STD(C,${p.bollN});\n` +
      `BOLL_LOWER: BOLL_MID-${p.bollP}*STD(C,${p.bollN});`,
    columns: () => ['BOLL_MID', 'BOLL_UPPER', 'BOLL_LOWER'],
    displayName: (col) =>
      ({ BOLL_MID: 'BOLL中轨', BOLL_UPPER: 'BOLL上轨', BOLL_LOWER: 'BOLL下轨' })[col] ?? col,
    colorFor: (col) => (col === 'BOLL_MID' ? '#f0a020' : '#94a3b8'),
    dashedFor: (col) => col !== 'BOLL_MID',
    isBar: () => false,
  },
  {
    id: 'macd',
    name: 'MACD',
    short: 'MACD',
    kind: 'sub',
    locked: true,
    buildFormula: (p) =>
      `DIF: EMA(C,${p.macdFast})-EMA(C,${p.macdSlow});\n` +
      `DEA: EMA(DIF,${p.macdSignal});\n` +
      `MACD_HIST: (DIF-DEA)*2;`,
    columns: () => ['DIF', 'DEA', 'MACD_HIST'],
    displayName: (col) => ({ DIF: 'DIF', DEA: 'DEA', MACD_HIST: 'MACD' })[col] ?? col,
    colorFor: (col) => (col === 'DIF' ? '#f0a020' : col === 'DEA' ? '#4a9eff' : '#f0a020'),
    dashedFor: () => false,
    isBar: (col) => col === 'MACD_HIST',
  },
  {
    id: 'kdj',
    name: 'KDJ',
    short: 'KDJ',
    kind: 'sub',
    locked: true,
    buildFormula: (p) =>
      `RSV := (C-LLV(L,${p.kdjN}))/(HHV(H,${p.kdjN})-LLV(L,${p.kdjN}))*100;\n` +
      `K: SMA(RSV,3,1);\nD: SMA(K,3,1);\nJ: 3*K-2*D;`,
    columns: () => ['K', 'D', 'J'],
    displayName: (col) => col,
    colorFor: (col) => (col === 'K' ? '#f0a020' : col === 'D' ? '#4a9eff' : '#c084fc'),
    dashedFor: () => false,
    isBar: () => false,
  },
  {
    id: 'rsi',
    name: 'RSI',
    short: 'RSI',
    kind: 'sub',
    locked: true,
    buildFormula: (p) =>
      `UD := C-REF(C,1);\n` +
      p.rsiPeriods
        .map((n) => `RSI${n}: SMA(MAX(UD,0),${n},1)/SMA(ABS(UD),${n},1)*100;`)
        .join('\n'),
    columns: (p) => p.rsiPeriods.map((n) => `RSI${n}`),
    displayName: (col) => col,
    colorFor: (_col, i) => rsiColors(i),
    dashedFor: () => false,
    isBar: () => false,
  },
]

export function presetById(id: string): PresetDef | undefined {
  return PRESETS.find((p) => p.id === id)
}

/** 解析逗号分隔的周期输入（与旧参数表单 setMa/setRsi 同口径）。 */
export function parsePeriods(text: string): number[] {
  return intList(text)
}
