// 美股观测雷达（US Market Observation Radar）——整页静态快照的数据层与口径工具。
//
// 数据形态：构建时点的一次性快照，走 GET /data/us-radar.json 拉取
// （放在 public/ 而不是 import 进主 chunk：一份 465KB 的 JSON 不该让首屏买单，
//  且这份数据本来就是「整体替换」而非「按需引用」）。
//
// 替换成真实后端接口时，只改 fetchUsRadar() 里的地址即可，页面与组件无感。
//
// 字段一律照抄快照的真实形状：缺值用 null 而不是省略字段，前端统一 ?? 兜底。
// 形如 Num 的类型 = 数据里既有数字也有 null（未触发/无数据）的那类字段。

// ── 通用 ────────────────────────────────────────────────────────────────

/** 可能为「无值」的数值：快照里既有数字也有 null，可选字段还会是 undefined */
export type Num = number | null | undefined

/** 带价格的行情行（指数/板块/宏观资产/三板斧共用） */
export interface QuoteRow {
  ticker: string
  name: string
  close: number
  d1: Num
  w1: Num
  m1: Num
  m3: Num
  vol_ratio: Num
}

/** 自选池个股行：总表、板块成分共用 */
export interface WatchRow {
  ticker: string
  theme: string
  gics: string
  close: number
  d1: Num
  w1: Num
  m1: Num
  m3: Num
  rs_1m: Num
  vol_ratio: Num
  from_hi: Num
  above50: boolean
  rsi: Num
  sup: Num
  /** 支撑位被回踩的次数。只有 1 次说明该价位没被验证过，左侧买点规则要求 ≥2 */
  sup_n?: Num
  dist_sup: Num
  res: Num
  dist_res: Num
  signals: string[]
  quality: string
  quality_score: Num
  quality_flags: string
  /** 机构持股占比 %（拥挤度用的真实披露字段） */
  inst: Num
  /** 做空占比 % */
  short: Num
}

/** 板块 ETF 行 */
export interface SectorRow extends QuoteRow {
  above50: boolean
  from_hi: Num
  /** 相对标普500 的 1 月超额 % */
  rs_1m: Num
  constituents: ConsRow[]
}

/** 题材行：顶部题材表与「题材趋势筛选」共用同一批字段名不同 */
export interface ThemeRow {
  theme: string
  n: number
  w1: Num
  m1: Num
  m3: Num
  /** 上升趋势个股占比 % */
  up_ratio: Num
  leaders: string[]
  laggers: string[]
  tickers: string[]
}

/** 量能异动行：只有信号位需要的字段 */
export interface AnomalyRow {
  ticker: string
  theme: string
  close: number
  d1: Num
  vol_ratio: Num
  signals: string[]
}

export interface NewsRow {
  title: string
  verdict: string
  impact: string
  scope: string
  tickers: string[]
  note: string
}

/** 信号位行：左侧雷达 / 兑现信号 / 信号专列共用。
 *
 * 快照里这些行实际是「观测池行」的窄子集（与 WatchRow 同源，含
 * ma5/bias5/signals/sup 等），并没有 `quality` 字段；组件只读下面声明的
 * 字段，`quality` 保留为可选仅为兼容旧快照。 */
export interface SignalRow {
  ticker: string
  theme: string
  close: number
  d1: Num
  w1: Num
  rsi: Num
  vol_ratio: Num
  quality?: string
  ma5: Num
  /** 相对 MA5 的乖离 % */
  bias5: Num
  from_hi: Num
  /** 左侧雷达独有：规律支撑位 / 触碰次数 / 距支撑 % */
  sup?: Num
  sup_n?: number
  dist_sup?: Num
}

// ── 各分区块 ────────────────────────────────────────────────────────────

export interface RadarMeta {
  asOf: string
  builtAt: string
  delay: string
  universe: string
  /** 数据源（实算构建会写入；旧静态快照没有此字段） */
  source?: string
  /** 分区名 → 缺失原因。值为 null 的分区必须有对应说明。 */
  degraded?: Record<string, string>
  /** 取数失败的标的代码 */
  failed_symbols?: string[]
}

