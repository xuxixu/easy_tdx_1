<script setup lang="ts">
// 02 大盘环境：5 大指数 + 10Y 美债 + 宏观资产表。
//
// 这一块回答「总仓位给多少」。10Y 单独用琥珀色卡：它是本轮定价的主导变量，
// 利率一动，成长/公用/地产的估值分母就跟着变——所以它不该和指数挤在同一排里
// 当作普通一行看。
import { dirCls, fmtNum, fmtPct, type Num, type RadarData } from '../../data/usRadar'

defineProps<{ data: RadarData }>()

/** 指数卡与 TNX 卡共用：左边名称+代码，下面三档日/周/月 */
function cells(row: { d1: Num; w1: Num; m1: Num }): [string, Num][] {
  return [
    ['日', row.d1],
    ['周', row.w1],
    ['月', row.m1],
  ]
}
</script>

<template>
  <div class="env">
    <div class="env-cards">
      <div v-for="r in data.index" :key="r.ticker" class="idx">
        <div class="idx-head">
          <span class="idx-name">{{ r.name }}</span>
          <span class="idx-code">{{ r.ticker }}</span>
        </div>
        <div class="idx-close">{{ fmtNum(r.close) }}</div>
        <div class="idx-grid">
          <div v-for="[k, v] in cells(r)" :key="k" class="idx-cell">
            <div class="idx-cell-k">{{ k }}</div>
            <div :class="dirCls(v)">{{ fmtPct(v) }}</div>
          </div>
        </div>
        <div class="idx-foot">
          距6月高点 <b :class="dirCls(r.from_hi)">{{ fmtPct(r.from_hi, 1) }}</b>
          <template v-if="r.ma50_dist !== null">
            · MA50 <b :class="dirCls(r.ma50_dist)">{{ fmtPct(r.ma50_dist, 1) }}</b>
          </template>
        </div>
      </div>

      <div class="idx idx-tnx">
        <div class="idx-head">
          <span class="idx-name rd-amber">10Y美债收益率</span>
          <span class="idx-code">^TNX</span>
        </div>
        <div class="idx-close rd-amber">{{ fmtNum(data.tnx.close) }}</div>
        <div class="idx-grid">
          <div v-for="[k, v] in cells(data.tnx)" :key="k" class="idx-cell">
            <div class="idx-cell-k">{{ k }}</div>
            <div :class="dirCls(v)">{{ fmtPct(v) }}</div>
          </div>
        </div>
        <div class="idx-foot tnx">2007年来高位 · 本轮定价主导变量</div>
      </div>
    </div>

    <div class="macro-wrap">
      <table class="rd-table">
        <thead>
          <tr>
            <th>宏观资产</th>
            <th>收盘</th>
            <th>日</th>
            <th>周</th>
            <th>月</th>
            <th>3月</th>
            <th>量比</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in data.macro" :key="m.ticker">
            <td><span class="nm">{{ m.name }}</span> <span class="rd-dim">{{ m.ticker }}</span></td>
            <td class="rd-flat">{{ fmtNum(m.close) }}</td>
            <td :class="dirCls(m.d1)">{{ fmtPct(m.d1) }}</td>
            <td :class="dirCls(m.w1)">{{ fmtPct(m.w1) }}</td>
            <td :class="dirCls(m.m1)">{{ fmtPct(m.m1) }}</td>
            <td :class="dirCls(m.m3)">{{ fmtPct(m.m3) }}</td>
            <td class="rd-flat">{{ fmtNum(m.vol_ratio) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.env {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.env-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
@media (min-width: 640px) {
  .env-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (min-width: 1200px) {
  .env-cards {
    grid-template-columns: repeat(6, 1fr);
  }
}
.idx {
  padding: 10px 12px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
/* TNX 卡用琥珀描边把它从指数群里分出来 */
.idx-tnx {
  border-color: color-mix(in srgb, var(--rd-amber) 40%, var(--border));
}
.idx-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.idx-name {
  font-size: 12px;
  font-weight: 600;
}
.idx-code {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.2em;
  color: var(--text-dim);
}
.idx-close {
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 19px;
  font-weight: 700;
  line-height: 1;
}
.idx-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 10.5px;
}
.idx-cell-k {
  font-size: 8.5px;
  letter-spacing: 0.2em;
  color: var(--text-dim);
}
.idx-foot {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--text-dim);
}
.idx-foot.tnx {
  color: color-mix(in srgb, var(--rd-amber) 80%, transparent);
}
.macro-wrap {
  overflow-x: auto;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.macro-wrap .rd-table {
  min-width: 640px;
}
.nm {
  color: var(--text);
}
</style>