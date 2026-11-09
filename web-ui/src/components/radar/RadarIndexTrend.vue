<script setup lang="ts">
// 指数实时走势（对应 ETF 代理）。
//
// 为什么要有它、为什么用 ETF 走势：雷达页原是「构建时点静态快照」，指数只给
// 收盘数字（标普 7659.44），看不出当日分时形态；而 MAC 扩展栈对美股/港股
// **指数**本身不返回分时（只回 1 根 qq 快照），直接拉指数分时是空的。这里用
// INDEX_ETF_PROXY 把**美股**指数映射到高度相关的 ETF（标普→SPY、纳指→QQQ、
// 道指→DIA）；港股指数（恒生/恒科）走原生指数分时，不走 ETF 代理。
// 代理卡的点位是 ETF 不是指数，必须标注出来，避免读者把 ETF 价格误当成指数点位。
//
// 本区是**实时**行情（走 /minute 与 /quotes），与页内静态快照的数字互补：
// 快照给收盘技术指标（均线/RSI），这里给当日分时形态。休市时显示最近一根分时。
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchMinute, fetchQuotes, firstPreClose, formatError } from '../../api'
import { dirCls, fmtNum, fmtPct } from '../../data/usRadar'
import { INDEX_ETF_PROXY } from '../../market'
import type { MinutePoint, SecurityQuote } from '../../types'
import IntradayChart from '../IntradayChart.vue'
import LoadingState from '../LoadingState.vue'

/** 一张指数走势卡。 */
interface TrendCard {
  /** 指数显示名。 */
  name: string
  /** 指数代码（美股为 INDEX_ETF_PROXY 的键；港股为原生指数代码）。 */
  code: string
  /** 指数所在市场（无代理时直接取该市场指数分时）。 */
  market: string
  /** 代理 ETF 标签（美股如 "SPY"）；港股指数有原生分时，为 null。 */
  proxy: string | null
  /** 分时点。 */
  points: MinutePoint[]
  /** 昨收（分时昨收基准线）。 */
  preClose: number | null
  /** 实时价。 */
  price: number | null
  /** 相对昨收的实时涨跌幅 %。 */
  pct: number | null
  /** 非空（YYYYMMDD）= 正在显示回退的上一交易日分时，用于诚实标注。 */
  historyDate: string
  loading: boolean
  error: string
}

// 美股三大指数（走 ETF 代理）+ 港股恒生/恒生科技（原生分时）。
// 港股指数**不走** ETF 代理：qq 源返回完整指数分时，点位正确、datetime 带日期，
// 与 IntradayChart 兼容；而代理到 02800（tdx 源，HH:MM:SS 无日期、点位是 ETF
// 价格）会让分时图 x 轴错乱、y 轴量级失衡。见 INDEX_ETF_PROXY 注释。
const INDEXES: Array<{ name: string; code: string; market: string }> = [
  { name: '标普500', code: 'SPX', market: 'US' },
  { name: '纳斯达克', code: 'IXIC', market: 'US' },
  { name: '道琼斯', code: 'DJI', market: 'US' },
  { name: '恒生指数', code: 'HSI', market: 'HK' },
  { name: '恒生科技', code: 'HSTECH', market: 'HK' },
]

const cards = ref<TrendCard[]>(
  INDEXES.map((x) => ({
    ...x,
    proxy: INDEX_ETF_PROXY[x.code]?.label ?? null,
    points: [],
    preClose: null,
    price: null,
    pct: null,
    historyDate: '',
    loading: true,
    error: '',
  })),
)

let alive = true
let recheckTimer: ReturnType<typeof setInterval> | null = null
/** 开盘后重查当日分时的间隔。 */
const RECHECK_MS = 60_000

/** YYYYMMDD → YYYY-MM-DD（标注用）。 */
function fmtDate(ymd: string): string {
  return ymd.length === 8 ? `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}` : ymd
}

