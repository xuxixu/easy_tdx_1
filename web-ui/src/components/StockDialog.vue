<script setup lang="ts">
// 个股预览对话框：头部实时报价 + 加/移除自选 + 左侧五档盘口
// + 右侧 分时/分钟K/日K tab（K 线 tab 支持技术指标切换）。
// 报价来自全局 SSE store；图表按需拉取，分时/日K 独立容错，
// 指数代码在个股 /bars 拿不到时回退 /bars/index（仅 A 股，见 loadDaily/loadIntra）。

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import {
  addWatchItem,
  fetchBars,
  fetchHistoryMinute,
  fetchIndexBars,
  fetchMinute,
  fetchQuotes,
  fetchWatchlist,
  formatError,
  removeWatchItem,
} from '../api'
import { dirClass, fmt2, fmtAmount, fmtPctSigned, fmtVol, fmtVolShares } from '../format'
import { loadIndicatorParams, saveIndicatorParams, subscribeIndicatorParams, type IndicatorParams } from '../indicatorParams'
import { US_SESSION_FILTERS, inUsSessionFilter, isAShare, isExMarket, isUsDst, type USSessionFilter , INDEX_ETF_PROXY} from '../market'
import { useQuoteStore } from '../stores/quotes'
import type { Bar, Category, MinutePoint, SecurityQuote } from '../types'
import IndicatorChips from './IndicatorChips.vue'
import IntradayChart from './IntradayChart.vue'
import StockKline from './StockKline.vue'

const props = defineProps<{
  market: string
  code: string
  name?: string
}>()

const emit = defineEmits<{ close: []; 'watchlist-changed': [] }>()

const quoteStore = useQuoteStore()
const quote = computed(() => quoteStore.getQuote(`${props.market}${props.code}`))

const changePct = computed(() => {
  const q = quote.value
  if (!q?.price || !q.pre_close) return null
  return (q.price / q.pre_close - 1) * 100
})

/**
 * 扩展时段（盘前/盘后）展示门控：有扩展价、与常规价不同、且带涨跌幅才显示。
 * 与常规价相同时隐藏（常规时段扩展字段可能镜像常规价，显示即噪音）。
 */
const showExt = computed(() => {
  const q = quote.value
  return (
    q?.ext_price != null && q.ext_pct != null && q.price != null && q.ext_price !== q.price
  )
})

/**
 * 扩展时段标签：按北京时间粗分盘前/盘后（与浏览器时区无关）。
 * 美东夏令时 盘前16:00~21:30 / 盘后04:00~09:00，冬令时整体+1h——边界小时
 * 可能误标，仅作展示，title 已注明；兜底"扩展时段"。
 */
const extSessionLabel = computed(() => {
  const now = new Date()
  const bj = new Date(now.getTime() + (now.getTimezoneOffset() + 8 * 60) * 60000)
  const t = bj.getHours() * 60 + bj.getMinutes()
  if (t >= 16 * 60 && t < 21 * 60 + 30) return '盘前'
  if (t >= 4 * 60 && t < 9 * 60 + 30) return '盘后'
  return '扩展时段'
})

// ── tab / 指标 ──────────────────────────────────────────────────────────────

const tab = ref<'minute' | 'daily' | 'm15' | 'm30' | 'h1' | 'h4'>('minute')
// 分钟 K 页签（key→ 后端 category；h4 = MIN_240，由 60M 重采样合成）
const KLINE_TABS = [
  { key: 'm15', label: '15分K', category: 'MIN_15', want: 320 },
  { key: 'm30', label: '30分K', category: 'MIN_30', want: 320 },
  { key: 'h1', label: '1小时K', category: 'MIN_60', want: 320 },
  { key: 'h4', label: '4小时K', category: 'MIN_240', want: 200 },
] as Array<{ key: 'm15' | 'm30' | 'h1' | 'h4'; label: string; category: Category; want: number }>
/** 当前分钟 K 页签（分时/日K 下为 null）。 */
const intraTab = computed(() => KLINE_TABS.find((t) => t.key === tab.value) ?? null)
const isMinuteK = computed(() => intraTab.value !== null)
const subPane = ref<string>('macd')
const minuteDays = ref<1 | 3 | 5>(1)
const DAY_OPTIONS: Array<{ value: 1 | 3 | 5; label: string }> = [
  { value: 1, label: '1日' },
  { value: 3, label: '3日' },
  { value: 5, label: '5日' },
]

