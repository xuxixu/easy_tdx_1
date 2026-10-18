<script setup lang="ts">
// 01 每日三板斧：QQQ / SPY / SOXX 三张卡。
//
// 这一块回答的是「今天该不该做个股」——先看大盘环境，再看主线。
// 三张卡的重点不在涨跌，而在均线排列：close 是否站在 MA5/MA20/MA50 之上，
// 分别用 ▲▼ 标出来，一眼看出是顺势还是逆势。
import { dirCls, fmtNum, fmtPct, type DailyBlock } from '../../data/usRadar'

defineProps<{ d: DailyBlock }>()
</script>

<template>
  <div>
    <div class="grid-3">
      <div v-for="r in d.rows" :key="r.ticker" class="card">
        <div class="card-head">
          <span class="card-ticker">{{ r.ticker }}</span>
          <span class="badge" :class="r.aligned ? 'badge-up' : 'badge-flat'">
            {{ r.aligned ? '多头排列' : '未排齐' }}
          </span>
        </div>

        <div class="price-row">
          <span class="price">{{ r.close.toFixed(2) }}</span>
          <span class="chg" :class="dirCls(r.d1)">日 {{ fmtPct(r.d1) }}</span>
          <span class="chg" :class="dirCls(r.w1)">周 {{ fmtPct(r.w1) }}</span>
        </div>

        <div class="ma-row">
          <div
            v-for="[label, value, above] in [
              ['MA5', r.ma5, r.close > r.ma5],
              ['MA20', r.ma20, r.close > r.ma20],
              ['MA50', r.ma50, r.close > r.ma50],
            ] as [string, number, boolean][]"
            :key="label"
            class="ma-cell"
          >
            <div :class="above ? 'rd-up' : 'rd-down'">{{ above ? '▲' : '▼' }} {{ label }}</div>
            <div class="rd-dim">{{ fmtNum(value, 1) }}</div>
          </div>
        </div>

        <div class="stat-row">
          <span>
            RSI
            <b :class="r.rsi >= 70 ? 'rd-up' : r.rsi <= 35 ? 'rd-down' : ''">{{ fmtNum(r.rsi, 1) }}</b>
          </span>
          <span>量比 {{ fmtNum(r.vol_ratio, 2) }}</span>
          <span>距高点 <b :class="dirCls(r.from_hi)">{{ fmtPct(r.from_hi, 1) }}</b></span>
        </div>
      </div>
    </div>

    <div class="rd-callout mt">
      <span class="callout-key rd-cyan">今天在玩什么</span>
      <span class="callout-text">{{ d.conclusion }}</span>
    </div>

    <div class="rd-callout rd-callout-warn mt">
      <span class="callout-key rd-amber">执行结论</span>
      <span class="callout-text dim">{{ d.playbook }}</span>
    </div>
  </div>
</template>

<style scoped>
.grid-3 {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
@media (min-width: 760px) {
  .grid-3 {
    grid-template-columns: repeat(3, 1fr);
  }
}
.card {
  padding: 14px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.card-ticker {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
}
.badge {
  padding: 1px 6px;
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.06em;
  font-weight: 600;
}
.badge-up {
  background: var(--rd-up-dim);
  color: var(--up);
}
.badge-flat {
  background: color-mix(in srgb, var(--text-muted) 14%, transparent);
  color: var(--text-muted);
}
.price-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-top: 6px;
}
.price {
  font-family: var(--font-mono);
  font-size: 20px;
  font-weight: 700;
}
.chg {
  font-size: 12px;
}
.ma-row {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  font-family: var(--font-mono);
  font-size: 10px;
}
.ma-cell {
  flex: 1;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: color-mix(in srgb, var(--bg) 60%, transparent);
  text-align: center;
}
.stat-row {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
.mt {
  margin-top: 8px;
}
.callout-key {
  margin-right: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.2em;
}
.callout-text {
  font-size: 12.5px;
  line-height: 1.7;
}
.callout-text.dim {
  font-size: 12px;
  color: var(--text-muted);
}
</style>