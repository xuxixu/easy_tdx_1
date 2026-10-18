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

import { fetchMinute, fetchQuotes, formatError } from '../../api'
import { dirCls, fmtNum, fmtPct } from '../../data/usRadar'
import { INDEX_ETF_PROXY } from '../../market'
import type { MinutePoint, SecurityQuote } from '../../types'
import IntradayChart from '../IntradayChart.vue'

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
    loading: true,
    error: '',
  })),
)

let alive = true

function pctOf(q: SecurityQuote | undefined): number | null {
  if (!q?.price || !q.pre_close) return null
  return (q.price / q.pre_close - 1) * 100
}

async function load() {
  await Promise.all(
    cards.value.map(async (card) => {
      // 美股指数走 ETF 代理；港股指数无代理、直接用指数本身（有原生分时）
      const proxy = INDEX_ETF_PROXY[card.code]
      const target = proxy
        ? { market: proxy.market, code: proxy.code }
        : { market: card.market, code: card.code }
      try {
        // 报价 + 分时并行；昨收基准必须与分时点**同量级**——
        // 美股用代理 ETF 的 pre_close（SPY ~760 配 SPY 分时），
        // 港股用指数 pre_close（HSI ~24062 配 HSI 分时）。
        const [quotes, pts] = await Promise.all([
          fetchQuotes([target]),
          fetchMinute(target.market, target.code),
        ])
        if (!alive) return
        const q = quotes[0]
        card.preClose = q?.pre_close ?? null
        card.price = q?.price ?? null
        card.pct = pctOf(q)
        card.points = pts
        card.error = pts.length === 0 ? '分时无数据（该标的当日可能无成交）' : ''
      } catch (e) {
        if (!alive) return
        card.error = formatError(e)
      } finally {
        if (alive) card.loading = false
      }
    }),
  )
}

onMounted(() => {
  void load()
})
onBeforeUnmount(() => {
  alive = false
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

        <IntradayChart
          v-if="c.points.length >= 2"
          :points="c.points"
          :pre-close="c.preClose"
          :vol-unit-shares="true"
          height="150px"
        />
        <div v-else class="it-chart-empty rd-dim">
          {{ c.loading ? '分时加载中…' : '—' }}
        </div>
      </div>
    </div>

    <p class="it-note rd-dim">
      美股指数以对应 ETF 分时代理（标普→SPY、纳指→QQQ、道指→DIA，点位为 ETF 价格）；
      港股指数为原生分时（点位即指数）。实时数据，休市显示最近分时。
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
.it-note {
  margin-top: 6px;
  font-size: 10.5px;
  line-height: 1.6;
}
</style>