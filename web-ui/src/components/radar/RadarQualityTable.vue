<script setup lang="ts">
// 09 基本面质地分层：把「优质」和「情绪/投机」两张表并排放，让人分开处理。
//
// 两张表结构完全一样，只是顶部强调色不同（青=可按投资逻辑对待、琥珀=按交易逻辑），
// 所以抽成一个带 accent 的表格组件复用，而不是写两遍。
// 质地分的配色：≥85 青（优秀）/ ≥55 中性 / 其余琥珀（偏弱）。
import { dirCls, fmtNum, fmtPct, type QualityRow } from '../../data/usRadar'

defineProps<{
  /** 中文表头 */
  title: string
  /** 英文小标 */
  en: string
  rows: QualityRow[]
  /** 顶部强调色 */
  accent: string
}>()

/** 质地分配色 */
function scoreCls(score: number | null | undefined): string {
  if (score === null || score === undefined || !Number.isFinite(score)) return 'rd-dim'
  if (score >= 85) return 'rd-cyan'
  if (score >= 55) return ''
  return 'rd-amber'
}

/** FCF：正为红（与全站「好=红」一致）、负为绿 */
function fcfCls(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return 'rd-dim'
  return v > 0 ? 'rd-up' : 'rd-down'
}
</script>

<template>
  <div class="qt">
    <div class="qt-head" :style="{ borderTop: `2px solid ${accent}` }">
      <span class="qt-title">{{ title }}</span>
      <span class="qt-en">{{ en }}</span>
    </div>
    <div class="scroll">
      <table class="rd-table">
        <thead>
          <tr>
            <th>代码</th>
            <th>题材</th>
            <th>质地分</th>
            <th>营收</th>
            <th>净利率</th>
            <th>FCF</th>
            <th>机构</th>
            <th>空头</th>
            <th>关键事实</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.ticker">
            <td class="tk">{{ r.ticker }}</td>
            <td class="theme" :title="r.theme">{{ r.theme }}</td>
            <td :class="['strong', scoreCls(r.score)]">{{ r.score ?? '—' }}</td>
            <td :class="dirCls(r.rev_growth)">{{ fmtPct(r.rev_growth, 0) }}</td>
            <td :class="dirCls(r.profit_margin)">{{ fmtPct(r.profit_margin, 0) }}</td>
            <td :class="fcfCls(r.fcf_b)">
              {{ r.fcf_b === null ? '—' : `$${fmtNum(r.fcf_b, 1)}B` }}
            </td>
            <td class="rd-flat">{{ r.inst === null ? '—' : `${fmtNum(r.inst, 0)}%` }}</td>
            <!-- 做空 ≥10% 视为拥挤空头，用琥珀标出 -->
            <td :class="(r.short ?? 0) >= 10 ? 'rd-amber' : 'rd-flat'">
              {{ r.short === null ? '—' : `${fmtNum(r.short, 1)}%` }}
            </td>
            <td class="flags" :title="r.flags">{{ r.flags }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.qt {
  overflow: hidden;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.qt-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
.qt-title {
  font-size: 13px;
  font-weight: 600;
}
.qt-en {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}
.scroll {
  overflow-x: auto;
}
.scroll .rd-table {
  min-width: 680px;
  font-size: 10.5px;
}
.scroll .rd-table th {
  font-size: 9px;
  letter-spacing: 0.14em;
}
.scroll .rd-table td {
  padding: 7px 8px;
}
.strong {
  font-weight: 700;
}
.tk {
  font-size: 11.5px;
  font-weight: 700;
}
.theme {
  max-width: 92px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: inherit;
  font-size: 10.5px;
  color: var(--text-dim);
  text-align: left;
}
.flags {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: inherit;
  font-size: 10.5px;
  color: var(--text-dim);
  text-align: left;
}
</style>