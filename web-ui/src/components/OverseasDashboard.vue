<script setup lang="ts">
// 外盘看板（港股/美股）：指数卡 + 代码搜索 + K线面板 + A 股同款六宫格
//（市场统计 / 市场情绪 / 涨跌分布 / 行业板块 / 概念板块 / 排行榜）。
//
// 与 A 股看板（DashboardView 内的 A 股分支）是平级关系：港美股无涨跌停制度，
// 故无「涨停雷达」；其余卡片找等价口径——
// 统计/分布/排行走全市场榜单快照（/overseas/rank，含 Top30 + 22 桶分布）；
// 行业/概念走板块列表（/board-mac/list，HK_HY/HK_GN/US_HY/US_GN）；
// 情绪雷达的量能维无港美股成交数据，固定中性 50，其余三维正常计算。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  fetchBars,
  fetchBoards,
  fetchMinute,
  fetchOverseasRank,
  fetchQuotes,
  firstPreClose,
  formatError,
  searchOverseasSymbols,
  type OverseasRank,
  type OverseasSymbol,
} from '../api'
import { dirClass, fmt2, fmtAmount, fmtPctSigned, fmtVolShares } from '../format'
import { loadIndicatorParams, saveIndicatorParams, subscribeIndicatorParams, type IndicatorParams } from '../indicatorParams'
import { enabledIndices } from '../indexIndicators'
import {
  INDEX_ETF_PROXY,
  inUsSessionFilter,
  isUsDst,
  MARKET_DEFAULT_INDEX,
  marketLabel,
  toHhmm,
  US_SESSION_FILTERS,
  type Market,
  type USSessionFilter,
} from '../market'
import { useQuoteStore } from '../stores/quotes'
import type { Bar, BoardRow, Category, MinutePoint, SecurityQuote } from '../types'
import { createSeqGuard } from '../utils/asyncGuard'
import BoardDialog from './BoardDialog.vue'
import IndicatorChips from './IndicatorChips.vue'
import IntradayChart from './IntradayChart.vue'
import MoodRadar from './MoodRadar.vue'
import SourceBadge from './SourceBadge.vue'
import Sparkline from './Sparkline.vue'
import StockDialog from './StockDialog.vue'
import StockKline from './StockKline.vue'
import UsOptionsRail from './UsOptionsRail.vue'

const props = defineProps<{ market: Market }>()

const quoteStore = useQuoteStore()

/** 是否显示期权右侧栏：只给美股模式挂，港股没有对应期权链口径，硬挂会变成噪音。 */
const showOptionsRail = computed(() => props.market === 'US')

/** 指数条（参照沪市看板三卡：价格 + 涨跌幅 + 迷你分时，点击切 K 线面板）。 */
// 指数条取自「指数设置」页配置（enabledIndices 内部读 localStorage，
// 每次访问重新读，便于设置页改动后无需刷新即可生效）。
const stripIndices = computed(() =>
  enabledIndices(props.market).map((x) => ({ market: x.market, code: x.code, name: x.name })),
)

const stripSparks = ref(new Map<string, number[]>())
const stripSparkBase = ref(new Map<string, number>())

function stripSymbol(idx: { market: string; code: string }): string {
  return `${idx.market}${idx.code}`
}

function stripQuote(idx: { market: string; code: string }) {
  return quoteStore.getQuote(stripSymbol(idx))
}

function stripPct(idx: { market: string; code: string }): number | null {
  const q = stripQuote(idx)
  if (!q?.price || !q.pre_close) return null
  return (q.price / q.pre_close - 1) * 100
}

/**
 * 组件是否仍挂载。指数条迷你分时是串行多请求，卸载后必须停止后续请求且不再
 * 写状态；`onBeforeUnmount` 里置 false。
 */
let alive = true

async function loadStripSparks() {
  // 指数条价格走 SSE，但休市时推送间隔 60s，首屏会长时间显示 “—”。挂载时先
  // 主动拉一次报价兜底（与 focal 的 SSE 兜底同理），并把分时序列画成迷你走势。
  try {
    const qs = await fetchQuotes(stripIndices.value.map((i) => ({ market: i.market, code: i.code })))
    quoteStore.seedQuotes(qs)
  } catch {
    // 拉取失败就等 SSE 推送
  }
  for (const idx of stripIndices.value) {
    // 组件已卸载：停止后续串行请求，也不再写响应式状态（旧实现会一路拉完
    // 并在卸载后继续写 stripSparks / stripSparkBase）。
    if (!alive) return
    try {
      // 美股/港股**指数**在 MAC 扩展栈没有分时（只回 1 根 qq 快照），直接
      // fetchMinute(指数代码) 是空——迷你分时永远画不出来。改走 INDEX_ETF_PROXY
      // 对应的 ETF 分时：走势形态一致（恒生→02800、标普→SPY、纳指→QQQ、道指→DIA）。
      // 代理分时的点位是 ETF 而非指数，因此基准（Sparkline 昨收线）也必须用
      // ETF 分时首价，而不是指数报价的 pre_close——两者量级不同，混用会让
      // 涨跌着色和虚线基准都错位。
      const proxy = INDEX_ETF_PROXY[idx.code]
      const target = proxy ? { market: proxy.market, code: proxy.code } : idx
      const pts = await fetchMinute(target.market, target.code)
      if (!alive) return
      if (pts.length > 0) {
        const key = stripSymbol(idx)
        stripSparks.value.set(key, pts.map((p) => p.price))
        stripSparkBase.value.set(key, pts[0].price)
      }
    } catch {
      // 单指数失败跳过
    }
  }
}

function pickIndex(idx: { market: string; code: string; name: string }) {
  focal.value = { ...idx }
  loadFocal()
}

// ── 当前标的（默认该市场指数，可搜索切换） ──────────────────────────────────

interface Focal {
  market: string
  code: string
  name: string
}

const focal = ref<Focal>({ ...MARKET_DEFAULT_INDEX[props.market] })

watch(
  () => props.market,
  (m) => {
    focal.value = { ...MARKET_DEFAULT_INDEX[m] }
    searchText.value = ''
    searchResults.value = []
    // 切市场重置视图：美股默认「盘中」价格面板，港股/其它默认「全部」（日K）
    sessionFilter.value = m === 'US' ? 'open' : 'all'
    minuteMode.value = sessionFilter.value !== 'all'
    restQuote.value = null
    if (minuteMode.value) {
      void loadFocalQuote()
      void loadSessionMinute()
    }
    else loadFocal()
  },
)

