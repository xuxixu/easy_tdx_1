<script setup lang="ts">
// 美股看板右侧栏的期权摘要：把完整卡片压成「一行一只」的两行式，
// 只保留扫一眼能用的三件事——PCR 分档、call/put 成交占比、最密集行权价。
// 完整版在 /us-options。
//
// 与 UsOptionChainCard 共用同一份数据和同一套 PCR 分档，两处不会算出不同结论。
import { computed } from 'vue'

import { US_OPTION_CHAINS, callSharePct, fmtChainVol, pcrVerdict } from '../data/usOptions'

const chains = US_OPTION_CHAINS

const rows = computed(() =>
  chains.map((chain) => ({
    chain,
    verdict: pcrVerdict(chain.pcr),
    callPct: callSharePct(chain),
    // 只取最密集的一个行权价：右栏宽度放三个热点会挤成两行，反而看不出重点
    topCall: chain.hotCalls[0],
    topPut: chain.hotPuts[0],
  })),
)

/** 摘要：整体是 call 拥挤还是 put 拥挤，给右栏顶部一句话 */
const summary = computed(() => {
  const bulls = rows.value.filter((r) => r.verdict.tone === 'bull' || r.verdict.tone === 'strong-bull')
  if (bulls.length === 0) return '无偏多标的'
  return `${bulls.length}/${rows.value.length} 只 call 端拥挤`
})
</script>

<template>
  <section class="rail">
    <header class="rail-head">
      <div>
        <h3>期权结构</h3>
        <p class="rail-sub mono">{{ summary }}</p>
      </div>
      <RouterLink to="/us-options" class="rail-more">全部 →</RouterLink>
    </header>

    <div class="rail-list">
      <article v-for="r in rows" :key="r.chain.ticker" class="rail-row">
        <div class="row-top">
          <div class="row-id">
            <span class="row-ticker mono">{{ r.chain.ticker }}</span>
            <span class="row-spot mono">{{ r.chain.spot.toFixed(2) }}</span>
          </div>
          <div class="row-pcr mono" :class="`tone-${r.verdict.tone}`">
            <span class="row-pcr-val">{{ r.chain.pcr.toFixed(2) }}</span>
            <span class="row-pcr-label">{{ r.verdict.label }}</span>
          </div>
        </div>

        <div
          class="row-bar"
          role="img"
          :aria-label="`看涨成交 ${fmtChainVol(r.chain.callVol)} 占 ${r.callPct.toFixed(1)}%，看跌成交 ${fmtChainVol(r.chain.putVol)}`"
        >
          <span class="bar-call" :style="{ width: `${r.callPct}%` }" />
        </div>

        <div class="row-hot mono">
          <span class="hot-call" v-if="r.topCall">
            看涨 {{ r.topCall.strike }}
          </span>
          <span class="hot-put" v-if="r.topPut">看跌 {{ r.topPut.strike }}</span>
        </div>
      </article>
    </div>

    <p class="rail-note">
      PCR = 看跌/看涨成交量，成交量不分开平仓；<RouterLink to="/us-options">口径与结论 →</RouterLink>
    </p>
  </section>
</template>

<style scoped>
.rail {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.rail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-2);
  padding-bottom: var(--sp-2);
  border-bottom: 1px solid var(--border);
}
.rail-head h3 {
  font-size: var(--fs-base);
  font-weight: 600;
}
.rail-sub {
  margin-top: 2px;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.rail-more {
  flex-shrink: 0;
  font-size: var(--fs-xs);
  text-decoration: none;
  white-space: nowrap;
}
.rail-more:hover {
  text-decoration: underline;
}
.rail-list {
  display: flex;
  flex-direction: column;
}
.rail-row {
  padding: var(--sp-2) 0;
  border-bottom: 1px solid var(--hairline);
}
.rail-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.row-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
}
.row-id {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  min-width: 0;
}
.row-ticker {
  font-size: var(--fs-base);
  font-weight: 700;
}
.row-spot {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.row-pcr {
  display: flex;
  align-items: baseline;
  gap: var(--sp-1);
  flex-shrink: 0;
}
.row-pcr-val {
  font-size: var(--fs-md);
  font-weight: 700;
}
.row-pcr-label {
  font-size: 10px;
}
/* 比例条只画 call 一侧：剩余空间天然就是 put，右栏窄，画满两段反而看不出对比 */
.row-bar {
  display: flex;
  height: 4px;
  margin: var(--sp-1) 0 3px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--down);
  opacity: 0.85;
}
.bar-call {
  display: block;
  height: 100%;
  background: var(--up);
}
.row-hot {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
}
.hot-call {
  color: var(--up);
}
.hot-put {
  color: var(--down);
}
.rail-note {
  padding-top: var(--sp-2);
  border-top: 1px solid var(--border);
  font-size: 10px;
  line-height: 1.6;
  color: var(--text-dim);
}
.tone-strong-bull,
.tone-bull {
  color: var(--up);
}
.tone-balanced {
  color: var(--warn);
}
.tone-bear {
  color: var(--down);
}
</style>