/** 主图叠加多选：勾选态写回 indParams.overlays（全局共用配置）。 */
const overlays = computed<string[]>(() => indParams.value.overlays ?? [])

function toggleOverlay(v: string) {
  const cur = overlays.value
  const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
  indParams.value.overlays = next
  indParams.value.overlay = next[0] ?? 'ma'
  saveIndicatorParams(indParams.value)
}

/** 副图切换：写回全局配置（与技术指标页/各 K 线图共用）。 */
function setSubPane(v: string) {
  subPane.value = v
  indParams.value.subPane = v
  saveIndicatorParams(indParams.value)
}

// ── 指标参数（全局共用，技术指标设置页写入后这里同步） ────────────────

const indParams = ref<IndicatorParams>(loadIndicatorParams())
const unsubscribeInd = subscribeIndicatorParams((p) => {
  indParams.value = { ...p }
  subPane.value = p.subPane
})
onUnmounted(unsubscribeInd)

const isEx = isExMarket(props.market)
/** 美股才有时段概念（盘前/盘中/盘后/夜盘，北京时钟划分）。 */
const isUS = computed(() => props.market === 'US')
// 美股时段过滤（分时 + 分钟 K 通用；日K 不参与）：默认全部，点选后按北京
// 时钟过滤（与海外看板同口径）。夜盘 TDX 无数据，空时给诚实提示。
const sessionFilter = ref<USSessionFilter>('all')

function inSession(datetime: string): boolean {
  if (!isUS.value || sessionFilter.value === 'all') return true
  if (datetime.length <= 13) return true // 无时分信息（日线）不过滤
  return inUsSessionFilter(datetime.slice(11, 16), sessionFilter.value, isUsDst())
}

/** 时段过滤后的分时点（美股分时只有当日，dayMarks 单天不受影响）。 */
const shownMinutePoints = computed(() => minutePoints.value.filter((p) => inSession(p.datetime)))
/** 时段过滤后的分钟 K 线（StockKline 经 bars 变化自动重拉 option）。 */
const shownIntraBars = computed(() => intraBars.value.filter((b) => inSession(b.datetime)))
if (isEx) minuteDays.value = 1

// ── 图表数据（独立容错） ────────────────────────────────────────────────────

const minutePoints = ref<MinutePoint[]>([])
/** 分时/分钟K 以 ETF 代理时的标注（指数在 MAC 数据源无原生分钟级数据）。 */
const minuteProxy = ref('')
const intraProxy = ref('')
/** 多日分时的天分隔标记（每天起始索引 + 日期）。 */
const minuteDayMarks = ref<Array<{ start: number; date: string }>>([])
const dailyBars = ref<Bar[]>([])
/** 当前分钟 K 页签的 K 线（StockKline 复用，与日K同走服务端 option）。 */
const intraBars = ref<Bar[]>([])
const minuteError = ref('')
const dailyError = ref('')
const intraError = ref('')
const loading = ref(false)

