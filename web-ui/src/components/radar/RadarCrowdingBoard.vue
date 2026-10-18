<script setup lang="ts">
// 08 拥挤度 · 机构集中度：Top3 卡 + 全题材表（可下钻）。
//
// 配色的一个刻意取舍：拥挤度的四档状态用的是「青/琥珀/绿」而不是红涨绿跌。
// 拥挤度不是涨跌——如果沿用 --up/--down，读者会把「极高拥挤」误读成「涨」，
// 而它的真实含义是「买盘可能枯竭」，是需要减仓警惕的信号。极端档给绿色，
// 与全站「绿色=需要当心」的直觉一致（原站也是这么配的）。
//
// 口径提醒：机构持股是 Yahoo 的当前披露字段，不是 13F 逐季仓位；
// 拥挤度是四因子代理指标。所以页尾必须带着 methodology 一起显示，
// 否则读者会把它当成真实仓位。
import { computed, ref } from 'vue'

import RadarConsTable from './RadarConsTable.vue'
import {
  dirCls,
  fmtNum,
  fmtPct,
  type ConsRow,
  type CrowdingRow,
  type WatchRow,
} from '../../data/usRadar'

const props = defineProps<{ c: { rows: CrowdingRow[]; conclusion: string; methodology: string }; watchlist: WatchRow[] }>()

const top3 = computed(() => props.c.rows.slice(0, 3))
const openTheme = ref<string | null>(null)

const byTicker = computed(() => new Map(props.watchlist.map((w) => [w.ticker, w])))

/** 拥挤度状态 → 颜色。与涨跌无关，四档递进：低(灰) → 中性(青) → 偏高(琥珀) → 极高(绿) */
const STATE_COLOR: Record<string, string> = {
  极高: 'var(--down)',
  偏高: 'var(--rd-amber)',
  中性: 'var(--rd-cyan)',
  低: 'var(--text-dim)',
}

function stateColor(s: string): string {
  return STATE_COLOR[s] ?? 'var(--text-muted)'
}

function consOf(r: CrowdingRow): ConsRow[] {
  return (r.tickers ?? [])
    .map((t) => byTicker.value.get(t))
    .filter((w): w is WatchRow => !!w)
    .map((w) => ({
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
    }))
}
</script>

