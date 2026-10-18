<script setup lang="ts">
// 单只标的的期权链卡片：现货 + PCR(量) 分档 + call/put 成交占比 + 热点行权价。
//
// 配色的一个刻意取舍：参考站按美股习惯把 call 画绿、put 画红；这里跟随本项目
// 既有的红涨绿跌语义（--up=红 / --down=绿，全站所有行情与热力图都这么用），
// 「看涨=红、看跌=绿」。两套配色混在一页里会让人重新学一次颜色。
import { computed } from 'vue'

import { callSharePct, fmtChainVol, pcrVerdict, type OptionChain } from '../data/usOptions'

const props = defineProps<{
  chain: OptionChain
}>()

const verdict = computed(() => pcrVerdict(props.chain.pcr))
const callPct = computed(() => callSharePct(props.chain))
const putPct = computed(() => 100 - callPct.value)

/** PCR 分档 → 颜色 class。tone 取自 pcrVerdict，class 名一一对应。 */
const toneClass = computed(() => `tone-${verdict.value.tone}`)
</script>

<template>
  <article class="chain">
    <header class="chain-head">
      <span class="chain-ticker mono">{{ chain.ticker }}</span>
      <span class="chain-exp mono">{{ chain.exp }} 到期</span>
    </header>

    <div class="chain-spot mono">
      <span class="dim">现货 {{ chain.spot.toFixed(2) }}</span>
      <span class="chain-role" :title="chain.role">{{ chain.role }}</span>
    </div>

    <div class="chain-pcr mono" :class="toneClass">
      <span class="chain-pcr-key">PCR(量)</span>
      <span class="chain-pcr-val">{{ chain.pcr.toFixed(2) }}</span>
      <span class="chain-pcr-verdict">{{ verdict.label }}</span>
    </div>

    <!-- 比例条同时是「多空成交量对比」和「PCR 的图形化」，aria 里把数字补全 -->
    <div
      class="chain-bar"
      role="img"
      :aria-label="`看涨成交 ${fmtChainVol(chain.callVol)}，占 ${callPct.toFixed(1)}%；看跌成交 ${fmtChainVol(chain.putVol)}，占 ${putPct.toFixed(1)}%`"
    >
      <span class="bar-call" :style="{ width: `${callPct}%` }" />
      <span class="bar-put" :style="{ width: `${putPct}%` }" />
    </div>

    <div class="chain-vols mono">
      <span>CALL {{ fmtChainVol(chain.callVol) }}</span>
      <span>PUT {{ fmtChainVol(chain.putVol) }}</span>
    </div>

    <div class="chain-hot mono">
      <div class="hot-row">
        <span class="hot-key">看涨热点</span>
        <span v-for="s in chain.hotCalls" :key="`c-${s.strike}`" class="hot-item hot-call">
          {{ s.strike }}<span class="hot-vol">({{ fmtChainVol(s.volume) }})</span>
        </span>
      </div>
      <div class="hot-row">
        <span class="hot-key">看跌热点</span>
        <span v-for="s in chain.hotPuts" :key="`p-${s.strike}`" class="hot-item hot-put">
          {{ s.strike }}<span class="hot-vol">({{ fmtChainVol(s.volume) }})</span>
        </span>
      </div>
    </div>

    <footer class="chain-foot mono">链数据 {{ chain.chainDate }}</footer>
  </article>
</template>

<style scoped>
.chain {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.chain-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
}
.chain-ticker {
  font-size: var(--fs-lg);
  font-weight: 700;
  letter-spacing: 0.3px;
}
.chain-exp {
  font-size: var(--fs-xs);
  color: var(--text-dim);
  white-space: nowrap;
}
.chain-spot {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
  font-size: var(--fs-xs);
}
/* 角色说明给足宽度并省略：写长了会把「现货」挤掉，而角色本身只是辅助注释 */
.chain-role {
  font-family: inherit;
  font-size: var(--fs-xs);
  color: var(--accent);
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.chain-pcr {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
}
.chain-pcr-key {
  font-size: var(--fs-xs);
  letter-spacing: 0.12em;
  color: var(--text-dim);
}
.chain-pcr-val {
  font-size: var(--fs-2xl);
  font-weight: 700;
  line-height: 1.1;
}
.chain-pcr-verdict {
  font-size: var(--fs-xs);
}
.chain-bar {
  display: flex;
  height: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--hairline);
}
.chain-bar span {
  display: block;
  height: 100%;
}
.bar-call {
  background: var(--up);
  opacity: 0.85;
}
.bar-put {
  background: var(--down);
  opacity: 0.85;
}
.chain-vols {
  display: flex;
  justify-content: space-between;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.chain-hot {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  padding-top: var(--sp-2);
  border-top: 1px solid var(--hairline);
  font-size: var(--fs-xs);
}
.hot-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--sp-2);
}
.hot-key {
  color: var(--text-dim);
}
.hot-item {
  margin-right: var(--sp-1);
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
.chain-foot {
  font-size: 10px;
  color: var(--text-dim);
  opacity: 0.8;
}

/* PCR 分档配色：强多头与偏多头同色，只是字重不同——两档差的是程度不是方向，
   换成两个色相反而会让人以为「偏多头」是另一种市况 */
.tone-strong-bull,
.tone-bull {
  color: var(--up);
}
.tone-strong-bull .chain-pcr-val {
  font-weight: 700;
}
.tone-bull .chain-pcr-val {
  font-weight: 600;
}
.tone-balanced {
  color: var(--warn);
}
.tone-bear {
  color: var(--down);
}
.tone-balanced .chain-pcr-val,
.tone-bear .chain-pcr-val {
  font-weight: 600;
}
</style>