async function loadMinute(my?: number) {
  const seq = my ?? ++chartSeq
  minuteError.value = ''
  proxyPreClose.value = null
  try {
    // 外盘只有当日分时（/minute/history 是 A 股标准协议接口），直接拉当日
    if (isEx) {
      // 指数（US/HK）无原生分时 → 以对应 ETF 代理，UI 上必须明示
      const proxy = INDEX_ETF_PROXY[props.code]
      const target = proxy ?? { market: props.market, code: props.code }
      const pts = await fetchMinute(target.market, target.code)
      if (seq !== chartSeq) return
      minuteProxy.value = proxy?.label ?? ''
      // 代理分时的昨收基准要取代理 ETF 的 pre_close（与分时点同量级），否则
      // y 轴对称基准用指数昨收会把曲线压到图底（见 preClose 注释）。
      if (proxy) {
        try {
          const q = await fetchQuotes([{ market: target.market, code: target.code }])
          proxyPreClose.value = q[0]?.pre_close ?? null
        } catch {
          proxyPreClose.value = null
        }
      }
      minutePoints.value = pts
      minuteDayMarks.value =
        pts.length > 0 ? [{ start: 0, date: new Date().toISOString().slice(0, 10) }] : []
      return
    }
    // 交易日从日K尾部取（末日=今天），今天走 /minute，历史日走 /minute/history
    const dates = dailyBars.value.slice(-minuteDays.value).map((b) => b.datetime.slice(0, 10))
    const all: MinutePoint[] = []
    const marks: Array<{ start: number; date: string }> = []
    for (const d of dates) {
      const dateInt = Number(d.replaceAll('-', ''))
      const pts =
        d === new Date().toISOString().slice(0, 10)
          ? await fetchMinute(props.market, props.code)
          : await fetchHistoryMinute(props.market, props.code, dateInt)
      // 已被更新的请求取代：停止后续串行请求，且不得写入本轮结果
      if (seq !== chartSeq) return
      if (pts.length === 0) continue
      marks.push({ start: all.length, date: d })
      all.push(...pts)
    }
    if (seq !== chartSeq) return
    minutePoints.value = all
    minuteDayMarks.value = marks
  } catch (e) {
    if (seq !== chartSeq) return
    minutePoints.value = []
    minuteDayMarks.value = []
    minuteError.value = formatError(e)
  }
}

// 注意：不能直接 `watch(minuteDays, loadMinute)` —— watch 回调会把
// (newVal, oldVal) 作为前两个实参传入，恰好落进 loadMinute 的 seq 形参，
// 导致守卫序号被日期值污染。这里显式包一层。
watch(minuteDays, () => void loadMinute())

async function loadDaily(my?: number) {
  const seq = my ?? ++chartSeq
  dailyError.value = ''
  try {
    // 日K只展示最近 250 根：取近 2 年（/bars 单页 800 根即可覆盖，避免全历史
    // 分页 5+ 页 + 深层 QFQ 负价重算）；长期停牌取不到再退回全历史。
    const since = new Date(Date.now() - 2 * 365 * 86400_000).toISOString().slice(0, 10)
    let bars = await fetchBars(props.market, props.code, 'DAY', since, undefined)
    if (seq !== chartSeq) return
    if (bars.length === 0) bars = await fetchBars(props.market, props.code, 'DAY', undefined, undefined)
    if (seq !== chartSeq) return
    // 指数（或 /bars 空数据的服务器）回退指数接口。仅 A 股：/bars/index 走标准
    // 协议 + baostock，且 FastAPI 层要求 6 位代码；港美股指数（HSI/SPX 等 3-5
    // 字符）在 /bars 已由 http 指数源覆盖，回退只会拿到 422。
    if (bars.length === 0 && isAShare(props.market)) {
      bars = await fetchIndexBars(props.market, props.code, 250)
    }
    if (seq !== chartSeq) return
    if (bars.length === 0) throw new Error('无日K数据（可能为新股或代码有误）')
    dailyBars.value = bars
  } catch (e) {
    if (seq !== chartSeq) return
    dailyBars.value = []
    dailyError.value = formatError(e)
  }
}

// 请求序号守卫：loadCharts 内部先 await 日K、再 await 分时，而分时依赖日K
// 尾部日期。快速连点两只标的时两次 loadCharts 并发，后发的日K可能先返回，
// 导致旧标的的 loadMinute 拿着新标的的 dailyBars —— 分时与日K分属两只票。
// 分钟 K 页签切换同样经此序号守卫，过期请求的结果直接丢弃。
let chartSeq = 0

