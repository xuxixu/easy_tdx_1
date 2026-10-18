<script setup lang="ts">
// 05 细分板块轮动：24 个细分 + 最强/最弱摘要卡 + 点击下钻成分。
//
// 上升趋势占比是这一块的判断核心：细分涨得多不等于趋势健康——占比 ≥60%
// 才说明是「多数个股在走趋势」而不是「一两只拉指数」，所以条色按占比分三档
// （≥60 红 / ≥40 琥珀 / 其余绿），让「涨但没量」的细分一眼可辨。
import { computed, ref } from 'vue'

import RadarConsTable from './RadarConsTable.vue'
import { dirCls, fmtNum, fmtPct, type SubMove, type SubsectorRow } from '../../data/usRadar'

const props = defineProps<{ d: { rows: SubsectorRow[]; conclusion: string } }>()

const openName = ref<string | null>(props.d.rows[0]?.name ?? null)

// 最强/最弱直接取首尾行：快照的行序本身已按周涨幅排好，不必再排一次
const strongest = computed(() => props.d.rows[0])
const weakest = computed(() => props.d.rows[props.d.rows.length - 1])

/** 占比条色：≥60% 多数个股在趋势里 / ≥40% 分化 / 其余 偏弱 */
function trendColor(pct: number | null | undefined): string {
  const v = pct ?? 0
  if (v >= 60) return 'var(--up)'
  if (v >= 40) return 'var(--rd-amber)'
  return 'var(--down)'
}

function moves(list: SubMove[] | undefined): string {
  return (list ?? []).map((m) => `${m.ticker} ${fmtPct(m.w1, 1)}`).join(' / ')
}

function toggle(name: string) {
  openName.value = openName.value === name ? null : name
}
</script>

<template>
  <div>
    <div class="best-grid">
      <div v-if="strongest" class="best best-up">
        <div class="rd-label">本期最强细分</div>
        <div class="best-row">
          <span class="best-name">{{ strongest.name }}</span>
          <span class="best-w1" :class="dirCls(strongest.w1)">{{ fmtPct(strongest.w1) }}</span>
          <span class="best-sub">周 · 趋势占比 {{ strongest.trend_pct }}%</span>
        </div>
        <div class="best-lead">领涨：{{ moves(strongest.leaders) }}</div>
      </div>

      <div v-if="weakest" class="best best-down">
        <div class="rd-label">本期最弱细分</div>
        <div class="best-row">
          <span class="best-name">{{ weakest.name }}</span>
          <span class="best-w1" :class="dirCls(weakest.w1)">{{ fmtPct(weakest.w1) }}</span>
          <span class="best-sub">周 · 趋势占比 {{ weakest.trend_pct }}%</span>
        </div>
        <div class="best-lead">拖累：{{ moves(weakest.laggers) }}</div>
      </div>
    </div>

    <div class="scroll">
      <table class="rd-table sub">
        <thead>
          <tr>
            <th>细分板块（点击展开成分）</th>
            <th>日</th>
            <th>周</th>
            <th>月</th>
            <th>3月</th>
            <th class="axis-col">上升趋势占比</th>
            <th>量比</th>
            <th>周内领涨 / 领跌</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="r in d.rows" :key="r.name">
            <tr
              class="rd-drill sub-row"
              :class="{ open: openName === r.name }"
              @click="toggle(r.name)"
            >
              <td>
                <span class="caret" :class="{ on: openName === r.name }">▶</span>
                <b class="sub-name">{{ r.name }}</b>
                <span class="rd-dim sub-n">{{ r.n }}只</span>
              </td>
              <td :class="dirCls(r.d1)">{{ fmtPct(r.d1, 1) }}</td>
              <td :class="[dirCls(r.w1), 'strong']">{{ fmtPct(r.w1, 1) }}</td>
              <td :class="dirCls(r.m1)">{{ fmtPct(r.m1, 1) }}</td>
              <td :class="dirCls(r.m3)">{{ fmtPct(r.m3, 0) }}</td>
              <td>
                <div class="trend">
                  <div class="rd-track trend-track">
                    <i
                      :style="{
                        width: `${r.trend_pct ?? 0}%`,
                        background: trendColor(r.trend_pct),
                        opacity: 0.85,
                      }"
                    />
                  </div>
                  <span class="trend-pct">{{ r.trend_pct }}%</span>
                </div>
              </td>
              <td class="rd-flat">{{ fmtNum(r.vol_ratio) }}</td>
              <td class="lead-cell">
                <span v-for="m in r.leaders.slice(0, 2)" :key="m.ticker" class="chip chip-up">
                  {{ m.ticker }}
                </span>
                <span v-for="m in r.laggers.slice(0, 1)" :key="m.ticker" class="chip chip-down">
                  {{ m.ticker }}
                </span>
              </td>
            </tr>
            <tr v-if="openName === r.name" class="expand-row">
              <td colspan="8" class="expand-cell">
                <RadarConsTable :rows="r.constituents" />
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
.best-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  margin-bottom: 8px;
}
@media (min-width: 760px) {
  .best-grid {
    grid-template-columns: 1fr 1fr;
  }
}
.best {
  padding: 10px 12px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
}
.best-up {
  border-left-color: var(--up);
}
.best-down {
  border-left-color: var(--down);
}
.best-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 4px;
}
.best-name {
  font-size: 15px;
  font-weight: 700;
}
.best-w1 {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 700;
}
.best-sub {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
.best-lead {
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-muted);
}
.scroll {
  overflow-x: auto;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.sub {
  min-width: 980px;
  font-size: 10.5px;
}
.sub .rd-table th {
  font-size: 9px;
  letter-spacing: 0.14em;
}
.sub-row > td {
  padding: 7px 8px;
}
.sub-row.open {
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
.sub-name {
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 600;
}
.sub-n {
  margin-left: 5px;
  font-size: 9.5px;
}
.strong {
  font-weight: 700;
}
.axis-col {
  text-align: center;
}
.trend {
  display: flex;
  align-items: center;
  gap: 6px;
}
.trend-track {
  flex: 1;
  height: 5px;
}
.trend-pct {
  width: 32px;
  text-align: right;
  font-size: 9.5px;
  color: var(--text-muted);
}
.lead-cell {
  text-align: left;
}
.chip {
  margin-right: 4px;
  padding: 1px 4px;
  border-radius: 2px;
  font-size: 9.5px;
}
.chip-up {
  background: var(--rd-up-dim);
  color: var(--up);
}
.chip-down {
  background: var(--rd-down-dim);
  color: var(--down);
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