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
  formatError,
  searchOverseasSymbols,
  type OverseasRank,
  type OverseasSymbol,
} from '../api'
import { dirClass, fmtAmount, fmtPctSigned, fmtVolShares } from '../format'
import { loadIndicatorParams, type IndicatorParams } from '../indicatorParams'
import { enabledIndices } from '../indexIndicators'
import {
  inUsSessionFilter,
  isUsDst,
  MARKET_DEFAULT_INDEX,
  marketLabel,
  US_SESSION_FILTERS,
  type Market,
  type USSessionFilter,
  usSession,
} from '../market'
import { useQuoteStore } from '../stores/quotes'
import type { Bar, BoardRow } from '../types'
import BoardDialog from './BoardDialog.vue'
import IndicatorEditor from './IndicatorEditor.vue'
import MoodRadar from './MoodRadar.vue'
import SourceBadge from './SourceBadge.vue'
import Sparkline from './Sparkline.vue'
import StockDialog from './StockDialog.vue'
import StockKline from './StockKline.vue'

const props = defineProps<{ market: Market }>()

const quoteStore = useQuoteStore()

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

async function loadStripSparks() {
  for (const idx of stripIndices.value) {
    try {
      const pts = await fetchMinute(idx.market, idx.code)
      if (pts.length > 0) {
        const key = stripSymbol(idx)
        stripSparks.value.set(key, pts.map((p) => p.price))
        const q = stripQuote(idx)
        stripSparkBase.value.set(key, q?.pre_close ?? pts[0].price)
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
    // 切市场重置时段档：美股回到当前时段（分钟K），港股/其它回到「全部」（日K）
    sessionFilter.value = m === 'US' ? (usSession() as USSessionFilter) : 'all'
    minuteMode.value = sessionFilter.value !== 'all'
    if (minuteMode.value) loadMinuteBars()
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
const kCategory = ref<'DAY' | 'WEEK' | 'MONTH'>('DAY')
const K_CATS: Array<{ value: 'DAY' | 'WEEK' | 'MONTH'; label: string }> = [
  { value: 'DAY', label: '日K' },
  { value: 'WEEK', label: '周K' },
  { value: 'MONTH', label: '月K' },
]

// ── 美股时段过滤（分钟数据按 夜盘/盘前/盘中/盘后 查看）────────────────────────
// TDX 分钟线含盘前盘后，夜盘无数据。选时段后自动切 MIN_5 并按北京时钟过滤；
// 切回日/周/月即退出时段模式。默认档：美股 = 当前时段（分钟K），
// 「全部」才回日K（盘后/夜盘看全貌，别默认把用户钉在分时上）。
const sessionFilter = ref<USSessionFilter>(
  props.market === 'US' ? (usSession() as USSessionFilter) : 'all',
)
const minuteMode = ref(sessionFilter.value !== 'all')

function pickSession(s: USSessionFilter) {
  sessionFilter.value = s
  if (s === 'all') {
    minuteMode.value = false
    loadFocal()
    return
  }
  minuteMode.value = true
  loadMinuteBars()
}

async function loadMinuteBars() {
  barsLoading.value = true
  barsError.value = ''
  try {
    const fetched = await fetchBars(focal.value.market, focal.value.code, 'MIN_5', undefined, undefined)
    if (fetched.length === 0) throw new Error('无分钟数据')
    bars.value = fetched.slice(-800)
  } catch (e) {
    bars.value = []
    barsError.value = formatError(e)
  } finally {
    barsLoading.value = false
  }
}

/** 过滤后的 K 线（时段模式下按北京时钟过滤分钟 bar）。 */
const shownBars = computed(() => {
  if (!minuteMode.value || sessionFilter.value === 'all') return bars.value
  const dst = isUsDst()
  return bars.value.filter((b) => {
    const t = b.datetime.slice(11, 16)
    if (!t || b.datetime.length <= 10) return true
    return inUsSessionFilter(t, sessionFilter.value, dst)
  })
})

/** 当前 K 线数据源（bars 首根的 source 标记）。 */
const barsSource = computed(() => bars.value[0]?.source)

// ── 指标参数（全局共用，编辑器写入 localStorage 后这里同步） ────────────────
const indParams = ref<IndicatorParams>(loadIndicatorParams())
const showIndEditor = ref(false)
const dialog = ref<Focal | null>(null)

/** 美股真指数 → 追踪 ETF（指数 K 线只有快照时一键切换看完整 K 线）。 */
const US_ETF_PROXY: Record<string, { market: string; code: string; name: string }> = {
  DJI: { market: 'US', code: 'DIA', name: '道指ETF' },
  IXIC: { market: 'US', code: 'QQQ', name: '纳指100ETF' },
  SPX: { market: 'US', code: 'SPY', name: '标普500ETF' },
}

/** 当前标的是否 K 线不足（美股真指数只有快照 1 根，画不出图）。 */
const barsTooFew = computed(() => !barsLoading.value && !barsError.value && shownBars.value.length < 2)
const etfProxy = computed(() =>
  props.market === 'US' ? (US_ETF_PROXY[focal.value.code] ?? null) : null,
)

async function loadFocal() {
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
    if (fetched.length === 0) throw new Error('无K线数据（可能为新股或代码有误）')
    bars.value = fetched.slice(-250)
  } catch (e) {
    bars.value = []
    barsError.value = formatError(e)
  } finally {
    barsLoading.value = false
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
  // 默认档：美股=当前时段分钟K（盘前/盘中/盘后/夜盘），其余=日K
  if (minuteMode.value) loadMinuteBars()
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
  window.clearTimeout(searchTimer)
  window.clearTimeout(rankTimer)
  window.clearInterval(refreshTimer)
})
</script>

<template>
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
        <button class="chip ind-edit" title="编辑指标参数" @click="showIndEditor = true">⚙ 指标</button>
        <!-- 美股时段切换（分钟数据按 夜盘/盘前/盘中/盘后 过滤查看） -->
        <span v-if="props.market === 'US'" class="k-cats session-cats">
          <button
            v-for="s in US_SESSION_FILTERS"
            :key="s.value"
            class="chip"
            :class="{ on: (s.value === 'all' ? !minuteMode : minuteMode && sessionFilter === s.value) }"
            :title="
              s.value === 'all'
                ? '返回日K'
                : s.value === 'open'
                  ? '只看盘中（21:30~04:00）分钟线——TDX 目前只提供此时段'
                  : `只看${s.label}时段分钟线（TDX 暂无此时段数据）`
            "
            @click="pickSession(s.value)"
          >
            {{ s.label }}
          </button>
        </span>
        <button class="chip" @click="dialog = { ...focal }">分时/盘口 ⌗</button>
      </div>
      <div v-if="barsLoading" class="loading">加载中…</div>
      <div v-else-if="barsError" class="err">{{ barsError }}</div>
      <div v-else-if="barsTooFew" class="loading">
        <!-- 时段模式下是"该时段无分钟数据"；日K 不足才是数据源只给快照 -->
        <template v-if="minuteMode">
          {{ focal.name }} 该时段无分钟数据（夜盘 TDX 不提供；指数无分钟线）。点「全部」回日K。
        </template>
        <template v-else>
          {{ focal.name }} K 线数据源仅提供实时快照，画不出 K 线。
          <button
            v-if="etfProxy"
            class="chip"
            @click="focal = { ...etfProxy }; loadFocal()"
          >
            切 {{ etfProxy.name }} 看完整 K 线
          </button>
        </template>
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
    <IndicatorEditor v-if="showIndEditor" v-model="indParams" @close="showIndEditor = false" />
  </div>
</template>

<style scoped>
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
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
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
.chip {
  padding: 2px 8px;
  font-size: 11px;
}
.chip.on {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(74, 158, 255, 0.12);
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
  background: rgba(74, 158, 255, 0.12);
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
  background: rgba(26, 29, 38, 0.97);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 6px 10px;
  font-size: 11px;
  white-space: nowrap;
  pointer-events: none;
  text-align: center;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45);
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
</style>
