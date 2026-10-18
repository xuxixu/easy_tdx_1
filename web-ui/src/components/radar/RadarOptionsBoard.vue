<script setup lang="ts">
// 14 期权结构 · 代表股：用期权链的成交量口径验证价格判断。
//
// PCR(量) = 看跌成交量 / 看涨成交量。<1 说明 call 端成交更拥挤（偏多头预期），
// 越高说明 put 端更活跃。热门行权价表示「钱打了多少」，不表示方向——
// 成交量不区分开平仓，一个「买看涨」和一个「卖看涨」在 PCR 里完全一样，
// 所以它只能说明拥挤度，不能当成持仓成本。这也是数据边界要单独写一行的原因。
import { fmtVolK, pcrVerdict, type OptionsBlock } from '../../data/usRadar'

defineProps<{ o: OptionsBlock }>()

/** 看涨成交占比（0-100），驱动 call/put 比例条 */
function callPct(callVol: number, putVol: number): number {
  const total = callVol + putVol
  return total > 0 ? (callVol / total) * 100 : 50
}
</script>

<template>
  <div>
    <div class="grid">
      <article v-for="c in o.chains" :key="c.ticker" class="card">
        <header class="head">
          <span class="ticker">{{ c.ticker }}</span>
          <span class="exp">{{ c.exp }} 到期</span>
        </header>

        <div class="spot">
          <span class="rd-dim">现货 {{ c.spot.toFixed(2) }}</span>
          <span class="role" :title="c.role">{{ c.role }}</span>
        </div>

        <div class="pcr" :class="pcrVerdict(c.pcr_vol).cls">
          <span class="pcr-key">PCR(量)</span>
          <span class="pcr-val">{{ c.pcr_vol.toFixed(2) }}</span>
          <span class="pcr-label">{{ pcrVerdict(c.pcr_vol).label }}</span>
        </div>

        <div
          class="bar"
          role="img"
          :aria-label="`看涨成交 ${fmtVolK(c.call_vol)} 占 ${callPct(c.call_vol, c.put_vol).toFixed(1)}%，看跌成交 ${fmtVolK(c.put_vol)}`"
        >
          <span class="bar-call" :style="{ width: `${callPct(c.call_vol, c.put_vol)}%` }" />
          <span class="bar-put" :style="{ width: `${100 - callPct(c.call_vol, c.put_vol)}%` }" />
        </div>

        <div class="vols">
          <span>CALL {{ fmtVolK(c.call_vol) }}</span>
          <span>PUT {{ fmtVolK(c.put_vol) }}</span>
        </div>

        <div class="hot">
          <div class="hot-row">
            <span class="hot-key">看涨热点</span>
            <span v-for="s in c.hot_calls" :key="`c-${s.strike}`" class="hot-item hot-call">
              {{ s.strike }}<span class="hot-vol">({{ fmtVolK(s.volume) }})</span>
            </span>
          </div>
          <div class="hot-row">
            <span class="hot-key">看跌热点</span>
            <span v-for="s in c.hot_puts" :key="`p-${s.strike}`" class="hot-item hot-put">
              {{ s.strike }}<span class="hot-vol">({{ fmtVolK(s.volume) }})</span>
            </span>
          </div>
        </div>

        <footer class="foot">链数据 {{ c.chain_date }}</footer>
      </article>
    </div>

    <div class="rd-callout">
      <span class="key rd-cyan">结论</span>
      <span class="txt">{{ o.conclusion }}</span>
    </div>
    <p class="boundary">数据边界：{{ o.note }}</p>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
@media (min-width: 760px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (min-width: 1200px) {
  .grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
.grid > * {
  min-width: 0;
}
.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.ticker {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.3px;
}
.exp {
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.04em;
  color: var(--text-dim);
  white-space: nowrap;
}
.spot {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
}
.role {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: inherit;
  font-size: 10px;
  color: var(--rd-cyan);
  opacity: 0.85;
}
.pcr {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 4px;
}
.pcr-key {
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.12em;
  color: var(--text-dim);
}
.pcr-val {
  font-family: var(--font-mono);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.1;
}
.pcr-label {
  font-family: var(--font-mono);
  font-size: 10px;
}
.bar {
  display: flex;
  height: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--rd-line);
}
.bar > span {
  display: block;
  height: 100%;
  opacity: 0.85;
}
.bar-call {
  background: var(--up);
}
.bar-put {
  background: var(--down);
}
.vols {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
.hot {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px solid var(--rd-line);
  font-family: var(--font-mono);
  font-size: 10px;
}
.hot-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
}
.hot-key {
  color: var(--text-dim);
}
.hot-item {
  margin-right: 4px;
}
.hot-call {
  color: var(--up);
}
.hot-put {
  color: var(--down);
}
.hot-vol {
  color: var(--text-dim);
}
.foot {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
  opacity: 0.8;
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