/** 最近若干个自然日里的交易日候选（YYYYMMDD），从昨天往前，跳过周末。 */
function recentTradeDates(max = 6): number[] {
  const out: number[] = []
  const d = new Date()
  d.setDate(d.getDate() - 1)
  for (let i = 0; i < max * 2 && out.length < max; i++) {
    const wd = d.getDay()
    if (wd !== 0 && wd !== 6) {
      out.push(d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate())
    }
    d.setDate(d.getDate() - 1)
  }
  return out
}

function pctOf(q: SecurityQuote | undefined): number | null {
  if (!q?.price || !q.pre_close) return null
  return (q.price / q.pre_close - 1) * 100
}

/** 取数目标：美股指数走 ETF 代理，港股指数用原生指数。 */
function targetOf(card: TrendCard): { market: string; code: string } {
  const proxy = INDEX_ETF_PROXY[card.code]
  return proxy
    ? { market: proxy.market as string, code: proxy.code }
    : { market: card.market, code: card.code }
}

/** 拉当日分时；不足 2 根（美股盘前 tdx 只给 1 根残留快照）时回退上一交易日。 */
async function loadCard(card: TrendCard, opts: { recheck?: boolean } = {}): Promise<void> {
  const target = targetOf(card)
  try {
    // 报价 + 分时并行；昨收基准必须与分时点**同量级**——
    // 美股用代理 ETF 的 pre_close，港股用指数 pre_close。
    const [quotes, pts] = await Promise.all([
      fetchQuotes([target]),
      fetchMinute(target.market, target.code),
    ])
    if (!alive) return
    const q = quotes[0]
    // 实时报价两条路径都要显示：即便图回退到上一交易日，卡片顶部的价/涨跌
    // 仍是当日盘前快照（真实值），不能因为画历史图就留空。
    card.price = q?.price ?? null
    card.pct = pctOf(q)
    const sameDay = pts.length >= 2
    if (sameDay) {
      // 当日分时已就绪（盘中 / 已从盘前切回）：正常显示，清除历史标注
      card.preClose = q?.pre_close ?? firstPreClose(pts)
      card.points = pts
      card.historyDate = ''
      card.error = ''
      return
    }

    // 盘前/休市：美股分时不足 → 回退上一交易日完整分时（港股不回退，其分时
    // 常年完整）。只在首次加载与非回退态时找，避免轮询反复打历史日期。
    if (card.market === 'US' && !opts.recheck) {
      const hist = await loadHistory(card, target)
      if (hist) {
        card.error = ''
        return
      }
    }
    // 回退也没数据：保留实时报价，图区显示诚实提示
    card.preClose = q?.pre_close ?? firstPreClose(pts)
    card.points = pts
    card.historyDate = ''
    card.error = pts.length === 0 ? '分时无数据（该标的当日可能无成交）' : ''
  } catch (e) {
    if (!alive) return
    card.error = formatError(e)
  } finally {
    if (alive) card.loading = false
  }
}

/** 从最近交易日里找一天有完整分时的，画历史图并登记日期（供诚实标注）。 */
async function loadHistory(
  card: TrendCard,
  target: { market: string; code: string },
): Promise<boolean> {
  for (const d of recentTradeDates()) {
    if (!alive) return false
    try {
      const pts = await fetchMinute(target.market, target.code, d)
      if (!alive) return false
      if (pts.length >= 2) {
        card.points = pts
        // 历史日的昨收用该日分时自带的 pre_close（同量级），而非当日报价昨收
        card.preClose = firstPreClose(pts)
        card.historyDate = String(d)
        return true
      }
    } catch {
      // 该日无数据（节假日/停牌），继续往前找
    }
  }
  return false
}

async function load() {
  await Promise.all(cards.value.map((card) => loadCard(card)))
}