async function loadCharts() {
  const my = ++chartSeq
  loading.value = true
  sessionFilter.value = 'all' // 换标的重回全时段，避免旧过滤造成新标的空白
  // 先日K后分时：多日分时的交易日列表取自 dailyBars 尾部。
  // 关键：序号必须**下传**给 loadDaily/loadMinute。它们内部各自直接写响应式
  // 状态，若只在 await 之后比对（本函数旧写法），慢返回的旧请求早已把数据
  // 写进 dailyBars/minutePoints，守卫形同虚设 —— 日K与分时可能分属两只票。
  await loadDaily(my)
  if (my !== chartSeq) return // 已被更新的标的取代
  await loadMinute(my)
  if (my !== chartSeq) return
  // 分钟 K 页签打开时一并刷新（日K tab 下跳过，不浪费请求）
  if (isMinuteK.value) await loadIntra(my)
  if (my !== chartSeq) return
  loading.value = false
}

/** 加载当前分钟 K 页签（指数回退 /bars/index；失败诚实报错，不阻塞）。 */
async function loadIntra(my?: number) {
  const t = intraTab.value
  if (!t) return
  const seq = my ?? ++chartSeq
  if (my === undefined) loading.value = true
  intraError.value = ''
  intraBars.value = []
  try {
    // 指数（US/HK）无原生分钟 K → 以对应 ETF 代理；1 根的 qq 快照不算有效数据
    const proxy = INDEX_ETF_PROXY[props.code]
    const target = proxy ?? { market: props.market, code: props.code }
    let bars = await fetchBars(target.market, target.code, t.category, undefined, undefined, t.want)
    // 同上：/bars/index 只服务 A 股（且要 6 位代码）；港美股指数分钟 K 由
    // /bars 的 http 指数分支或 ETF 代理覆盖，回退会拿到 422。
    if (bars.length === 0 && isAShare(props.market)) {
      bars = await fetchIndexBars(props.market, props.code, t.want, t.category)
    }
    if (bars.length === 0) throw new Error(`无${t.label}数据（该市场/指数可能不支持此周期）`)
    if (seq !== chartSeq) return
    intraProxy.value = proxy?.label ?? ''
    intraBars.value = bars.slice(-t.want)
  } catch (e) {
    if (seq !== chartSeq) return
    intraBars.value = []
    intraError.value = formatError(e)
  } finally {
    if (seq === chartSeq) loading.value = false
  }
}

watch(tab, () => {
  if (isMinuteK.value) void loadIntra()
})

onMounted(loadCharts)
watch([() => props.market, () => props.code], loadCharts)

// ── 自选状态 ────────────────────────────────────────────────────────────────

const inWatchlist = ref(false)
const watchBusy = ref(false)

async function refreshWatchState() {
  try {
    const resp = await fetchWatchlist()
    inWatchlist.value = resp.items.some((i) => i.symbol === `${props.market}${props.code}`)
  } catch {
    inWatchlist.value = false
  }
}
onMounted(refreshWatchState)
watch([() => props.market, () => props.code], refreshWatchState)

async function toggleWatch() {
  watchBusy.value = true
  try {
    if (inWatchlist.value) {
      await removeWatchItem(props.market, props.code)
      inWatchlist.value = false
    } else {
      await addWatchItem(props.market, props.code, props.name ?? '')
      inWatchlist.value = true
    }
    emit('watchlist-changed')
  } catch (e) {
    alert(formatError(e))
  } finally {
    watchBusy.value = false
  }
}

// ── 五档 ────────────────────────────────────────────────────────────────────
// 盘口只依赖 SSE 全局 store 时，非自选股打开弹窗必然空白（store 里没它）。
// 这里主动拉一次 REST 快照写入 store 兜底；港美股扩展报价若无五档字段，
// 则降级显示实时快照（股单位），盘口区永不空白。

const quoteLoading = ref(false)
const quoteError = ref('')

