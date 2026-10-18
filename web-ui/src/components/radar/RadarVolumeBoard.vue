<script setup lang="ts">
// 15 量能异动：量比 ≥1.25 且 当日 |涨跌| ≥3% 的标的。
//
// 这里对原站做了一处修正：原站的表格有「周」和「距6月高点」两列，但它读的
// 量能异动数据里根本没有这两个字段，所以那两列恒为「—」。快照里同一张
// watchlist 总表含这两列且以代码为键，直接补上即可，不必留着两列空值。
import { computed } from 'vue'

import {
  SIGNAL_META,
  dirCls,
  fmtNum,
  fmtPct,
  type AnomalyRow,
  type Num,
  type RadarData,
} from '../../data/usRadar'

const props = defineProps<{ data: RadarData }>()

interface Row extends AnomalyRow {
  /** 从总表补齐的周涨幅 / 距高点 */
  w1: Num
  from_hi: Num
}

const rows = computed<Row[]>(() => {
  // 建索引：总表 299 行，逐行 find 是 O(n²)，这里一次建表
  const byTicker = new Map(props.data.watchlist.map((w) => [w.ticker, w]))
  return props.data.anomalies.map((a) => {
    const full = byTicker.get(a.ticker)
    return { ...a, w1: full?.w1 ?? null, from_hi: full?.from_hi ?? null }
  })
})
</script>

<template>
  <div class="wrap">
    <div class="scroll">
      <table class="rd-table vol">
        <thead>
          <tr>
            <th>代码</th>
            <th>所属主题</th>
            <th>量比·5/20日</th>
            <th>当日</th>
            <th>周</th>
            <th>距6月高点</th>
            <th>信号</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.ticker">
            <td class="tk">{{ r.ticker }}</td>
            <td class="theme">{{ r.theme }}</td>
            <td class="rd-cyan strong">{{ fmtNum(r.vol_ratio) }}</td>
            <td :class="[dirCls(r.d1), 'strong']">{{ fmtPct(r.d1) }}</td>
            <td :class="dirCls(r.w1)">{{ fmtPct(r.w1) }}</td>
            <td :class="dirCls(r.from_hi)">{{ fmtPct(r.from_hi, 1) }}</td>
            <td class="sig-cell">
              <!-- 放量方向药丸：涨用红底、跌用绿底，与全站红涨绿跌一致 -->
              <span
                class="rd-pill"
                :class="(r.d1 ?? 0) > 0 ? 'pill-up' : 'pill-down'"
              >
                {{ (r.d1 ?? 0) > 0 ? '放量上涨' : '放量下跌' }}
              </span>
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
        </tbody>
      </table>
    </div>

    <p class="note">
      筛选规则：量比≥1.25 且 当日|涨跌|≥3%。放量是「资金关注度」信号而非方向信号——放量上涨需看是否接近前高（追高风险），
      放量下跌需看是否跌破关键均线。
    </p>
  </div>
</template>

<style scoped>
.wrap {
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.scroll {
  overflow-x: auto;
}
.vol {
  min-width: 720px;
  font-size: 11.5px;
}
.vol .rd-table th {
  font-size: 9.5px;
  letter-spacing: 0.15em;
}
.vol .rd-table td {
  padding: 5px 10px;
}
.strong {
  font-weight: 600;
}
.tk {
  font-family: inherit;
  font-weight: 700;
}
.theme {
  font-family: inherit;
  font-size: 11px;
  color: var(--text-muted);
  text-align: left;
}
.pill-up {
  background: var(--rd-up-dim);
  color: var(--up);
}
.pill-down {
  background: var(--rd-down-dim);
  color: var(--down);
}
.sig-cell {
  text-align: left;
}
.sig {
  margin-left: 4px;
  background: color-mix(in srgb, var(--text) 4%, transparent);
}
.note {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  font-size: 10.5px;
  line-height: 1.7;
  color: var(--text-dim);
}
</style>