/** 定时重查：美股开盘后当日分时变多，自动从历史图切回当日图。 */
function startRecheck() {
  recheckTimer = setInterval(() => {
    const stale = cards.value.filter((c) => c.historyDate && c.market === 'US')
    if (!stale.length) return
    void Promise.all(stale.map((c) => loadCard(c, { recheck: true })))
  }, RECHECK_MS)
}

onMounted(() => {
  void load().then(startRecheck)
})
onBeforeUnmount(() => {
  alive = false
  if (recheckTimer) clearInterval(recheckTimer)
  recheckTimer = null
})
</script>

<template>
  <div class="it">
    <div class="it-grid">
      <div v-for="c in cards" :key="c.code" class="it-card">
        <div class="it-head">
          <span class="it-name">{{ c.name }}</span>
          <span
            class="it-proxy"
            :title="c.proxy ? `走势由 ${c.proxy}（ETF）代理，点位是 ETF 而非指数` : '指数原生分时，点位即指数'"
          >
            {{ c.proxy ? `${c.proxy} 走势` : '指数分时' }}
          </span>
        </div>

        <div class="it-price-row">
          <template v-if="c.loading">
            <span class="it-loading">加载中…</span>
          </template>
          <template v-else-if="c.error">
            <span class="it-err">{{ c.error }}</span>
          </template>
          <template v-else>
            <span class="it-price mono" :class="dirCls(c.pct)">{{ fmtNum(c.price, 2) }}</span>
            <span class="it-pct mono" :class="dirCls(c.pct)">{{ fmtPct(c.pct) }}</span>
          </template>
        </div>

        <!-- 回退历史分时：必须显著标注，避免把上一日的形态误读成当日实时 -->
        <div v-if="c.historyDate" class="it-history">
          上一交易日 {{ fmtDate(c.historyDate) }} 分时 · 美股盘前/休市 · 开盘后自动切回当日
        </div>
        <IntradayChart
          v-if="c.points.length >= 2"
          :points="c.points"
          :pre-close="c.preClose"
          :vol-unit-shares="true"
          height="150px"
        />
        <LoadingState v-else-if="c.loading" label="分时加载中…" compact :lines="2" />
        <div v-else class="it-chart-empty rd-dim">美股盘前/休市，暂无当日分时</div>
      </div>
    </div>

    <p class="it-note rd-dim">
      美股指数以对应 ETF 分时代理（标普→SPY、纳指→QQQ、道指→DIA，点位为 ETF 价格）；
      港股指数为原生分时（点位即指数）。盘前/休市回退显示上一交易日完整分时并标注，开盘后自动切回当日实时。
    </p>
  </div>
</template>

<style scoped>
.it-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
@media (min-width: 860px) {
  .it-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (min-width: 1100px) {
  .it-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (min-width: 1440px) {
  .it-grid {
    grid-template-columns: repeat(5, 1fr);
  }
}
.it-card {
  padding: 10px 12px 4px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.it-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}
.it-name {
  font-size: 12.5px;
  font-weight: 600;
}
.it-proxy {
  padding: 1px 5px;
  border-radius: 2px;
  background: var(--rd-cyan-dim);
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.04em;
  color: var(--rd-cyan);
  cursor: help;
  white-space: nowrap;
}
.it-price-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 3px 0 6px;
  min-height: 16px;
}
.it-price {
  font-family: var(--font-mono);
  font-size: 17px;
  font-weight: 700;
}
.it-pct {
  font-family: var(--font-mono);
  font-size: 12px;
}
.it-loading,
.it-err {
  font-size: 11.5px;
}
.it-err {
  color: var(--warn);
}
.it-chart-empty {
  height: 150px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
}
/* 历史分时回退标注：琥珀色细条，压在分时图上方，明确「不是当日实时」 */
.it-history {
  padding: 3px 6px;
  margin-bottom: 2px;
  border-radius: 2px;
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 9.5px;
  line-height: 1.4;
  text-align: center;
}
.it-note {
  margin-top: 6px;
  font-size: 10.5px;
  line-height: 1.6;
}
</style>