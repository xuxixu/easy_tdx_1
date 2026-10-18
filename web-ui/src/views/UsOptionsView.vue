<script setup lang="ts">
// 美股期权结构：用期权链的成交量口径验证价格判断。
//
// 一句话读法——PCR(量) = 看跌成交量 / 看涨成交量。
// 数值越低说明 call 端成交越拥挤（市场在买上涨的期权），越高说明 put 端更拥挤；
// 配合「最密集行权价」看市场把注意力放在哪个价位上。
//
// 当前数据是静态 mock（见 data/usOptions.ts 的说明）：项目后端还没有期权链
// 接口。页面结构按真实接口的返回形状写好，接上数据源即可直接用。
import { computed } from 'vue'

import HelpCollapse from '../components/HelpCollapse.vue'
import PageShell from '../components/PageShell.vue'
import RiskDisclaimer from '../components/RiskDisclaimer.vue'
import UsOptionChainCard from '../components/UsOptionChainCard.vue'
import {
  US_OPTION_CHAINS,
  US_OPTION_CONCLUSION,
  US_OPTION_MOCK_NOTICE,
  US_OPTION_NOTE,
  pcrVerdict,
  summarizeChains,
} from '../data/usOptions'

const chains = US_OPTION_CHAINS
const summary = summarizeChains(chains)

/** 工具条上的分档计数：让人一眼看到这批标的偏多还是偏空，而不是逐张读 PCR */
const toneCounts = computed(() => {
  const buckets = { strongBull: 0, bull: 0, balanced: 0, bear: 0 }
  for (const c of chains) {
    const tone = pcrVerdict(c.pcr).tone
    if (tone === 'strong-bull') buckets.strongBull++
    else if (tone === 'bull') buckets.bull++
    else if (tone === 'balanced') buckets.balanced++
    else buckets.bear++
  }
  return buckets
})

/** 全批统一的到期日；不同标的到期日不一致时如实提示，不假装是同一天 */
const expLabel = computed(() => {
  const exps = new Set(chains.map((c) => c.exp))
  if (exps.size !== 1) return `${chains.length} 个到期日`
  return `${chains[0]?.exp ?? '-'} 到期`
})
</script>

<template>
  <PageShell title="美股期权结构" :desc="summary">
    <template #toolbar>
      <span class="tool-item">
        <span class="tool-key">到期</span>
        <span class="mono">{{ expLabel }}</span>
      </span>
      <span class="tool-item">
        <span class="tool-key">分档</span>
        <span class="mono tone-strong-bull">强多头 {{ toneCounts.strongBull }}</span>
        <span class="mono tone-bull">偏多头 {{ toneCounts.bull }}</span>
        <span class="mono tone-balanced">均衡 {{ toneCounts.balanced }}</span>
        <span class="mono tone-bear">偏空头 {{ toneCounts.bear }}</span>
      </span>
      <span class="tool-item mock-notice">{{ US_OPTION_MOCK_NOTICE }}</span>
    </template>

    <div class="chain-grid">
      <UsOptionChainCard v-for="chain in chains" :key="chain.ticker" :chain="chain" />
    </div>

    <div class="conclusion">
      <span class="conclusion-key">结论</span>
      <span class="conclusion-text">{{ US_OPTION_CONCLUSION }}</span>
    </div>

    <p class="boundary">
      <span class="boundary-key">数据边界</span>{{ US_OPTION_NOTE }}
    </p>

    <HelpCollapse label="PCR 怎么读">
      <ul class="help-list">
        <li><b>PCR(量) = 看跌成交量 ÷ 看涨成交量</b>，只统计当月到期的合约。</li>
        <li>
          <b>≤0.50 强多头</b>：call 端极度拥挤，短线情绪往往已在亢奋区间，追高要付溢价。
        </li>
        <li><b>0.50 ~ 0.75 偏多头</b>：看涨预期占优但未到极端。</li>
        <li><b>0.75 ~ 1.00 均衡</b>：多空成交接近，没有明显偏向。</li>
        <li><b>&gt;1.00 偏空头</b>：put 端成交更活跃，防守或对冲需求上升。</li>
        <li>
          <b>热点行权价</b>是成交最密集的价位，代表注意力集中处；实值/虚值要结合现货价看，
          不能只看数字大小。
        </li>
        <li>
          <b>最关键的限制</b>：成交量不区分开平仓，一个「买入看涨」和一个「卖出看涨」在
          PCR 里完全一样。因此 PCR 只能说明拥挤度，不能直接当成持仓成本或净方向。
        </li>
      </ul>
    </HelpCollapse>

    <RiskDisclaimer />
  </PageShell>
</template>

<style scoped>
.chain-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--sp-3);
  align-items: start;
}
.tool-item {
  display: inline-flex;
  align-items: baseline;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
  color: var(--text-muted);
}
.tool-key {
  color: var(--text-dim);
  font-size: var(--fs-xs);
}
/* mock 声明用弱化的告警色块：不抢卡片视觉，但常驻在页头避免误当真实行情 */
.mock-notice {
  padding: 3px var(--sp-2);
  border: 1px solid var(--warn-line);
  border-radius: var(--radius-sm);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: var(--fs-xs);
  line-height: 1.5;
}
.conclusion {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  padding: var(--sp-3);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--accent) 7%, transparent);
}
.conclusion-key {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  font-weight: 700;
  letter-spacing: 0.16em;
  color: var(--accent);
}
.conclusion-text {
  font-size: var(--fs-base);
  line-height: 1.7;
}
.boundary {
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--radius-sm);
  background: var(--warn-soft);
  font-size: var(--fs-xs);
  line-height: 1.7;
  color: var(--warn);
}
.boundary-key {
  margin-right: var(--sp-2);
  font-weight: 600;
}
.help-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: var(--fs-sm);
  line-height: 1.7;
  color: var(--text-muted);
  list-style: none;
}
.help-list b {
  color: var(--text);
  font-weight: 600;
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