export interface DailyBlock {
  rows: {
    ticker: string
    close: number
    d1: Num
    w1: Num
    /** 均线/RSI 由价格序列算出，必然存在，不做空值兜底 */
    ma5: number
    ma20: number
    ma50: number
    rsi: number
    /** 多头排列（close > ma5 > ma20 > ma50） */
    aligned: boolean
    from_hi: Num
    vol_ratio: Num
  }[]
  conclusion: string
  playbook: string
}

export interface LeftBlock {
  buy: SignalRow[]
  buy_spec: SignalRow[]
  watch: SignalRow[]
  rule: string
  conclusion: string
}

export interface ExitsBlock {
  overext: SignalRow[]
  dist_candle: SignalRow[]
  breakdown_vol: SignalRow[]
  panic_watch: SignalRow[]
  breakout_vol: SignalRow[]
  breakout_weak: SignalRow[]
  lost_ma5: SignalRow[]
  conclusion: string
}

export interface OptionStrike {
  strike: number
  volume: number
}

export interface OptionChain {
  ticker: string
  exp: string
  spot: number
  call_vol: number
  put_vol: number
  pcr_vol: number
  hot_calls: OptionStrike[]
  hot_puts: OptionStrike[]
  chain_date: string
  role: string
}

export interface OptionsBlock {
  note: string
  chains: OptionChain[]
  conclusion: string
}

export interface FocusStock {
  ticker: string
  name: string
  reason: string
  signals: string[]
  price: {
    close: number
    d1: Num
    w1: Num
    m1: Num
    m3: Num
    from_hi: Num
    vol_ratio: Num
  }
  technicals: {
    ma20: Num
    ma50: Num
    above50: boolean
    hi20: Num
    dist_hi20: Num
    text: string
  }
  options: {
    exp: string
    pcr_vol: number
    hot_calls: string
    hot_puts: string
    text: string
  } | null
  fundamentals: {
    fwd_pe: Num
    target_mean: Num
    target_range: string
    analysts: string
    mktcap: string
    rev_growth: string
    margin_note: string
    short_pct: Num
  }
  catalysts: string[]
  risks: string[]
  conclusion: string
}

export interface FocusBlock {
  note: string
  stocks: FocusStock[]
}

/** 质地分层的个股行（基本面快照，非行情） */
export interface QualityRow {
  ticker: string
  theme: string
  /** 质地分 0-100 */
  score: Num
  quality: string
  flags: string
  w1: Num
  m1: Num
  inst: Num
  short: Num
  rev_growth: Num
  profit_margin: Num
  /** 自由现金流（十亿美元） */
  fcf_b: Num
}

export interface QualityBlock {
  methodology: string
  summary: {
    equity_n: number
    etf_n: number
    quality_n: number
    neutral_n: number
    spec_n: number
    unknown_n: number
  }
  top: QualityRow[]
  speculative: QualityRow[]
  conclusion: string
}

/** 拥挤度按「题材」聚合（一行一个题材，不是��只票） */
export interface CrowdingRow {
  theme: string
  /** 题材内观测池只数 */
  n: number
  /** 有机构持股数据的只数 */
  inst_n: number
  /** 机构持股中位数 % */
  inst_pct: Num
  /** 高机构持仓（≥70%）公司的市值占比 % */
  high_inst_share: Num
  m3: Num
  trend_pct: Num
  vol_ratio: Num
  /** 拥挤度综合分 0-100 */
  crowding: Num
  state: string
  quality_n: number
  spec_n: number
  leaders: string[]
  tickers: string[]
}

export interface CrowdingBlock {
  methodology: string
  rows: CrowdingRow[]
  conclusion: string
}

/** 细分板块的领涨/领跌带涨跌幅，不是纯代码 */
export interface SubMove {
  ticker: string
  w1: Num
}

