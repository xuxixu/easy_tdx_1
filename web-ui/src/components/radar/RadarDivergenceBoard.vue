<script setup lang="ts">
// 板块内部分化异动检测（挂在 05 细分板块下方）。
//
// 回答的是「同一条产业链内部在换血」这类事件：板块中位数会把内部剧烈分化
// 抹平，而定价逻辑切换的第一信号恰恰是分化——所以对子组做利差对比，
// 日差 ≥4pp 或两日累计 ≥5pp 才报。
//
// 利差用「中轴双向条」而不是数字：正负方向一眼可见，长度按 |利差|/12 归一，
// 12pp 封顶是为了不让极端值把其它行压成看不见的短线。
import { computed } from 'vue'

import { dirCls, fmtPct, type DivergenceBlock, type Num } from '../../data/usRadar'

const props = defineProps<{ d: DivergenceBlock }>()

const firedCount = computed(() => props.d.rows.filter((r) => r.fired).length)

/** 中轴条：正数从中轴向右长，负数向左；长度封顶 50%（即 ±12pp） */
function barGeom(spread1: Num) {
  const v = spread1 ?? 0
  const half = (Math.min(Math.abs(v) / 12, 1) * 50).toFixed(1)
  return {
    width: `${half}%`,
    left: v > 0 ? '50%' : `${50 - Number(half)}%`,
    background: v > 0 ? 'var(--up)' : 'var(--down)',
  }
}

function pp(v: Num): string {
  return v === null || v === undefined || !Number.isFinite(v)
    ? '—'
    : `${v > 0 ? '+' : ''}${v.toFixed(1)}pp`
}
</script>

<template>
  <div class="rd-panel mb">
    <div class="dg-head">
      <span>板块内部分化异动检测 · DIVERGENCE WATCH</span>
      <span v-if="firedCount > 0" class="dg-fired">⚡ {{ firedCount }} 组触发</span>
      <span v-else class="rd-dim">本期无触发</span>
    </div>

    <div class="dg-scroll">
      <table class="rd-table">
        <thead>
          <tr>
            <th>对比组</th>
            <th>A组当日</th>
            <th>B组当日</th>
            <th class="dg-axis-col">当日利差（A−B，pp）</th>
            <th>两日累计利差</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in d.rows" :key="r.name" :class="{ fired: r.fired }">
            <td>
              <span class="dg-name">{{ r.name }}</span>
              <span class="dg-sub">{{ r.a_label }} vs {{ r.b_label }}</span>
            </td>
            <td :class="dirCls(r.a_d1)">{{ fmtPct(r.a_d1, 1) }}</td>
            <td :class="dirCls(r.b_d1)">{{ fmtPct(r.b_d1, 1) }}</td>
            <td>
              <div class="dg-axis">
                <div class="dg-axis-mid" />
                <div class="dg-axis-bar" :style="barGeom(r.spread1)" />
                <span
                  class="dg-axis-val"
                  :class="[dirCls(r.spread1), (r.spread1 ?? 0) > 0 ? 'right' : 'left']"
                >
                  {{ (r.spread1 ?? 0) > 0 ? '+' : '' }}{{ (r.spread1 ?? 0).toFixed(1) }}pp
                </span>
              </div>
            </td>
            <td :class="dirCls(r.spread2)">{{ pp(r.spread2) }}</td>
            <td class="dg-state">
              <span v-if="r.fired" class="rd-pill dg-pill">⚡ 触发·{{ r.direction }}</span>
              <span v-else class="rd-dim">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="dg-rule">规则：{{ d.rule }}</p>

    <div v-if="d.conclusion" class="rd-callout rd-callout-warn">
      <span class="dg-callout-key">解读</span>
      <span class="dg-callout-text">{{ d.conclusion }}</span>
    </div>
  </div>
</template>

<style scoped>
.mb {
  margin-bottom: 8px;
}
.dg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}
.dg-fired {
  font-weight: 700;
  color: var(--rd-amber);
}
.dg-scroll {
  overflow-x: auto;
}
.dg-scroll .rd-table {
  min-width: 760px;
  font-size: 10.5px;
}
/* 触发行整行淡琥珀底：需要被优先看到 */
.rd-table tbody tr.fired {
  background: var(--rd-amber-dim);
}
.dg-name {
  font-weight: 600;
}
.dg-sub {
  margin-left: 6px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
}
.dg-axis-col {
  text-align: center;
}
.dg-axis {
  position: relative;
  display: flex;
  align-items: center;
  height: 14px;
}
.dg-axis-mid {
  position: absolute;
  left: 50%;
  top: 0;
  width: 1px;
  height: 100%;
  background: color-mix(in srgb, var(--text-dim) 60%, transparent);
}
.dg-axis-bar {
  position: absolute;
  top: 3px;
  height: 8px;
  border-radius: 1px;
  opacity: 0.9;
}
.dg-axis-val {
  position: absolute;
  font-size: 10px;
  font-weight: 700;
}
.dg-axis-val.left {
  left: 2px;
}
.dg-axis-val.right {
  right: 2px;
}
.dg-state {
  text-align: center;
}
.dg-pill {
  border: 1px solid var(--rd-amber);
  color: var(--rd-amber);
}
.dg-rule {
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  line-height: 1.7;
  color: var(--text-dim);
}
.dg-callout-key {
  margin-right: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.2em;
  color: var(--rd-amber);
}
.dg-callout-text {
  font-size: 12px;
  line-height: 1.7;
}
</style>