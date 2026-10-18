<script setup lang="ts">
// 07 题材趋势筛选：用「上升趋势占比」区分真趋势与单日情绪。
//
// 一个题材一周涨 20% 可能只是两只权重股拉的——所以判定看的是
// 「价格站上 MA50 且 MA50 上行」的个股占比，而不是题材本身的涨幅。
// 占比 ≥60% 判上升、≥40% 震荡、其余下行。
//
// 下钻成分时要把总表的 WatchRow 裁成成分表的窄形状：总表里那 20 多列
// （支撑位/机构持股/空头…）在题材下钻场景全是重复信息，全塞进来反而看不清。
import { computed, ref } from 'vue'

import RadarConsTable from './RadarConsTable.vue'
import {
  dirCls,
  fmtPct,
  type ConsRow,
  type Num,
  type WatchRow,
} from '../../data/usRadar'

interface TrendRow {
  theme: string
  n: number
  /** 上升 / 震荡 / 下行 */
  state: string
  w1: Num
  pct_trend: Num
  pct_aligned: Num
  leaders: string[]
  tickers: string[]
}

const props = defineProps<{
  d: { rows: TrendRow[]; conclusion: string }
  watchlist: WatchRow[]
}>()

const openTheme = ref<string | null>(null)

/** 总表索引：题材只带 tickers 数组，展开时要回总表取完整行 */
const byTicker = computed(() => new Map(props.watchlist.map((w) => [w.ticker, w])))

/** 裁成成分表要的窄形状，顺带丢掉 theme（成分表已有题材列） */
function toConsRow(w: WatchRow): ConsRow {
  return {
    ticker: w.ticker,
    theme: w.theme,
    close: w.close,
    d1: w.d1,
    w1: w.w1,
    m1: w.m1,
    rsi: w.rsi,
    vol_ratio: w.vol_ratio,
    signals: w.signals,
    quality: w.quality,
  }
}

const STATE_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  上升: { bg: 'var(--rd-up-dim)', fg: 'var(--up)', label: '上升·可做' },
  震荡: { bg: 'var(--rd-amber-dim)', fg: 'var(--rd-amber)', label: '震荡·轻仓' },
  下行: { bg: 'var(--rd-down-dim)', fg: 'var(--down)', label: '下行·回避左侧' },
}

function stateStyle(s: string) {
  return STATE_STYLE[s] ?? STATE_STYLE['震荡']!
}

function trendColor(pct: Num): string {
  const v = pct ?? 0
  if (v >= 60) return 'var(--up)'
  if (v >= 40) return 'var(--rd-amber)'
  return 'var(--down)'
}

function consOf(r: TrendRow): ConsRow[] {
  return (r.tickers ?? [])
    .map((t) => byTicker.value.get(t))
    .filter((w): w is WatchRow => !!w)
    .map(toConsRow)
}
</script>

<template>
  <div>
    <div class="scroll">
      <table class="rd-table tt">
        <thead>
          <tr>
            <th>题材篮子（点击展开成分）</th>
            <th class="mid">趋势判定</th>
            <th>周涨幅·中位</th>
            <th class="axis-col">上升趋势占比（价&gt;MA50且MA50上行）</th>
            <th>多头排列占比</th>
            <th>周内领涨</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="r in d.rows" :key="r.theme">
            <tr
              class="rd-drill tt-row"
              :class="{ open: openTheme === r.theme }"
              @click="openTheme = openTheme === r.theme ? null : r.theme"
            >
              <td>
                <span class="caret" :class="{ on: openTheme === r.theme }">▶</span>
                <b class="nm">{{ r.theme }}</b>
                <span class="rd-dim cnt">{{ r.n }}只</span>
              </td>
              <td class="mid">
                <span
                  class="rd-pill state"
                  :style="{ background: stateStyle(r.state).bg, color: stateStyle(r.state).fg }"
                >
                  {{ stateStyle(r.state).label }}
                </span>
              </td>
              <td :class="[dirCls(r.w1), 'strong']">{{ fmtPct(r.w1) }}</td>
              <td>
                <div class="pct">
                  <div class="rd-track pct-track">
                    <i
                      :style="{
                        width: `${r.pct_trend ?? 0}%`,
                        background: trendColor(r.pct_trend),
                        opacity: 0.85,
                      }"
                    />
                  </div>
                  <span class="pct-num">{{ r.pct_trend }}%</span>
                </div>
              </td>
              <td class="rd-flat">{{ r.pct_aligned }}%</td>
              <td class="lead">
                <span v-for="l in r.leaders" :key="l" class="chip">{{ l }}</span>
              </td>
            </tr>
            <tr v-if="openTheme === r.theme" class="expand-row">
              <td colspan="6" class="expand-cell">
                <RadarConsTable :rows="consOf(r)" />
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div class="rd-callout">
      <span class="key rd-cyan">结论</span>
      <span class="txt">{{ d.conclusion }}</span>
    </div>
  </div>
</template>

<style scoped>
.scroll {
  overflow-x: auto;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.tt {
  min-width: 820px;
  font-size: 11.5px;
}
.tt .rd-table th {
  font-size: 9.5px;
  letter-spacing: 0.15em;
}
.tt-row > td {
  padding: 7px 10px;
}
.tt-row.open {
  background: var(--rd-cyan-dim);
}
.caret {
  display: inline-block;
  margin-right: 5px;
  font-size: 9px;
  color: var(--text-dim);
  transition: transform 0.15s ease;
}
.caret.on {
  transform: rotate(90deg);
}
.nm {
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 600;
}
.cnt {
  margin-left: 5px;
  font-size: 10px;
}
.strong {
  font-weight: 600;
}
.mid {
  text-align: center;
}
.state {
  font-size: 10px;
  font-weight: 600;
}
.axis-col {
  text-align: center;
}
.pct {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pct-track {
  flex: 1;
  height: 5px;
}
.pct-num {
  width: 32px;
  text-align: right;
  font-size: 10px;
  color: var(--text-muted);
}
.lead {
  text-align: left;
}
.chip {
  margin-right: 5px;
  padding: 1px 4px;
  border-radius: 2px;
  background: var(--rd-up-dim);
  font-size: 10px;
  color: var(--up);
}
.expand-cell {
  padding: 8px 10px !important;
  background: color-mix(in srgb, var(--bg) 30%, transparent);
}
.key {
  margin-right: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.2em;
}
.txt {
  font-size: 12px;
  line-height: 1.7;
}
</style>