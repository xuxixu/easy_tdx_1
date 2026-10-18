<script setup lang="ts">
// 11 左侧雷达 · 回踩支撑：按「离规律支撑位有多近」分三个梯队。
//
// 分梯队是这一块的核心：左侧买点的成立条件是「上升趋势 + 距支撑簇≤3% + 质地合格」。
// 已经到位的（≤3%）单独一档，而「质地为情绪/投机」的虽然也触发了，但因为
// V2 规则要求质地合格，只能列示不采纳——把它和真买点混在一张表里，
// 会让人以为规则没有生效。
import { dirCls, fmtNum, fmtPct, type LeftBlock } from '../../data/usRadar'

defineProps<{ d: LeftBlock }>()

/** 失效位 = 支撑价下方 3%：跌破它说明「回踩支撑」这个前提已经失效 */
function invalidLevel(sup: number | null | undefined): string {
  if (sup === null || sup === undefined || !Number.isFinite(sup)) return '—'
  return (sup * 0.97).toFixed(2)
}
</script>

<template>
  <div>
    <p class="rule">{{ d.rule }}</p>

    <div class="panel">
      <div class="band band-hit">
        ● 已触发 · 回踩到位（{{ d.buy.length }}）
      </div>
      <table class="rd-table lr">
        <thead>
          <tr>
            <th>代码</th>
            <th>题材</th>
            <th>现价</th>
            <th>规律支撑</th>
            <th>验证次数</th>
            <th>距支撑</th>
            <th>RSI</th>
            <th>周</th>
            <th title="支撑价下方3%">失效位·参考</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in d.buy" :key="r.ticker" class="hit">
            <td class="tk">{{ r.ticker }}</td>
            <td class="theme">{{ r.theme }}</td>
            <td class="rd-flat">{{ r.close.toFixed(2) }}</td>
            <td class="rd-cyan strong">{{ fmtNum(r.sup, 2) }}</td>
            <!-- 触碰 ≥3 次才算「规律」，否则只是偶然的一次支撑 -->
            <td :class="(r.sup_n ?? 0) >= 3 ? 'rd-cyan' : 'rd-flat'">{{ r.sup_n }}次</td>
            <td :class="[dirCls(r.dist_sup), 'strong']">{{ fmtPct(r.dist_sup, 1) }}</td>
            <td :class="(r.rsi ?? 50) >= 70 ? 'rd-amber' : 'rd-flat'">{{ fmtNum(r.rsi, 0) }}</td>
            <td :class="dirCls(r.w1)">{{ fmtPct(r.w1) }}</td>
            <td class="inval">{{ invalidLevel(r.sup) }}</td>
          </tr>
          <tr v-if="d.buy.length === 0">
            <td colspan="9" class="empty">今日无触发</td>
          </tr>
        </tbody>
      </table>

      <template v-if="(d.buy_spec ?? []).length > 0">
        <div class="band band-spec">
          ⚠ 已触发但质地为情绪/投机（{{ d.buy_spec.length }}）· V2规则不采纳，仅列示
        </div>
        <table class="rd-table lr">
          <tbody>
            <tr v-for="r in d.buy_spec" :key="r.ticker">
              <td class="tk">{{ r.ticker }}</td>
              <td class="theme">{{ r.theme }}</td>
              <td class="rd-flat">{{ r.close.toFixed(2) }}</td>
              <td class="rd-cyan strong">{{ fmtNum(r.sup, 2) }}</td>
              <td class="rd-flat">{{ r.sup_n }}次</td>
              <td :class="[dirCls(r.dist_sup), 'strong']">{{ fmtPct(r.dist_sup, 1) }}</td>
              <td :class="(r.rsi ?? 50) >= 70 ? 'rd-amber' : 'rd-flat'">{{ fmtNum(r.rsi, 0) }}</td>
              <td :class="dirCls(r.w1)">{{ fmtPct(r.w1) }}</td>
              <td class="inval">{{ invalidLevel(r.sup) }}</td>
            </tr>
          </tbody>
        </table>
      </template>

      <div class="band band-watch">
        ○ 观察梯队 · 距支撑≤5%（{{ d.watch.length }}）
      </div>
      <table class="rd-table lr">
        <tbody>
          <tr v-for="r in d.watch" :key="r.ticker">
            <td class="tk">{{ r.ticker }}</td>
            <td class="theme">{{ r.theme }}</td>
            <td class="rd-flat">{{ r.close.toFixed(2) }}</td>
            <td class="rd-cyan strong">{{ fmtNum(r.sup, 2) }}</td>
            <td class="rd-flat">{{ r.sup_n }}次</td>
            <td :class="[dirCls(r.dist_sup), 'strong']">{{ fmtPct(r.dist_sup, 1) }}</td>
            <td :class="(r.rsi ?? 50) >= 70 ? 'rd-amber' : 'rd-flat'">{{ fmtNum(r.rsi, 0) }}</td>
            <td :class="dirCls(r.w1)">{{ fmtPct(r.w1) }}</td>
            <td class="inval">{{ invalidLevel(r.sup) }}</td>
          </tr>
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
.rule {
  margin-bottom: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  color: var(--text-dim);
}
.panel {
  overflow-x: auto;
  background: var(--rd-panel);
  border: 1px solid color-mix(in srgb, var(--rd-cyan) 30%, var(--border));
  border-radius: var(--radius-sm);
}
.lr {
  min-width: 760px;
  font-size: 11.5px;
}
.lr .rd-table th {
  font-size: 9.5px;
  letter-spacing: 0.15em;
}
.lr .rd-table td {
  padding: 7px 10px;
}
/* 梯队条带：靠底色把三档隔开，滚动时不会看错档 */
.band {
  padding: 6px 12px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.2em;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.band:first-child {
  border-top: none;
}
.band-hit {
  background: var(--rd-cyan-dim);
  color: var(--rd-cyan);
}
.band-spec {
  background: var(--rd-amber-dim);
  color: var(--rd-amber);
}
.band-watch {
  background: color-mix(in srgb, var(--bg) 40%, transparent);
  color: var(--text-muted);
}
.rd-table tbody tr.hit {
  background: var(--rd-cyan-dim);
}
.tk {
  font-weight: 700;
}
.theme {
  font-family: inherit;
  font-size: 11.5px;
  color: var(--text-muted);
  text-align: left;
}
.strong {
  font-weight: 600;
}
.inval {
  color: color-mix(in srgb, var(--rd-amber) 90%, transparent);
}
.empty {
  padding: 12px !important;
  text-align: center;
  font-family: inherit;
  color: var(--text-dim);
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