export interface SubsectorRow {
  name: string
  n: number
  d1: Num
  w1: Num
  m1: Num
  m3: Num
  /** 上升趋势占比 % */
  trend_pct: Num
  /** 多头排列占比 % */
  aligned_pct: Num
  vol_ratio: Num
  leaders: SubMove[]
  laggers: SubMove[]
  constituents: ConsRow[]
}

export interface DivergenceRow {
  name: string
  a_label: string
  b_label: string
  a_d1: Num
  b_d1: Num
  /** 当日利差 A−B（百分点） */
  spread1: Num
  /** 两日累计利差 */
  spread2: Num
  fired: boolean
  direction: string
}

export interface DivergenceBlock {
  rule: string
  rows: DivergenceRow[]
  conclusion: string
}

/** 涨跌归因：按标的拆解「为什么涨」 */
export interface DriverItem {
  ticker: string
  w1: Num
  /** 驱动大类，如「公司基本面」 */
  driver: string
  /** 具体发生了什么 */
  what: string
  /** 实质性判定 */
  verdict: string
}

export interface DriversBlock {
  /** 当日市场层面的归因 */
  market: string[]
  items: DriverItem[]
  conclusion: string
}

export interface GeoPrice {
  ticker: string
  name: string
  close: number
  d1: Num
  w1: Num
  m1: Num
  m3: Num
  hi: number
  lo: number
  /** 当前价在 6 月区间内的位置 % */
  pos: Num
}

export interface GeoOilBlock {
  prices: GeoPrice[]
  equities: QuoteRow[]
  timeline: { date: string; event: string }[]
  transmission: string[]
  risk_level: string
  conclusion: string
}

export interface CongressFigure {
  name: string
  role: string
  summary: string
  tickers: string[]
  stance: string
}

export interface CongressBlock {
  note: string
  figures: CongressFigure[]
  overlap: string[]
  conclusion: string
}

/** 单个信号的历史命中率 */
export interface SignalStat {
  signal: string
  samples: number
  /** 尚未走完观察窗、计入「待验证」的次数 */
  pending: number
  avg5: Num
  med5: Num
  /** 方向命中率 %（看多信号看涨命中，看空信号看跌命中） */
  hit5: Num
  direction: string
  /** 95% 置信区间半宽 */
  ci: Num
  avg10: Num
  med10: Num
  hit10: Num
  /** 样本量不足时的显式提醒（如「样本仅3次，95%置信±53pp」） */
  note?: string
}

/** 判断登记里一条已对账的判断 */
export interface LedgerRow {
  date: string
  ticker: string
  rule: string
  text: string
  /** hit = 判断正确 */
  status: 'hit' | 'miss'
  ret: Num
}

export interface ReviewBlock {
  methodology: string
  /** 近 1 个月主窗口 */
  signal_stats: SignalStat[]
  /** 滚动 3 个月参照窗口 */
  signal_stats_ref: SignalStat[]
  /** 判断登记对账统计 */
  weekly: { total: number; pending: number; scored: number; hit_rate: Num; recent: LedgerRow[] }
  snapshots: { count: number; dir: string; note: string }
  findings: string[]
  proposals: { change: string; detail: string; reason: string; status: string }[]
  conclusion: string
}

export interface RadarData {
  meta: RadarMeta
  regime: { summary: string; stance: string; breadth: string }
  index: (QuoteRow & { from_hi: Num; above50: boolean; rsi: Num; ma50_dist: Num })[]
  tnx: QuoteRow
  macro: QuoteRow[]
  sectors: SectorRow[]
  themes: ThemeRow[]
  anomalies: AnomalyRow[]
  /** 无新闻数据源时为 null——页面显示「数据源不可用」而非空白 */
  news: NewsRow[] | null
  watchlist: WatchRow[]
  /** 无期权链数据源时为 null */
  options: OptionsBlock | null
  focus: FocusBlock
  daily: DailyBlock
  left: LeftBlock
  exits: ExitsBlock
  /** 题材趋势筛选：行形状比 ThemeRow 窄（无 m1/m3/laggers），字段以快照实况为准 */
  theme_trend: {
    rows: {
      theme: string
      n: number
      w1: Num
      /** 上升 / 震荡 / 下行 */
      state: string
      pct_trend: Num
      pct_aligned: Num
      leaders: string[]
      tickers: string[]
    }[]
    conclusion: string
  }
  /** 无基本面数据源时为 null */
  quality: QualityBlock | null
  crowding: CrowdingBlock
  subsectors: { rows: SubsectorRow[]; conclusion: string }
  divergence: DivergenceBlock
  drivers: DriversBlock
  /** 无原油期货源时为 null */
  geo_oil: GeoOilBlock | null
  /** 无国会披露数据源时为 null */
  congress: CongressBlock | null
  review: ReviewBlock
}