/** 报价是否带有效档位（任一买卖档有正价格）。0 价不可能是真实挂单。 */
function depthOk(q: unknown): boolean {
  if (!q) return false
  const rec = q as Record<string, number | null>
  for (let i = 1; i <= 5; i++) {
    const b = rec[`bid${i}`]
    const a = rec[`ask${i}`]
    if ((typeof b === 'number' && b > 0) || (typeof a === 'number' && a > 0)) return true
  }
  return false
}

async function ensureQuote() {
  const symbol = `${props.market}${props.code}`
  // 注意判据是「有没有档位」而不是「store 里有没有这条」：SSE 推的是精简
  // 报价（字段白名单不含 bid/ask），自选股在 store 里天然有一份**没有五档**
  // 的快照。只看存在性就 return 的话，自选股的盘口会永远停在「实时快照」降级态，
  // 而 REST 明明能给出完整五档。
  if (depthOk(quoteStore.getQuote(symbol))) {
    quoteError.value = ''
    return
  }
  quoteLoading.value = true
  quoteError.value = ''
  try {
    const rows = await fetchQuotes([{ market: props.market, code: props.code }])
    const hit = rows.find((r) => r.symbol === symbol) ?? rows[0]
    if (hit) {
      quoteStore.quotes.set(symbol, hit as SecurityQuote)
    } else {
      quoteError.value = '暂无该股实时报价'
    }
  } catch (e) {
    quoteError.value = formatError(e)
  } finally {
    quoteLoading.value = false
  }
}

onMounted(ensureQuote)
watch([() => props.market, () => props.code], ensureQuote)

/** 是否有五档数据：无档位（或补 0 填充）时走快照降级。 */
const hasDepth = computed(() => depthOk(quote.value))

/** 港美股 vol 单位是股，A 股是手。 */
function fmtDepthVol(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return isEx ? fmtVolShares(v) : String(Math.round(v))
}

function fmtTotalVol(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return isEx ? fmtVolShares(v) : fmtVol(v)
}

const bids = computed(() => {
  const q = quote.value
  if (!q) return []
  return [1, 2, 3, 4, 5].map((i) => ({
    level: i,
    price: (q as unknown as Record<string, number | null>)[`bid${i}`] ?? null,
    vol: (q as unknown as Record<string, number | null>)[`bid_vol${i}`] ?? null,
  }))
})
const asks = computed(() => {
  const q = quote.value
  if (!q) return []
  return [5, 4, 3, 2, 1].map((i) => ({
    level: i,
    price: (q as unknown as Record<string, number | null>)[`ask${i}`] ?? null,
    vol: (q as unknown as Record<string, number | null>)[`ask_vol${i}`] ?? null,
  }))
})

const maxDepthVol = computed(() => {
  let m = 1
  for (const lv of [...bids.value, ...asks.value]) m = Math.max(m, lv.vol ?? 0)
  return m
})

/**
 * 分时/分钟代理（ETF）的昨收基准。走 ETF 代理渲染指数分时时，点的量级是 ETF
 * （如 QQQ ~600），而标的 quote 的昨收是指数的（如 IXIC ~26700）——两者混用会让
 * y 轴对称基准错位，整条曲线贴到图底。代理时必须改用代理 ETF 的昨收。
 */
const proxyPreClose = ref<number | null>(null)

const preClose = computed(() =>
  minuteProxy.value ? proxyPreClose.value : (quote.value?.pre_close ?? null),
)

// ── 一键寻优（跳 /optimize 并自动跑全策略预设网格） ─────────────────────────

const router = useRouter()

function gotoOptimize() {
  emit('close')
  router.push({ path: '/optimize', query: { code: props.code, autoAll: '1' } })
}
</script>