<template>
  <div>
    <div class="top-grid">
      <div
        v-for="(r, i) in top3"
        :key="r.theme"
        class="top-card"
        :style="{ borderTop: `2px solid ${stateColor(r.state)}` }"
      >
        <div class="top-head">
          <span>CROWDING #{{ i + 1 }}</span>
          <span :style="{ color: stateColor(r.state) }">{{ r.state }}</span>
        </div>
        <div class="top-main">
          <span class="top-name">{{ r.theme }}</span>
          <span class="top-val" :style="{ color: stateColor(r.state) }">
            {{ fmtNum(r.crowding, 1) }}
          </span>
        </div>
        <div class="rd-track top-track">
          <i
            :style="{
              width: `${Math.min(r.crowding ?? 0, 100)}%`,
              background: stateColor(r.state),
              opacity: 0.9,
            }"
          />
        </div>
        <div class="top-stats">
          <span>机构 {{ r.inst_pct === null ? '—' : `${fmtNum(r.inst_pct, 0)}%` }}</span>
          <span class="right">3月 <b :class="dirCls(r.m3)">{{ fmtPct(r.m3, 0) }}</b></span>
          <span class="right">趋势 {{ r.trend_pct ?? '—' }}%</span>
        </div>
      </div>
    </div>

    <div class="scroll">
      <table class="rd-table cw">
        <thead>
          <tr>
            <th>题材</th>
            <th class="wide">拥挤度代理</th>
            <th class="mid">状态</th>
            <th title="Yahoo Finance当前机构持股比例，市值加权">机构持股·真实</th>
            <th title="题材内机构持股≥70%公司的市值占比">高机构持仓占比</th>
            <th>3月动量</th>
            <th>上升趋势</th>
            <th>量比</th>
            <th>优质/投机</th>
            <th>动量领先</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="r in c.rows" :key="r.theme">
            <tr
              class="rd-drill cw-row"
              :class="{ open: openTheme === r.theme }"
              @click="openTheme = openTheme === r.theme ? null : r.theme"
            >
              <td>
                <span class="caret" :class="{ on: openTheme === r.theme }">▶</span>
                <b class="nm">{{ r.theme }}</b>
                <span class="rd-dim cnt">{{ r.n }}股/{{ r.inst_n }}有机构数据</span>
              </td>
              <td class="wide">
                <div class="meter">
                  <div class="rd-track meter-track">
                    <i
                      :style="{
                        width: `${Math.min(r.crowding ?? 0, 100)}%`,
                        background: stateColor(r.state),
                        opacity: 0.9,
                      }"
                    />
                  </div>
                  <span class="meter-val" :style="{ color: stateColor(r.state) }">
                    {{ fmtNum(r.crowding, 1) }}
                  </span>
                </div>
              </td>
              <td class="mid">
                <span
                  class="rd-pill state"
                  :style="{ color: stateColor(r.state), borderColor: stateColor(r.state) }"
                >
                  {{ r.state }}
                </span>
              </td>
              <td class="rd-flat">{{ r.inst_pct === null ? '—' : `${fmtNum(r.inst_pct, 1)}%` }}</td>
              <td class="rd-flat">
                {{ r.high_inst_share === null ? '—' : `${fmtNum(r.high_inst_share, 1)}%` }}
              </td>
              <td :class="[dirCls(r.m3), 'strong']">{{ fmtPct(r.m3, 1) }}</td>
              <td class="rd-flat">{{ r.trend_pct ?? '—' }}%</td>
              <td class="rd-flat">{{ fmtNum(r.vol_ratio, 2) }}</td>
              <td class="qs">
                <span class="rd-cyan">{{ r.quality_n }}</span>
                <span class="rd-dim"> / </span>
                <span class="rd-amber">{{ r.spec_n }}</span>
              </td>
              <td class="lead">
                <span v-for="l in r.leaders" :key="l" class="chip">{{ l }}</span>
              </td>
            </tr>
            <tr v-if="openTheme === r.theme" class="expand-row">
              <td colspan="10" class="expand-cell">
                <RadarConsTable :rows="consOf(r)" show-theme />
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div class="rd-callout">
      <span class="key rd-cyan">结论</span>
      <span class="txt">{{ c.conclusion }}</span>
    </div>
    <p class="boundary">数据边界：{{ c.methodology }}</p>
  </div>
</template>

<style scoped>
.top-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
@media (min-width: 760px) {
  .top-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
.top-card {
  padding: 12px 14px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.top-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}
.top-main {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
}
.top-name {
  font-size: 14px;
  font-weight: 600;
}
.top-val {
  font-family: var(--font-mono);
  font-size: 21px;
  font-weight: 700;
}
.top-track {
  height: 6px;
  margin-top: 8px;
}
.top-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--text-dim);
}
.top-stats .right {
  text-align: right;
}
.scroll {
  margin-top: 8px;
  overflow-x: auto;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.cw {
  min-width: 1080px;
  font-size: 10.5px;
}
.cw .rd-table th {
  font-size: 9px;
  letter-spacing: 0.14em;
}
.cw-row > td {
  padding: 7px 8px;
}
.cw-row.open {
  background: var(--rd-cyan-dim);
}
.wide {
  width: 190px;
  text-align: left;
}
.mid {
  text-align: center;
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
  font-size: 9.5px;
}
.strong {
  font-weight: 600;
}
.meter {
  display: flex;
  align-items: center;
  gap: 8px;
}
.meter-track {
  flex: 1;
  height: 6px;
}
.meter-val {
  width: 36px;
  text-align: right;
  font-weight: 700;
}
.state {
  border: 1px solid;
}
.qs {
  text-align: right;
}
.lead {
  text-align: left;
}
.chip {
  margin-right: 4px;
  padding: 1px 4px;
  border-radius: 2px;
  background: var(--rd-up-dim);
  font-size: 9.5px;
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
.boundary {
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.7;
  letter-spacing: 0.04em;
  color: color-mix(in srgb, var(--rd-amber) 85%, transparent);
}
</style>