// ── 搜索 ────────────────────────────────────────────────────────────────────

const searchText = ref('')
const searchResults = ref<OverseasSymbol[]>([])
const searchError = ref('')
const searching = ref(false)
let searchTimer = 0

function onSearchInput() {
  window.clearTimeout(searchTimer)
  const kw = searchText.value.trim()
  if (!kw) {
    searchResults.value = []
    return
  }
  searchTimer = window.setTimeout(async () => {
    searching.value = true
    searchError.value = ''
    try {
      const resp = await searchOverseasSymbols(props.market, kw, 12)
      searchResults.value = resp.data
    } catch (e) {
      searchError.value = formatError(e)
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function pickSymbol(s: OverseasSymbol) {
  focal.value = { market: s.market, code: s.code, name: s.name }
  searchText.value = ''
  searchResults.value = []
  minuteMode.value = false
  sessionFilter.value = 'all'
  loadFocal()
}

// ── 当前标的行情（K线 + 报价 + 迷你分时） ────────────────────────────────────

const bars = ref<Bar[]>([])
const barsError = ref('')
const barsLoading = ref(false)

// 序号守卫：外盘走扩展栈（7727）延迟波动更大，日K/分钟K/时段切换互相覆盖的
// 概率高于 A 股；切标的与切周期都可能连点。
const barsGuard = createSeqGuard()

const kCategory = ref<Category>('DAY')
const K_CATS: Array<{ value: Category; label: string }> = [
  { value: 'DAY', label: '日K' },
  { value: 'WEEK', label: '周K' },
  { value: 'MONTH', label: '月K' },
  // 分钟周期：港股指数已修复（后端从当日分时聚合，无历史分钟K，仅当日）；
  // 美股指数分钟K数据源受限（见 _http_bars / INDEX_ETF_PROXY 说明），
  // 少数周期可能只有当日几根，K线不足时前端会提示。
  { value: 'MIN_15', label: '15分' },
  { value: 'MIN_30', label: '30分' },
  { value: 'MIN_60', label: '60分' },
  { value: 'MIN_120', label: '120分' },
  { value: 'MIN_240', label: '240分' },
]

// ── 美股时段视图（「盘中」= 纯价格面板，不画曲线）────────────────────────────
// 只保留「全部」（日/周/月 K 线）与「盘中」（价格面板）两档。盘前 / 盘后 /
// 夜盘在 TDX 与东财免费接口下均无数据（实测美股分钟线仅美东 09:30–16:00），
// 摆出来只会让人点了看到空白，故移除。
//
// 价格面板直接读实时报价（SSE store 优先、REST 兜底），不取分时序列、
// 不画曲线，只呈现价格与量额。
const sessionFilter = ref<USSessionFilter>(props.market === 'US' ? 'open' : 'all')
const minuteMode = ref(sessionFilter.value !== 'all')

/** REST 兜底的报价（非自选股不会进 SSE store，需要单独拉一次）。 */
const restQuote = ref<SecurityQuote | null>(null)

/** 当前标的实时报价：SSE store 优先，其次 REST 兜底。 */
const focalQuote = computed<SecurityQuote | null>(
  () => quoteStore.getQuote(`${focal.value.market}${focal.value.code}`) ?? restQuote.value,
)

/** 主动拉一次报价填入兜底；失败静默——价格面板缺数据显示「—」，不弹错误条。 */
async function loadFocalQuote() {
  restQuote.value = null
  try {
    const symbol = `${focal.value.market}${focal.value.code}`
    const rows = await fetchQuotes([
      { market: focal.value.market, code: focal.value.code },
    ])
    restQuote.value = rows.find((r) => r.symbol === symbol) ?? rows[0] ?? null
  } catch {
    restQuote.value = null
  }
}

/** 「盘中」档的分时点（已按盘中时段裁剪）。 */
const sessionPoints = ref<MinutePoint[]>([])

/** 分时以 ETF 代理时的标注（如「QQQ」）；空 = 指数原生分时（不存在，但保留语义）。 */
const sessionProxy = ref('')

/** 分时图昨收基准（涨跌着色用）。 */
// 焦点是指数、分时走 ETF 代理时，focalQuote 是**指数**报价，其 pre_close
// （如道指 ~50000）和代理 ETF 分时点（如 DIA ~400）量级不同，直接当基准会
// 毁掉 y 轴对称。因此真正的基准由 sessionPreClose 提供，加载分时时按
// 「走代理取 ETF 昨收 / 不走代理取焦点昨收」赋值，见其定义。
//（原 focalPreClose computed 已移除，避免与 sessionPreClose 两套基准打架。）

/**
 * 分时图真正的昨收基准。
 *
 * 焦点是**指数**且分时走 ETF 代理时，分时点量级是 ETF（如 DIA ~400），而
 * focalPreClose 是指数昨收（如道指 ~50000）——把 50000 当基准画 400±5 的分时，
 * y 轴单侧幅度会被 base 撑成巨大，价格线压成一条贴边的平线，比例彻底失衡。
 * 因此代理分时的昨收必须取**代理 ETF** 的 pre_close（IndexTrend 组件同样这么处理）。
 * 非代理（个股原生分时）回退到 focalPreClose。
 */
const sessionPreClose = ref<number | null>(null)

/**
 * 取当日分时，只保留「盘中」时段（美东 09:30–16:00 = 北京 21:30–04:00）。
 *
 * 分时点的时间只有 `HH:MM:SS`，先经 `toHhmm` 归一化再比对窗口——直接
 * 截取子串在带日期的格式下会把整段过滤成空。
 */
async function loadSessionMinute() {
  const my = barsGuard.next()
  barsLoading.value = true
  barsError.value = ''
  sessionPoints.value = []
  sessionProxy.value = ''
  // 分时昨收基准也随切换清空，避免上一个标的（尤其上一只代理 ETF）的
  // 昨收残留到新分时加载完成，造成短期的 y 轴对称基准错位。
  sessionPreClose.value = null
  try {
    // 真指数（道指/纳指/标普）在 MAC 数据源里没有分时行情（只回 1 根 qq 快照），
    // 直接展示就是空白/一个点。这里用对应 ETF 的分时**代理渲染**——走势形态一致，
    // 但点位不是指数本身，必须通过 sessionProxy 在图上明示。
    const proxy = INDEX_ETF_PROXY[focal.value.code]
    const target = proxy ? { market: proxy.market, code: proxy.code } : focal.value
    const pts = await fetchMinute(target.market, target.code)
    if (barsGuard.stale(my)) return
    // 代理分时的昨收基准必须取代理 ETF 的 pre_close（与分时点同量级），
    // 不能拿指数 quote 的昨收——否则 y 轴对称的基准错位，见 sessionPreClose 注释。
    // 分时行自带 pre_close（外盘 tdx 分时）时直接用，省掉一次 /quotes；无该列再回落到报价。
    const fromMinute = firstPreClose(pts)
    if (proxy) {
      if (fromMinute !== null) {
        sessionPreClose.value = fromMinute
      } else {
        try {
          const q = await fetchQuotes([{ market: target.market, code: target.code }])
          sessionPreClose.value = q[0]?.pre_close ?? null
        } catch {
          sessionPreClose.value = null
        }
      }
    } else {
      sessionPreClose.value = fromMinute ?? focalQuote.value?.pre_close ?? null
    }
    if (pts.length === 0) throw new Error('无分时数据')
    const dst = isUsDst()
    sessionPoints.value = pts.filter((p) => {
      const t = toHhmm(p.datetime)
      return t !== '' && inUsSessionFilter(t, 'open', dst)
    })
    if (sessionPoints.value.length === 0) {
      barsError.value = proxy
        ? `${proxy.label}（代理）也暂无分时数据，该标的当日可能无盘中成交`
        : '盘中时段暂无分时数据（该标的当日无盘中成交）'
      return
    }
    if (proxy) sessionProxy.value = proxy.label
  } catch (e) {
    if (barsGuard.stale(my)) return
    barsError.value = formatError(e)
  } finally {
    if (!barsGuard.stale(my)) barsLoading.value = false
  }
}

function pickSession(s: USSessionFilter) {
  sessionFilter.value = s
  // 切档清掉上一个视图的错误（日K 失败过的红条不该糊在分时/盘口上）
  barsError.value = ''
  if (s === 'all') {
    minuteMode.value = false
    sessionPoints.value = []
    sessionProxy.value = ''
    loadFocal()
    return
  }
  minuteMode.value = true
  void loadFocalQuote()
  void loadSessionMinute()
}

/** 价格面板的涨跌幅（无昨收时返回 null，由 UI 显示「—」）。 */
const focalPct = computed(() => {
  const q = focalQuote.value
  if (!q?.price || !q.pre_close) return null
  return (q.price / q.pre_close - 1) * 100
})

// ── 五档盘口 ────────────────────────────────────────────────────────────────
// A 股标准协议 20 个档位列齐全；扩展栈（港美股）只回了 16 个（缺 vol2/vol5），
// 且休市时全为 0。**0 价不可能是真实挂单**，一律按「无」处理并显示「—」，
// 而不是画一排 0.00 让人误以为盘口坏了。

function quoteRec(): Record<string, number | null> | null {
  return focalQuote.value as unknown as Record<string, number | null> | null
}

/** 档位价格文本；无挂单返回 null。 */
function lvPrice(side: 'bid' | 'ask', lv: number): string | null {
  const v = quoteRec()?.[`${side}${lv}`]
  return typeof v === 'number' && v > 0 ? fmt2(v) : null
}

/** 档位挂单量文本；无挂单返回 null。港美股单位是股、A 股是手。 */
function lvVol(side: 'bid' | 'ask', lv: number): string | null {
  const v = quoteRec()?.[`${side}_vol${lv}`]
  if (typeof v !== 'number' || v <= 0) return null
  return fmtVolShares(v)
}

/** 是否有任一有效档位（决定盘口区显示表格还是「休市无挂单」）。 */
const hasDepth = computed(() => {
  for (let lv = 1; lv <= 5; lv += 1) {
    if (lvPrice('bid', lv) !== null || lvPrice('ask', lv) !== null) return true
  }
  return false
})

/** 日/周/月 K 线。 */
const shownBars = computed(() => bars.value)

/** 当前 K 线数据源（bars 首根的 source 标记）。 */
const barsSource = computed(() => bars.value[0]?.source)

// ── 指标参数（全局共用，技术指标设置页写入后这里同步） ────────────────
const indParams = ref<IndicatorParams>(loadIndicatorParams())
const unsubscribeInd = subscribeIndicatorParams((p) => {
  indParams.value = { ...p }
})
onBeforeUnmount(unsubscribeInd)

/** 主图叠加多选 + 副图切换：写回全局指标配置（各 K 线图/技术指标页共用）。 */
function toggleOverlay(v: string) {
  const cur = indParams.value.overlays ?? []
  const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
  indParams.value.overlays = next
  indParams.value.overlay = next[0] ?? 'ma'
  saveIndicatorParams(indParams.value)
}

function setSubPane(v: string) {
  indParams.value.subPane = v
  saveIndicatorParams(indParams.value)
}
const dialog = ref<Focal | null>(null)

/** 美股真指数 → 追踪 ETF（指数 K 线只有快照时一键切换看完整 K 线）。 */
const US_ETF_PROXY: Record<string, { market: string; code: string; name: string }> = {
  DJI: { market: 'US', code: 'DIA', name: '道指ETF' },
  IXIC: { market: 'US', code: 'QQQ', name: '纳指100ETF' },
  SPX: { market: 'US', code: 'SPY', name: '标普500ETF' },
}

/** K 线是否不足（「盘中」价格面板与 K 线无关，直接放行）。 */
const barsTooFew = computed(
  () => !minuteMode.value && !barsLoading.value && !barsError.value && shownBars.value.length < 2,
)
const etfProxy = computed(() =>
  props.market === 'US' ? (US_ETF_PROXY[focal.value.code] ?? null) : null,
)

async function loadFocal() {
  const my = barsGuard.next()
  barsLoading.value = true
  barsError.value = ''
  try {
    const fetched = await fetchBars(
      focal.value.market,
      focal.value.code,
      kCategory.value,
      undefined,
      undefined,
    )
    if (barsGuard.stale(my)) return
    if (fetched.length === 0) throw new Error('无K线数据（可能为新股或代码有误）')
    bars.value = fetched
  } catch (e) {
    if (barsGuard.stale(my)) return
    bars.value = []
    barsError.value = formatError(e)
  } finally {
    if (!barsGuard.stale(my)) barsLoading.value = false
  }
}

watch(kCategory, () => {
  minuteMode.value = false
  sessionFilter.value = 'all'
  loadFocal()
})

// ── 榜单（building 轮询） ───────────────────────────────────────────────────

const rank = ref<OverseasRank | null>(null)
const rankError = ref('')
const rankTab = ref<'gainers' | 'losers' | 'by_amount' | 'by_vol'>('gainers')
const RANK_TABS = [
  { value: 'gainers', label: '涨幅' },
  { value: 'losers', label: '跌幅' },
  { value: 'by_amount', label: '成交额' },
  { value: 'by_vol', label: '成交量' },
] as const

let rankTimer = 0

async function loadRank() {
  try {
    const r = await fetchOverseasRank(props.market)
    rank.value = r
    rankError.value = ''
    // building 中继续轮询；ready 后停（靠定时器周期性刷新）
    if (r.status === 'building') {
      window.clearTimeout(rankTimer)
      rankTimer = window.setTimeout(loadRank, 2000)
    }
  } catch (e) {
    rankError.value = formatError(e)
  }
}

const rankRows = computed(() => {
  if (!rank.value || rank.value.status !== 'ready') return []
  const direct = rank.value[rankTab.value]
  if (direct && direct.length > 0) return direct
  // 老后端无 by_vol 字段时，前端用 by_amount 按 vol 现排兜底（Top30）
  if (rankTab.value === 'by_vol' && rank.value.by_amount) {
    return [...rank.value.by_amount]
      .sort((a, b) => Number(b.vol ?? 0) - Number(a.vol ?? 0))
      .slice(0, 30)
  }
  return direct ?? []
})

function openRow(market: string, code: string, name: string) {
  dialog.value = { market, code, name }
}

const breadth = computed(() => {
  const r = rank.value
  if (!r || r.status !== 'ready' || !r.total) return null
  const total = r.total || 1
  return {
    up: ((r.up ?? 0) / total) * 100,
    flat: ((r.flat ?? 0) / total) * 100,
    down: ((r.down ?? 0) / total) * 100,
  }
})

// ── 市场情绪（榜单涨跌比 + 默认指数 K 线合成四维雷达） ───────────────────────
// 量能维无港美股全市场成交数据，固定中性 50；动量/趋势取默认指数日 K。

const idxBars = ref<Bar[]>([])

async function loadIndexContext() {
  try {
    const d = MARKET_DEFAULT_INDEX[props.market]
    idxBars.value = (await fetchBars(d.market, d.code, 'DAY')).slice(-60)
  } catch {
    idxBars.value = []
  }
}

const radarValues = computed(() => {
  const r = rank.value
  let profit = 50
  if (r && r.status === 'ready' && (r.up ?? 0) + (r.down ?? 0) > 0) {
    const ratio = (r.up ?? 0) / Math.max(r.down ?? 0, 1)
    profit = 50 + Math.tanh(Math.log(ratio)) * 50
  }
  const volume = 50
  const sh = idxBars.value
  let momentum = 50
  if (sh.length >= 6) {
    const ret5 = (sh.at(-1)!.close / sh.at(-6)!.close - 1) * 100
    momentum = Math.min(100, Math.max(0, 50 + ret5 * 10))
  }
  let trend = 50
  if (sh.length >= 20) {
    const ma20 = sh.slice(-20).reduce((a, b) => a + b.close, 0) / 20
    trend = Math.min(100, Math.max(0, 50 + (sh.at(-1)!.close / ma20 - 1) * 1000))
  }
  return { profit, volume, momentum, trend }
})

const moodScore = computed(() => {
  const v = radarValues.value
  return Math.round(((v.profit + v.volume + v.momentum + v.trend) / 4) * 10) / 10
})

function moodLabel(score: number): string {
  if (score >= 70) return '亢奋'
  if (score >= 57) return '偏暖'
  if (score >= 43) return '均衡'
  if (score >= 30) return '偏冷'
  return '冰点'
}

// ── 涨跌分布直方图（榜单快照自带 22 桶，无需全量行下发） ─────────────────────

const BUCKETS = [
  '≤-10',
  ...Array.from({ length: 20 }, (_, i) => {
    const v = -10 + i
    return v === 0 ? '0' : `${v > 0 ? '+' : ''}${v}`
  }),
  '≥10',
]

const distCounts = computed<number[] | null>(() => {
  const r = rank.value
  if (!r || r.status !== 'ready' || !r.dist_counts || r.dist_counts.length === 0) return null
  return r.dist_counts
})
const distTotal = computed(() => rank.value?.dist_total ?? 0)

/** 桶区间文案（如 "-5% ~ -4%"；两端为 ≤-10% / ≥+10%）。 */
function bucketRange(i: number): string {
  if (i === 0) return '≤ -10%'
  if (i === BUCKETS.length - 1) return '≥ +10%'
  const v = -10 + (i - 1)
  if (v === 0) return '0 ~ +1%'
  const fmt = (x: number) => (x > 0 ? `+${x}%` : `${x}%`)
  return `${fmt(v)} ~ ${fmt(v + 1)}`
}

/** 桶内家数占比。 */
function bucketShare(count: number): string {
  const total = distTotal.value
  return total > 0 ? `${((count / total) * 100).toFixed(1)}%` : '-'
}

/** 分布柱高（相对最大桶）。 */
function distHeight(count: number): string {
  const max = Math.max(...(distCounts.value ?? [1]), 1)
  return `${Math.max(2, (count / max) * 100)}%`
}

function distColor(i: number): string {
  if (i === 0) return 'var(--down)'
  if (i === BUCKETS.length - 1) return 'var(--up)'
  if (i === 11) return 'var(--text-dim)'
  return i < 11 ? 'var(--down)' : 'var(--up)'
}

/** 涨跌分布 hover 浮窗：跟随鼠标，超界自动贴边。 */
const hoverBucket = ref(-1)
const popX = ref(0)
const popY = ref(0)
const distChartEl = ref<HTMLElement | null>(null)

function onDistMove(e: MouseEvent) {
  const host = distChartEl.value
  if (!host) return
  const rect = host.getBoundingClientRect()
  popX.value = Math.min(Math.max(e.clientX - rect.left + 14, 0), rect.width - 110)
  popY.value = Math.min(Math.max(e.clientY - rect.top - 64, 0), rect.height - 56)
}

// ── 行业 / 概念板块（热 + 冷） ───────────────────────────────────────────────

const industryBoards = ref<BoardRow[]>([])
const conceptBoards = ref<BoardRow[]>([])
const boardsError = ref('')

function hotBoards(list: BoardRow[]): BoardRow[] {
  return list.slice(0, 8)
}

function coldBoards(list: BoardRow[]): BoardRow[] {
  return list.slice(-8).reverse()
}

async function loadBoards() {
  boardsError.value = ''
  try {
    const hy = props.market === 'HK' ? 'HK_HY' : 'US_HY'
    const gn = props.market === 'HK' ? 'HK_GN' : 'US_GN'
    const [a, b] = await Promise.all([fetchBoards(hy, 200), fetchBoards(gn, 500)])
    industryBoards.value = a
    conceptBoards.value = b
  } catch (e) {
    boardsError.value = formatError(e)
  }
}

function boardPct(b: BoardRow): number {
  return Number(b.change_pct ?? 0)
}

function barWidth(pct: number, list: BoardRow[]): string {
  const maxAbs = Math.max(...list.map(boardPct), 0.5)
  return `${Math.min(100, (Math.abs(pct) / maxAbs) * 100)}%`
}

const boardDialog = ref<{ code: string; name: string } | null>(null)

function openBoard(code: string | undefined, name: string | undefined) {
  if (!code) return
  boardDialog.value = { code: String(code), name: String(name ?? code) }
}

let refreshTimer = 0

onMounted(() => {
  // 默认视图：美股=「盘中」价格面板，其余=日K
  if (minuteMode.value) {
      void loadFocalQuote()
      void loadSessionMinute()
    }
  else loadFocal()
  loadStripSparks()
  loadRank()
  loadBoards()
  loadIndexContext()
  refreshTimer = window.setInterval(() => {
    loadRank()
    loadBoards()
    loadIndexContext()
  }, 120_000)
  // SSE 兜底：当前标的没进自选就不会被推送，主动拉一次报价
  fetchQuotes([{ market: focal.value.market, code: focal.value.code }]).catch(() => undefined)
})

onBeforeUnmount(() => {
  alive = false
  window.clearTimeout(searchTimer)
  window.clearTimeout(rankTimer)
  window.clearInterval(refreshTimer)
})
</script>

<template>
  <!--
    美股模式多一条右侧栏（期权结构精简版）；港股模式不显示。
    外层 .ov-shell 只为放这条右栏而存在，.ov 内部布局保持原样。
  -->
  <div class="ov-shell" :class="{ 'has-rail': showOptionsRail }">
    <div class="ov">
      <!-- 指数条（参照沪市看板：三卡，点击切 K 线面板）+ 搜索 -->
      <div class="ov-head">
        <div
          v-for="idx in stripIndices"
          :key="stripSymbol(idx)"
          class="idx-card"
          :class="{ active: focal.code === idx.code }"
          @click="pickIndex(idx)"
        >
          <div class="idx-top">
            <span class="idx-price mono" :class="dirClass(stripPct(idx))">
              {{ stripQuote(idx)?.price?.toFixed(2) ?? '—' }}
            </span>
            <Sparkline
              :prices="stripSparks.get(stripSymbol(idx)) ?? []"
              :base="stripSparkBase.get(stripSymbol(idx)) ?? null"
              :width="110"
              :height="24"
            />
          </div>
          <div class="idx-bottom">
            <span class="idx-name">{{ idx.name }}</span>
            <span class="idx-chg mono" :class="dirClass(stripPct(idx))">
              {{ fmtPctSigned(stripPct(idx)) }}
            </span>
          </div>
        </div>
        <div class="search-box">
          <input
            v-model="searchText"
            class="search-input"
            :placeholder="`搜索${marketLabel(props.market)}代码/名称（如 ${props.market === 'HK' ? '00700 腾讯' : 'AAPL 苹果'}）`"
            @input="onSearchInput"
            @keyup.enter="searchResults.length > 0 && pickSymbol(searchResults[0])"
          />
          <div v-if="searching" class="search-hint">搜索中…</div>
          <div v-else-if="searchError" class="search-hint err">{{ searchError }}</div>
          <div v-else-if="searchResults.length > 0" class="search-list">
            <div
              v-for="s in searchResults"
              :key="s.symbol"
              class="search-row"
              @click="pickSymbol(s)"
            >
              <span class="s-name">{{ s.name || s.code }}</span>
              <span class="s-code mono dim">{{ s.symbol }}</span>
              <span v-if="s.sub_market" class="s-sub">{{ s.sub_market }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- K线面板（全宽） -->
      <div class="card k-panel">
        <div class="k-head">
          <h3>{{ focal.name }} <span class="dim mono code">{{ focal.market }}{{ focal.code }}</span></h3>
          <SourceBadge :source="barsSource" />
          <span class="k-cats">
            <button
              v-for="c in K_CATS"
              :key="c.value"
              class="chip"
              :class="{ on: kCategory === c.value }"
              @click="kCategory = c.value"
            >
              {{ c.label }}
            </button>
          </span>
          <IndicatorChips
            :overlays="indParams.overlays ?? []"
            :sub="indParams.subPane"
            @toggle-overlay="toggleOverlay"
            @select-sub="setSubPane"
          />
          <!-- 美股视图切换：「全部」= 日/周/月 K 线，「盘中」= 纯价格面板 -->
          <span v-if="props.market === 'US'" class="k-cats session-cats">
            <button
              v-for="s in US_SESSION_FILTERS"
              :key="s.value"
              class="chip"
              :class="{ on: (s.value === 'all' ? !minuteMode : minuteMode && sessionFilter === s.value) }"
              :title="s.value === 'all' ? '返回日K' : '盘中分时图 + 五档盘口'"
              @click="pickSession(s.value)"
            >
              {{ s.label }}
            </button>
          </span>
          <button class="chip" @click="dialog = { ...focal }">分时/盘口 ⌗</button>
        </div>
        <div v-if="barsLoading" class="loading">加载中…</div>
        <div v-else-if="barsError" class="err">{{ barsError }}</div>
        <!-- 「盘中」：分时图（左）+ 五档盘口（右） -->
        <div v-else-if="minuteMode" class="pp">
          <div class="pp-left">
            <div class="pp-price-row">
              <span class="pp-price mono" :class="dirClass(focalPct)">
                {{ fmt2(focalQuote?.price) }}
              </span>
              <span class="pp-pct mono" :class="dirClass(focalPct)">
                {{ fmtPctSigned(focalPct) }}
              </span>
            <span class="pp-meta dim mono">
              开 {{ fmt2(focalQuote?.open) }} · 高 {{ fmt2(focalQuote?.high) }} · 低
              {{ fmt2(focalQuote?.low) }} · 量 {{ fmtVolShares(focalQuote?.vol) }}
            </span>
            <!-- 指数无原生分时：用 ETF 代理渲染时必须明示，否则价格量级会被误读 -->
            <span v-if="sessionProxy" class="pp-proxy">分时以 {{ sessionProxy }} 代理</span>
          </div>
            <IntradayChart
              v-if="sessionPoints.length >= 2"
              :points="sessionPoints"
              :pre-close="sessionPreClose"
              :vol-unit-shares="true"
              height="232px"
            />
            <div v-else class="loading">分时加载中…</div>
          </div>
            <!-- 五档盘口：卖盘在上（高→低）、现价居中、买盘在下（高→低），与交易软件一致 -->
            <div class="pp-depth">
              <div class="pd-head">
                <span>五档盘口</span>
                <span class="dim">{{ hasDepth ? '实时' : '休市' }}</span>
              </div>
              <!-- 无挂单时不铺 10 行短横线（那样看着像坏了），收成一个说明 -->
              <div v-if="!hasDepth" class="pd-empty">
                <span class="dim">暂无挂单数据</span>
                <span class="pd-empty-sub dim">休市期间交易所不提供买卖盘</span>
              </div>
              <template v-else>
                <div
                  v-for="lv in [5, 4, 3, 2, 1]"
                  :key="`a${lv}`"
                  class="pd-row"
                  :class="{ 'pd-nil': lvPrice('ask', lv) === null }"
                >
                  <span class="pd-tag">卖{{ lv }}</span>
                  <span class="pd-price mono down">{{ lvPrice('ask', lv) ?? '—' }}</span>
                  <span class="pd-vol mono">{{ lvVol('ask', lv) ?? '—' }}</span>
                </div>
                <div class="pd-row pd-mid">
                  <span class="pd-tag">现价</span>
                  <span class="pd-price mono" :class="dirClass(focalPct)">
                    {{ fmt2(focalQuote?.price) }}
                  </span>
                  <span class="pd-vol mono dim">{{ fmtVolShares(focalQuote?.vol) }}</span>
                </div>
                <div
                  v-for="lv in [1, 2, 3, 4, 5]"
                  :key="`b${lv}`"
                  class="pd-row"
                  :class="{ 'pd-nil': lvPrice('bid', lv) === null }"
                >
                  <span class="pd-tag">买{{ lv }}</span>
                  <span class="pd-price mono up">{{ lvPrice('bid', lv) ?? '—' }}</span>
                  <span class="pd-vol mono">{{ lvVol('bid', lv) ?? '—' }}</span>
                </div>
              </template>
            </div>
        </div>
        <div v-else-if="barsTooFew" class="loading">
          {{ focal.name }} K 线数据源仅提供实时快照，画不出 K 线。
          <button v-if="etfProxy" class="chip" @click="focal = { ...etfProxy }; loadFocal()">
            切 {{ etfProxy.name }} 看完整 K 线
          </button>
        </div>
        <StockKline v-else :bars="shownBars" :params="indParams" />
      </div>

      <!-- 六宫格（A 股同款口径，港美股无涨跌停制度故无涨停雷达） -->
      <div class="grid">
        <!-- 市场统计（榜单快照：涨/平/跌/总数） -->
        <div class="card">
          <h3>市场统计</h3>
          <div v-if="rankError" class="err">{{ rankError }}</div>
          <template v-else-if="breadth && rank?.status === 'ready'">
            <div class="breadth-bar">
              <div class="seg up" :style="{ width: `${breadth.up}%` }"></div>
              <div class="seg flat" :style="{ width: `${breadth.flat}%` }"></div>
              <div class="seg down" :style="{ width: `${breadth.down}%` }"></div>
            </div>
            <div class="stat-nums">
              <span class="up">涨 {{ rank.up }}</span>
              <span class="flat">平 {{ rank.flat }}</span>
              <span class="down">跌 {{ rank.down }}</span>
              <span class="dim">共 {{ rank.total }}</span>
            </div>
          </template>
          <div v-else class="loading">
            {{ rank?.status === 'building' ? `榜单构建中…${rank.progress ? `（${rank.progress}）` : ''}` : '加载中…' }}
          </div>
        </div>

        <!-- 市场情绪雷达（量能维无全市场成交数据，固定中性） -->
        <div class="card">
          <h3>市场情绪 <span class="mood-score mono">{{ moodScore }}</span></h3>
          <MoodRadar :values="radarValues" />
          <div class="mood-foot">
            <span class="mood-word">{{ moodLabel(moodScore) }}</span>
            <span class="dim mono">量能 —（暂无全市场成交）</span>
          </div>
        </div>

        <!-- 涨跌分布直方图（榜单快照 22 桶） -->
        <div class="card dist-card">
          <h3>涨跌分布 <span class="dim title-sub">（全市场 {{ distTotal || '…' }} 只）</span></h3>
          <div v-if="rankError" class="err">{{ rankError }}</div>
          <div
            v-else-if="distCounts"
            ref="distChartEl"
            class="dist-chart"
            @mousemove="onDistMove"
            @mouseleave="hoverBucket = -1"
          >
            <div
              v-for="(count, i) in distCounts"
              :key="i"
              class="dist-col"
              :class="{ zero: BUCKETS[i] === '0', hovered: hoverBucket === i }"
              @mouseenter="hoverBucket = i"
            >
              <div class="dist-bar" :style="{ height: distHeight(count), background: distColor(i) }"></div>
              <div class="dist-label">{{ BUCKETS[i] }}</div>
            </div>
            <div v-if="hoverBucket >= 0" class="dist-pop" :style="{ left: `${popX}px`, top: `${popY}px` }">
              <div class="pop-range">{{ bucketRange(hoverBucket) }}</div>
              <div class="pop-count mono">{{ distCounts[hoverBucket] }} 只</div>
              <div class="pop-share mono">占 {{ bucketShare(distCounts[hoverBucket]) }}</div>
            </div>
          </div>
          <div v-else class="loading">
            {{ rank?.status === 'building' ? '全市场榜单构建中…（首次约 20~70 秒）' : '加载中…' }}
          </div>
        </div>

        <!-- 行业板块（热 + 冷，点击看成分股） -->
        <div class="card board-card">
          <h3>行业板块 <span class="dim title-sub">热</span></h3>
          <div v-if="boardsError" class="err">{{ boardsError }}</div>
          <div v-else class="board-list">
            <div
              v-for="b in hotBoards(industryBoards)"
              :key="b.code"
              class="board-row clickable"
              @click="openBoard(b.code, b.name)"
            >
              <span class="b-name">{{ b.name }}</span>
              <div class="b-bar-wrap">
                <div class="b-bar" :class="dirClass(boardPct(b))" :style="{ width: barWidth(boardPct(b), industryBoards) }"></div>
              </div>
              <span class="b-pct mono" :class="dirClass(boardPct(b))">{{ fmtPctSigned(boardPct(b)) }}</span>
            </div>
          </div>
          <h3 class="cold-title">冷</h3>
          <div v-if="!boardsError" class="board-list">
            <div
              v-for="b in coldBoards(industryBoards)"
              :key="`c${b.code}`"
              class="board-row clickable"
              @click="openBoard(b.code, b.name)"
            >
              <span class="b-name">{{ b.name }}</span>
              <div class="b-bar-wrap">
                <div class="b-bar" :class="dirClass(boardPct(b))" :style="{ width: barWidth(boardPct(b), industryBoards) }"></div>
              </div>
              <span class="b-pct mono" :class="dirClass(boardPct(b))">{{ fmtPctSigned(boardPct(b)) }}</span>
            </div>
          </div>
        </div>

        <!-- 概念板块（热 + 冷） -->
        <div class="card board-card">
          <h3>概念板块 <span class="dim title-sub">热</span></h3>
          <div v-if="boardsError" class="err">{{ boardsError }}</div>
          <div v-else class="board-list">
            <div
              v-for="b in hotBoards(conceptBoards)"
              :key="b.code"
              class="board-row clickable"
              @click="openBoard(b.code, b.name)"
            >
              <span class="b-name">{{ b.name }}</span>
              <div class="b-bar-wrap">
                <div class="b-bar" :class="dirClass(boardPct(b))" :style="{ width: barWidth(boardPct(b), conceptBoards) }"></div>
              </div>
              <span class="b-pct mono" :class="dirClass(boardPct(b))">{{ fmtPctSigned(boardPct(b)) }}</span>
            </div>
          </div>
          <h3 class="cold-title">冷</h3>
          <div v-if="!boardsError" class="board-list">
            <div
              v-for="b in coldBoards(conceptBoards)"
              :key="`c${b.code}`"
              class="board-row clickable"
              @click="openBoard(b.code, b.name)"
            >
              <span class="b-name">{{ b.name }}</span>
              <div class="b-bar-wrap">
                <div class="b-bar" :class="dirClass(boardPct(b))" :style="{ width: barWidth(boardPct(b), conceptBoards) }"></div>
              </div>
              <span class="b-pct mono" :class="dirClass(boardPct(b))">{{ fmtPctSigned(boardPct(b)) }}</span>
            </div>
          </div>
        </div>

        <!-- 排行榜（涨幅/跌幅/成交额/成交量，每行都带成交额） -->
        <div class="card rank-panel">
          <h3>
            {{ marketLabel(props.market) }}行情榜
            <span v-if="rank?.status === 'ready'" class="dim title-sub">（{{ rank.total }} 只）</span>
          </h3>
          <div v-if="rankError" class="err">{{ rankError }}</div>
          <div v-else-if="!rank || rank.status === 'building'" class="loading">
            全市场榜单构建中…{{ rank?.progress ? `（${rank.progress}）` : '（首次约 20~70 秒）' }}
          </div>
          <template v-else>
            <span class="rank-tabs">
              <button
                v-for="t in RANK_TABS"
                :key="t.value"
                class="rank-tab"
                :class="{ on: rankTab === t.value }"
                @click="rankTab = t.value"
              >
                {{ t.label }}
              </button>
            </span>
            <table class="qtable">
              <tbody>
                <tr
                  v-for="(r, i) in rankRows"
                  :key="`${rankTab}${r.code}`"
                  @click="openRow(r.market, r.code, r.name)"
                >
                  <td>{{ i + 1 }}. {{ r.name || r.code }}</td>
                  <td class="mono dim">{{ rankTab === 'by_vol' ? fmtVolShares(Number(r.vol ?? 0)) : fmtAmount(Number(r.amount ?? 0)) }}</td>
                  <td class="mono" :class="rankTab === 'by_vol' ? 'dim' : dirClass(r.change_pct)">
                    {{ rankTab === 'by_vol' ? fmtAmount(Number(r.amount ?? 0)) : fmtPctSigned(r.change_pct) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </template>
        </div>
      </div>

      <StockDialog
        v-if="dialog"
        :market="dialog.market"
        :code="dialog.code"
        :name="dialog.name"
        @close="dialog = null"
      />
      <BoardDialog
        v-if="boardDialog"
        :code="boardDialog.code"
        :name="boardDialog.name"
        @close="boardDialog = null"
      />
    </div>

    <aside v-if="showOptionsRail" class="ov-rail">
      <UsOptionsRail />
    </aside>
  </div>
</template>

<style scoped>
/* 外壳只为承载美股模式的期权右侧栏；无右栏时退化成普通块，不影响原布局 */
.ov-shell {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ov-shell.has-rail {
  flex-direction: row;
  align-items: flex-start;
  gap: var(--sp-3);
}
.ov-shell.has-rail > .ov {
  /* min-width:0 是关键：.ov 内部的指数条/榜单是 flex，不加会被右侧栏挤出视口 */
  flex: 1;
  min-width: 0;
}
.ov-rail {
  width: 288px;
  flex-shrink: 0;
  /* 看板整页滚动（.dash），所以右栏跟随滚动吸附；超长时自己内部滚，
     不把主区的滚动条顶下去 */
  position: sticky;
  top: 0;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
}
.ov {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ov-head {
  display: flex;
  gap: 10px;
}
.idx-card {
  flex: 0 0 250px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px 6px;
  cursor: pointer;
}
.idx-card:hover {
  border-color: var(--accent);
}
.idx-card.active {
  border-color: var(--accent);
}
.idx-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.idx-price {
  font-size: 22px;
  font-weight: 700;
}
.idx-bottom {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 2px;
}
.idx-name {
  font-size: 12px;
  color: var(--text-muted);
}
.idx-chg {
  font-size: 12px;
}
.search-box {
  flex: 1;
  position: relative;
}
.search-input {
  width: 100%;
  padding: 8px 12px;
  font-size: 13px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  outline: none;
}
.search-input:focus {
  border-color: var(--accent);
}
.search-hint {
  padding: 6px 2px;
  font-size: 12px;
  color: var(--text-dim);
}
.search-hint.err {
  color: var(--up);
}
.search-list {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 30;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-top: 4px;
  max-height: 320px;
  overflow: auto;
  box-shadow: 0 8px 24px var(--shadow);
}
.search-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 7px 12px;
  font-size: 12px;
  cursor: pointer;
}
.search-row:hover {
  background: var(--bg-elevated);
}
.s-name {
  font-weight: 600;
}
.s-code {
  font-size: 11px;
}
.s-sub {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-dim);
}
.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
@media (max-width: 1600px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.k-panel {
  min-width: 0;
}
.k-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.k-head h3 {
  margin-right: auto;
}
.k-head .code {
  font-size: 11px;
  font-weight: 400;
}
.k-cats {
  display: inline-flex;
  gap: 4px;
}
.ind-group {
  display: inline-flex;
  gap: 4px;
}
.chip {
  padding: 2px 8px;
  font-size: 11px;
}
.chip.on {
  border-color: var(--accent);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.rank-panel {
  min-height: 300px;
}
.rank-tabs {
  display: inline-flex;
  gap: 3px;
  margin: 8px 0;
}
.rank-tab {
  padding: 1px 8px;
  font-size: 11px;
}
.rank-tab.on {
  border-color: var(--accent);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.breadth-bar {
  display: flex;
  height: 10px;
  border-radius: 3px;
  overflow: hidden;
  margin: 8px 0 6px;
}
.seg.up {
  background: var(--up);
}
.seg.flat {
  background: var(--text-dim);
}
.seg.down {
  background: var(--down);
}
.stat-nums {
  display: flex;
  gap: 14px;
  font-size: 12px;
  margin-bottom: 6px;
}
.title-sub {
  font-weight: 400;
  font-size: 11px;
}
.mood-score {
  float: right;
  font-size: 15px;
  font-weight: 700;
  color: var(--accent);
}
.mood-foot {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 4px;
}
.mood-word {
  font-size: 15px;
  font-weight: 700;
}
.dist-card {
  min-height: 220px;
}
.dist-chart {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 120px;
  margin-top: 10px;
  position: relative;
}
.dist-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
  position: relative;
}
.dist-col:hover,
.dist-col.hovered {
  z-index: 10;
}
.dist-pop {
  position: absolute;
  background: color-mix(in srgb, var(--bg-elevated) 97%, transparent);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 6px 10px;
  font-size: 11px;
  white-space: nowrap;
  pointer-events: none;
  text-align: center;
  box-shadow: 0 4px 14px var(--shadow);
  z-index: 20;
}
.pop-range {
  color: var(--text-muted);
  margin-bottom: 3px;
}
.pop-count {
  font-size: 13px;
  font-weight: 700;
}
.pop-share {
  color: var(--text-dim);
  font-size: 10.5px;
}
.dist-bar {
  width: 100%;
  border-radius: 1px;
  min-height: 1px;
}
.dist-col.zero {
  outline: 1px dashed var(--text-dim);
  outline-offset: 1px;
}
.dist-label {
  font-size: 8.5px;
  color: var(--text-dim);
  margin-top: 3px;
  transform: rotate(-60deg);
  transform-origin: top center;
  white-space: nowrap;
}
.board-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.board-row {
  display: grid;
  grid-template-columns: 84px 1fr 64px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.b-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.board-row.clickable {
  cursor: pointer;
}
.board-row.clickable:hover .b-name {
  color: var(--accent);
}
.cold-title {
  margin-top: 10px;
}
.b-bar-wrap {
  height: 8px;
  background: var(--bg);
  border-radius: 2px;
  overflow: hidden;
}
.b-bar {
  height: 100%;
  border-radius: 2px;
  margin-left: auto;
}
.b-bar.up {
  background: var(--up);
}
.b-bar.down {
  background: var(--down);
}
.b-pct {
  text-align: right;
}
.err {
  color: var(--up);
  font-size: 12px;
  padding: 12px 0;
}
.loading {
  color: var(--text-dim);
  padding: 12px 0;
  font-size: 12px;
}
.dim {
  color: var(--text-dim);
}

/* 「盘中」：左价格与关键指标，右五档盘口；整体不画曲线 */
.pp {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 292px;
  gap: var(--sp-4);
  padding: var(--sp-2) var(--sp-3) var(--sp-1);
  align-items: stretch;
}
.pp-left {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  min-width: 0;
}
.pp-price-row {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.pp-price {
  font-size: var(--fs-2xl);
  font-weight: 600;
  line-height: 1.05;
  letter-spacing: -0.5px;
}
.pp-pct {
  font-size: var(--fs-md);
  font-weight: 500;
}
/* 开/高/低/量：跟在价格后的一行紧凑摘要，不再单独占一块六格 */
.pp-meta {
  font-size: var(--fs-xs);
  color: var(--text-dim);
  white-space: nowrap;
}
/* 分时以 ETF 代理时的明示徽标：点位不是指数本身，不标会被误读 */
.pp-proxy {
  font-size: var(--fs-xs);
  color: var(--warn);
  border: 1px solid var(--warn-line);
  border-radius: 4px;
  padding: 1px 6px;
  white-space: nowrap;
}

/* 五档盘口（卖盘在上 → 现价 → 买盘在下，与交易软件一致） */
.pp-depth {
  display: flex;
  flex-direction: column;
  padding-left: 24px;
  border-left: 1px solid var(--hairline);
}
.pd-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding-bottom: 8px;
  margin-bottom: 2px;
  border-bottom: 1px solid var(--hairline);
  font-size: 12px;
  color: var(--text-muted);
}
.pd-row {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 84px;
  align-items: center;
  gap: 8px;
  padding: 2.5px 0;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
/* 无挂单（休市/该档为空）：整行压暗，避免一排 0.00 被误读成真实盘口 */
.pd-row.pd-nil {
  opacity: 0.4;
}
.pd-mid {
  margin: 6px 0;
  padding: 7px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  font-weight: 600;
}
.pd-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 34px 8px;
  font-size: 13px;
}
.pd-empty-sub {
  font-size: 11px;
}
.pd-tag {
  font-size: 12px;
  color: var(--text-dim);
}
.pd-price {
  text-align: right;
}
.pd-vol {
  text-align: right;
  font-size: 12px;
  color: var(--text-muted);
}

@media (max-width: 980px) {
  .pp {
    grid-template-columns: minmax(0, 1fr);
  }
  .pp-depth {
    padding-left: 0;
    padding-top: 14px;
    border-left: none;
    border-top: 1px solid var(--hairline);
  }
}
</style>
