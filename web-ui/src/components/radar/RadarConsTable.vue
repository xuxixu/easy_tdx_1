<script setup lang="ts">
// 板块/细分板块下钻用的成分表（板块行点击后展开的那张）。
//
// 为什么单独一个组件而不是把总表裁几列：总表 20 列是给「全池筛选」用的，
// 下钻场景关心的是「这个板块里谁在动」，列少但要能一眼看到质地和信号——
// 复用总表会带出一堆恒为空值的列，反而更难扫。
import { QUALITY_COLOR, SIGNAL_META, dirCls, fmtNum, type ConsRow } from '../../data/usRadar'

withDefaults(defineProps<{ rows: ConsRow[]; showTheme?: boolean }>(), { showTheme: false })

/** RSI 染色：≥70 超买（红）、≤35 超卖（绿） */
function rsiCls(rsi: number | null | undefined): string {
  if (rsi === null || rsi === undefined || !Number.isFinite(rsi)) return 'rd-flat'
  if (rsi >= 70) return 'rd-up'
  if (rsi <= 35) return 'rd-down'
  return 'rd-flat'
}

/** 量比染色阈值比别处更严（1.5）：下钻表本身已是异动子集，再宽就没意义 */
function volCls(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return 'rd-flat'
  return v >= 1.5 ? 'rd-amber' : 'rd-flat'
}
</script>

<template>
  <div class="cons">
    <table class="rd-table">
      <thead>
        <tr>
          <th>代码</th>
          <th v-if="showTheme">题材</th>
          <th>现价</th>
          <th>日</th>
          <th>周</th>
          <th>月</th>
          <th>RSI</th>
          <th>量比</th>
          <th>质地</th>
          <th>信号</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.ticker">
          <td class="cons-ticker">{{ r.ticker }}</td>
          <td v-if="showTheme" class="cons-theme" :title="r.theme">{{ r.theme }}</td>
          <td class="rd-flat">{{ fmtNum(r.close) }}</td>
          <td :class="dirCls(r.d1)">{{ fmtNum(r.d1, 1) }}%</td>
          <td :class="[dirCls(r.w1), 'strong']">{{ fmtNum(r.w1, 1) }}%</td>
          <td :class="dirCls(r.m1)">{{ fmtNum(r.m1, 1) }}%</td>
          <td :class="rsiCls(r.rsi)">{{ fmtNum(r.rsi, 0) }}</td>
          <td :class="volCls(r.vol_ratio)">{{ fmtNum(r.vol_ratio) }}</td>
          <td class="cons-mid">
            <span class="rd-pill" :style="{ color: QUALITY_COLOR[r.quality] ?? 'var(--text-dim)' }">
              {{ r.quality || '—' }}
            </span>
          </td>
          <td class="cons-sig">
            <span
              v-for="s in r.signals"
              :key="s"
              class="rd-pill sig"
              :style="{ color: SIGNAL_META[s]?.color ?? 'var(--text-dim)' }"
            >
              {{ SIGNAL_META[s]?.text ?? s }}
            </span>
          </td>
        </tr>
        <tr v-if="rows.length === 0">
          <td :colspan="showTheme ? 10 : 9" class="cons-empty">观测池内暂无该板块成分</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.cons {
  overflow-x: auto;
  background: color-mix(in srgb, var(--bg) 40%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  border-radius: var(--radius-sm);
}
.cons .rd-table {
  min-width: 860px;
  font-size: 10.5px;
}
.cons .rd-table th {
  font-size: 9px;
  letter-spacing: 0.14em;
}
.cons .rd-table td {
  padding: 5px 8px;
}
/* 周涨幅加粗：下钻场景最常看的就是「这一周谁强」 */
.strong {
  font-weight: 600;
}
.cons-ticker {
  font-size: 11px;
  font-weight: 700;
}
.cons-theme {
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: inherit;
  font-size: 10.5px;
  color: var(--text-dim);
  text-align: left;
}
.cons-mid {
  text-align: center;
}
.cons-sig {
  text-align: left;
}
.rd-pill {
  background: color-mix(in srgb, var(--text) 4%, transparent);
}
.sig {
  margin-right: 4px;
}
.cons-empty {
  padding: 12px !important;
  text-align: center;
  font-family: inherit;
  color: var(--text-dim);
}
</style>