<template>
  <teleport to="body">
    <div class="dlg-mask" @click.self="emit('close')">
      <div class="dlg" :key="`${market}${code}`">
        <!-- 头部：名称 + 实时报价 + 自选开关 -->
        <div class="dlg-head">
          <div class="head-left">
            <span class="stock-name">{{ name || `${market}${code}` }}</span>
            <span class="stock-code mono">{{ market }}{{ code }}</span>
            <span v-if="quote?.server_time" class="srv-time mono">{{ quote.server_time.slice(0, 8) }}</span>
          </div>
          <div class="head-quote">
            <span class="price mono" :class="dirClass(changePct)">{{ fmt2(quote?.price) }}</span>
            <span v-if="changePct !== null" class="chg mono" :class="dirClass(changePct)">
              {{ fmt2((quote?.price ?? 0) - (quote?.pre_close ?? 0)) }}
              {{ fmtPctSigned(changePct) }}
            </span>
            <span
              v-if="showExt"
              class="ext mono"
              :class="dirClass(quote?.ext_pct)"
              :title="`免费快照扩展时段价（${quote?.source ?? '?'}，量 ${fmtAmount(quote?.ext_vol ?? null)}）· 时段按北京时间粗分`"
            >
              {{ extSessionLabel }} {{ fmt2(quote?.ext_price) }} {{ fmtPctSigned(quote?.ext_pct) }}
            </span>
            <button
              class="watch-btn"
              :class="{ watched: inWatchlist }"
              :disabled="watchBusy"
              :title="inWatchlist ? '移除自选' : '加入自选'"
              @click="toggleWatch"
            >
              {{ inWatchlist ? '★ 移除自选' : '☆ 加入自选' }}
            </button>
            <button class="watch-btn" title="用全部策略的预设网格对该股一键寻优" @click="gotoOptimize">
              ⚙ 一键寻优
            </button>
            <button class="close-btn" @click="emit('close')">✕</button>
          </div>
        </div>

        <div class="dlg-body">
          <!-- 五档盘口（按市场自适应：无五档数据的市场显示实时快照） -->
          <div class="depth">
            <div class="depth-title">{{ hasDepth ? '五档盘口' : '实时快照' }}</div>
            <div v-if="!quote && quoteLoading" class="depth-msg">盘口加载中…</div>
            <div v-else-if="!quote && quoteError" class="depth-msg error">
              {{ quoteError }}
              <button class="chip retry" @click="ensureQuote">重试</button>
            </div>
            <template v-else-if="quote">
              <table v-if="hasDepth" class="depth-table">
                <tbody>
                  <tr v-for="lv in asks" :key="`a${lv.level}`">
                    <td class="lv">卖{{ lv.level }}</td>
                    <td class="mono" :class="lv.price && quote?.pre_close ? dirClass(lv.price - quote.pre_close) : 'flat'">
                      {{ fmt2(lv.price) }}
                    </td>
                    <td class="vol-cell">
                      <div class="vol-bar ask" :style="{ width: `${((lv.vol ?? 0) / maxDepthVol) * 100}%` }"></div>
                      <span class="mono">{{ fmtDepthVol(lv.vol) }}</span>
                    </td>
                  </tr>
                  <tr class="sep-row">
                    <td colspan="3"><div class="sep"></div></td>
                  </tr>
                  <tr v-for="lv in bids" :key="`b${lv.level}`">
                    <td class="lv">买{{ lv.level }}</td>
                    <td class="mono" :class="lv.price && quote?.pre_close ? dirClass(lv.price - quote.pre_close) : 'flat'">
                      {{ fmt2(lv.price) }}
                    </td>
                    <td class="vol-cell">
                      <div class="vol-bar bid" :style="{ width: `${((lv.vol ?? 0) / maxDepthVol) * 100}%` }"></div>
                      <span class="mono">{{ fmtDepthVol(lv.vol) }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-else class="no-depth-hint">该市场暂不提供五档盘口，仅显示实时快照</div>
              <div class="depth-stats mono">
                <div><span class="dim2">现价</span>{{ fmt2(quote.price) }}</div>
                <div><span class="dim2">涨跌</span>{{ fmtPctSigned(changePct) }}</div>
                <div><span class="dim2">量</span>{{ fmtTotalVol(quote.vol) }}</div>
                <div><span class="dim2">额</span>{{ fmtAmount(quote.amount) }}</div>
                <div><span class="dim2">高</span>{{ fmt2(quote.high) }}</div>
                <div><span class="dim2">低</span>{{ fmt2(quote.low) }}</div>
                <div><span class="dim2">开</span>{{ fmt2(quote.open) }}</div>
                <div><span class="dim2">昨收</span>{{ fmt2(quote.pre_close) }}</div>
              </div>
            </template>
          </div>

          <!-- 图表区 -->
          <div class="chart-area">
            <div class="tabs">
              <button :class="{ active: tab === 'minute' }" @click="tab = 'minute'">分时</button>
              <button
                v-for="t in KLINE_TABS"
                :key="t.key"
                :class="{ active: tab === t.key }"
                @click="tab = t.key"
              >
                {{ t.label }}
              </button>
              <button :class="{ active: tab === 'daily' }" @click="tab = 'daily'">日K</button>
              <span v-if="tab === 'minute' && !isEx" class="ind-group">
                <button
                  v-for="opt in DAY_OPTIONS"
                  :key="opt.value"
                  class="chip"
                  :class="{ on: minuteDays === opt.value }"
                  @click="minuteDays = opt.value"
                >
                  {{ opt.label }}
                </button>
              </span>
              <span v-if="isUS && (tab === 'minute' || isMinuteK)" class="ind-group" title="按北京时钟划分美股时段">
                <button
                  v-for="s in US_SESSION_FILTERS"
                  :key="s.value"
                  class="chip"
                  :class="{ on: sessionFilter === s.value }"
                  @click="sessionFilter = s.value"
                >
                  {{ s.label }}
                </button>
              </span>
              <template v-if="tab === 'daily' || isMinuteK">
                <IndicatorChips
                  :overlays="overlays"
                  :sub="subPane"
                  @toggle-overlay="toggleOverlay"
                  @select-sub="setSubPane"
                />
                <span v-if="overlays.length > 1" class="dim ov-multi">叠加 {{ overlays.length }} 项</span>
              </template>
            </div>
            <div v-if="loading" class="chart-msg">加载中…</div>
            <template v-else>
              <template v-if="tab === 'minute'">
                <div v-if="minuteError" class="chart-msg error">分时：{{ minuteError }}</div>
                <template v-else>
                  <!-- 代理标注是附加提示，不参与 v-else-if 渲染链（否则图会被吞掉） -->
                  <div v-if="minuteProxy" class="chart-msg proxy">分时以 {{ minuteProxy }} 代理（指数无原生分时）</div>
                  <div v-if="isUS && sessionFilter !== 'all' && shownMinutePoints.length === 0" class="chart-msg">
                    该时段暂无数据（TDX 夜盘无数据），可切「全部」查看
                  </div>
                  <IntradayChart
                    v-if="!(isUS && sessionFilter !== 'all' && shownMinutePoints.length === 0)"
                    :points="shownMinutePoints"
                    :pre-close="preClose"
                    :day-marks="minuteDayMarks"
                    :vol-unit-shares="isEx"
                  />
                </template>
              </template>
              <template v-else-if="isMinuteK">
                <div v-if="intraError" class="chart-msg error">{{ intraTab?.label }}：{{ intraError }}</div>
                <template v-else>
                  <div v-if="intraProxy" class="chart-msg proxy">
                    {{ intraTab?.label }}以 {{ intraProxy }} 代理（指数无原生分钟 K，走势形态一致、点位不同）
                  </div>
                  <div v-if="isUS && sessionFilter !== 'all' && shownIntraBars.length === 0" class="chart-msg">
                    该时段暂无数据（TDX 夜盘无数据），可切「全部」查看
                  </div>
                  <!-- 分钟线首根涨跌相对自身开盘（不拿日级昨收）；vol 单位为股（后端契约），指数分钟线 vol 为 null 显示 0 -->
                  <StockKline
                    v-if="!(isUS && sessionFilter !== 'all' && shownIntraBars.length === 0)"
                    :bars="shownIntraBars"
                    :overlays="overlays"
                    :sub-pane="subPane"
                    :params="indParams"
                    :pre-close="null"
                    :vol-unit-shares="true"
                  />
                </template>
              </template>
              <template v-else>
                <div v-if="dailyError" class="chart-msg error">日K：{{ dailyError }}</div>
                <StockKline
                  v-else
                  :bars="dailyBars"
                  :overlays="overlays"
                  :sub-pane="subPane"
                  :params="indParams"
                  :pre-close="preClose"
                  :vol-unit-shares="isEx"
                />
              </template>
            </template>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.dlg-mask {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.dlg {
  width: min(1280px, 96vw);
  max-height: 94vh;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dlg-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.head-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.stock-name {
  font-size: 16px;
  font-weight: 700;
}
.stock-code {
  font-size: 12px;
  color: var(--text-dim);
}
.srv-time {
  font-size: 11px;
  color: var(--text-dim);
}
.head-quote {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.price {
  font-size: 22px;
  font-weight: 700;
}
.chg {
  font-size: 13px;
}
.ext {
  font-size: 12px;
  opacity: 0.85;
}
.watch-btn {
  font-size: 12px;
  padding: 4px 10px;
  margin-left: 10px;
  align-self: center;
}
.watch-btn.watched {
  border-color: var(--warn);
  color: var(--warn);
}
.close-btn {
  padding: 2px 8px;
  font-size: 12px;
  align-self: center;
}
.dlg-body {
  display: flex;
  gap: 0;
  overflow: auto;
}
.depth {
  width: 260px;
  flex-shrink: 0;
  padding: 10px 14px;
  border-right: 1px solid var(--border);
}
.depth-title {
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 6px;
}
.depth-msg {
  font-size: 12px;
  color: var(--text-dim);
  padding: 24px 0;
  text-align: center;
}
.depth-msg.error {
  color: var(--up);
}
.depth-msg .retry {
  margin-left: 8px;
  padding: 2px 10px;
  font-size: 11px;
}
.no-depth-hint {
  font-size: 11px;
  color: var(--text-dim);
  background: var(--bg-elevated);
  border-radius: var(--radius);
  padding: 6px 10px;
  margin-bottom: 8px;
  line-height: 1.5;
}
.depth-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.depth-table td {
  padding: 2.5px 4px;
  white-space: nowrap;
}
.lv {
  color: var(--text-dim);
  width: 34px;
}
.vol-cell {
  position: relative;
  width: 90px;
}
.vol-bar {
  position: absolute;
  right: 0;
  top: 2px;
  bottom: 2px;
  opacity: 0.18;
  border-radius: 2px;
}
.vol-bar.ask {
  background: var(--up);
}
.vol-bar.bid {
  background: var(--down);
}
.vol-cell span {
  position: relative;
}
.sep {
  border-top: 1px dashed var(--border);
  margin: 3px 0;
}
.depth-stats {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3px 10px;
  font-size: 11.5px;
  color: var(--text-muted);
}
.depth-stats > div {
  display: flex;
  justify-content: space-between;
}
.dim2 {
  color: var(--text-dim);
}
.chart-area {
  flex: 1;
  min-width: 0;
  padding: 10px 12px;
}
.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.tabs button.active {
  border-color: var(--accent);
  color: var(--accent);
}
.ind-group {
  display: inline-flex;
  gap: 4px;
  margin-left: 12px;
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
.ov-multi {
  font-size: 11px;
  margin-left: 4px;
}
.chart-msg {
  padding: 40px 0;
  text-align: center;
  color: var(--text-dim);
}
.chart-msg.error {
  color: var(--up);
}
/* 代理标注：不是错误，用警告色但保持紧凑（继承的 40px padding 太占地方） */
.chart-msg.proxy {
  color: var(--warn);
  background: var(--warn-soft);
  padding: 8px 12px;
  border-radius: var(--radius);
}
</style>