/** 分区缺失时统一显示的占位（各 board 组件在 prop 为 null 时渲染它） */
export function degradedNote(data: RadarData | null, section: string): string {
  return data?.meta.degraded?.[section] ?? '数据源不可用'
}

// ── 格式化与口径（对应原站的 L / lt / z / Q0 / Cs）─────────────────────────

/** 百分比带号：1.23 → "+1.23%"；null/NaN → "—" */
export function fmtPct(v: Num, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)}%`
}

/** 纯数字：1.234 → "1.23"；null/NaN → "—" */
export function fmtNum(v: Num, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

/** 涨跌幅 → 颜色 class。0 走弱化色，避免满屏红绿里 0.00% 也在抢视线 */
export function dirCls(v: Num): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return 'rd-dim'
  if (v > 0) return 'rd-up'
  if (v < 0) return 'rd-down'
  return 'rd-flat'
}

/** 量比等「越大越异常」：≥1.25 高亮（与原站口径一致） */
export function volRatioCls(v: Num): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return ''
  return v >= 1.25 ? 'rd-hi' : ''
}

/** 信号码 → 中文名与颜色。原站是一张固定表，这里原样搬过来 */
export const SIGNAL_META: Record<string, { text: string; color: string }> = {
  LEFT_BUY: { text: '左侧·回踩支撑', color: 'var(--rd-cyan)' },
  LOST_MA5: { text: '跌破MA5', color: 'var(--rd-down)' },
  DIST_CANDLE: { text: '高位放量阴线', color: 'var(--rd-down)' },
  BREAKDOWN_VOL: { text: '放量破位·趋势外', color: 'var(--rd-down)' },
  PANIC_WATCH: { text: '恐慌破位·观察', color: 'var(--rd-amber)' },
  BREAKOUT_VOL: { text: '放量突破·趋势内', color: 'var(--rd-up)' },
  BREAKOUT_WEAK: { text: '非趋势突破·存疑', color: 'var(--rd-dim)' },
  OVEREXT: { text: '超买乖离·一等风控', color: 'var(--rd-amber)' },
}

/** PCR 分档判定：≤0.5 强多头 / ≤0.75 偏多头 / ≤1 均衡 / >1 偏空头。
 *  边界值归入更保守的一档（0.5 算强多头、1.0 算均衡），保证同一条数据在任何
 *  位置渲染出的分档一致。 */
export function pcrVerdict(pcr: number): { label: string; cls: string } {
  if (!Number.isFinite(pcr)) return { label: '数据缺失', cls: 'rd-dim' }
  if (pcr <= 0.5) return { label: '强多头', cls: 'rd-up' }
  if (pcr <= 0.75) return { label: '偏多头', cls: 'rd-up' }
  if (pcr <= 1) return { label: '均衡', cls: 'rd-amber' }
  return { label: '偏空头', cls: 'rd-down' }
}

/** 质地标签 → 颜色。与原站 z0 一致：优质=青、中性=中性色、情绪/投机=琥珀 */
export const QUALITY_COLOR: Record<string, string> = {
  优质: 'var(--rd-cyan)',
  中性: 'var(--text-muted)',
  '情绪/投机': 'var(--rd-amber)',
  ETF: 'var(--text-dim)',
  数据不足: 'var(--text-dim)',
}

/** 板块成分行的精简形状（比总表少很多列：板块下钻不需要支撑/压力/机构持股） */
export interface ConsRow {
  ticker: string
  theme: string
  close: number
  d1: Num
  w1: Num
  m1: Num
  rsi: Num
  vol_ratio: Num
  signals: string[]
  quality: string
}

/**
 * 涨跌归因的「性质判定」→ 颜色与简写。
 *
 * 原站是一张按完整字符串查表的固定字典，但快照里实际出现的 8 个判定值里有 7 个
 * 不在表内（带括号后缀的那些），于是全部落到兜底灰——这一列等于没上色。
 * 这里保留原表逐项照抄，再补一条前缀规则兜底：实质性→青、情绪→琥珀、
 * 宏观→中性色。判定词本来就分这三类，按前缀归并比逐条穷举更耐改。
 */
const VERDICT_MAP: Record<string, { label: string; color: string }> = {
  实质性: { label: '实质性', color: 'var(--rd-cyan)' },
  '实质性(资金流)': { label: '实质·资金流', color: 'var(--rd-cyan)' },
  实质性利空: { label: '实质利空', color: 'var(--rd-down)' },
  '轮动+情绪为主': { label: '轮动+情绪', color: 'var(--rd-amber)' },
  '情绪/轮动': { label: '情绪/轮动', color: 'var(--rd-amber)' },
  '纯Beta+情绪': { label: '纯Beta+情绪', color: 'var(--rd-amber)' },
  宏观驱动: { label: '宏观驱动', color: 'var(--text-muted)' },
  '宏观(油价)': { label: '宏观·油价', color: 'var(--text-muted)' },
}

export function driverVerdict(v: string): { label: string; color: string } {
  const hit = VERDICT_MAP[v]
  if (hit) return hit
  if (v.startsWith('实质性')) return { label: '实质性', color: 'var(--rd-cyan)' }
  if (v.startsWith('情绪')) return { label: '情绪为主', color: 'var(--rd-amber)' }
  if (v.startsWith('宏观')) return { label: '宏观驱动', color: 'var(--text-muted)' }
  return { label: v, color: 'var(--text-muted)' }
}

/** 看涨成交占比（0-100），驱动 call/put 比例条 */
export function callSharePct(callVol: number, putVol: number): number {
  const total = callVol + putVol
  return total > 0 ? (callVol / total) * 100 : 50
}

/** 成交量紧凑写法：134059 → "134.1k" */
export function fmtVolK(v: number): string {
  if (!Number.isFinite(v)) return '—'
  return `${(v / 1e3).toFixed(1)}k`
}

/** 顶栏锚点表：锚点 id 与各 Section 的 id 对应 */
export const RADAR_NAV: [string, string][] = [
  ['#daily', '三板斧'],
  ['#geo', '油价地缘'],
  ['#subsectors', '细分行业'],
  ['#drivers', '驱动'],
  ['#themes', '题材'],
  ['#crowding', '拥挤度'],
  ['#congress', '国会交易'],
  ['#left', '左侧'],
  ['#focus', 'INTC'],
  ['#options', '期权'],
  ['#news', '新闻'],
  ['#review', '复盘'],
  ['#watchlist', '自选股'],
]

// ── 取数 ────────────────────────────────────────────────────────────────

/**
 * 拉取整份快照。走 public/ 下的静态 JSON：这份数据是「整体替换」的快照而不是
 * 按需接口，放进主 chunk 只会让所有页面为 465KB 买单。
 * 换成后端接口时只改这里的地址。
 */
export async function fetchUsRadar(signal?: AbortSignal): Promise<RadarData> {
  const resp = await fetch(`${import.meta.env.BASE_URL}data/us-radar.json`, { signal })
  if (!resp.ok) {
    throw new Error(`雷达快照加载失败：HTTP ${resp.status}`)
  }
  return (await resp.json()) as RadarData
}