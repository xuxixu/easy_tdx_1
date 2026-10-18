<script setup lang="ts">
// 09 基本面质地分层的装配层：口径说明 + 分布统计 + 两张表 + 结论。
import RadarQualityTable from './RadarQualityTable.vue'
import type { QualityBlock } from '../../data/usRadar'

defineProps<{ q: QualityBlock }>()

/** 分布统计的展示顺序：优质→中性→情绪/投机→未知，从好到差排 */
const SUMMARY_ROWS = [
  { key: 'quality_n', label: '优质' },
  { key: 'neutral_n', label: '中性' },
  { key: 'spec_n', label: '情绪/投机' },
  { key: 'unknown_n', label: '数据不足' },
] as const
</script>

<template>
  <div>
    <p class="method">{{ q.methodology }}</p>

    <div class="dist">
      <span class="rd-label">分布</span>
      <span class="dist-n">普通股 {{ q.summary.equity_n }} 只</span>
      <span v-for="s in SUMMARY_ROWS" :key="s.key" class="dist-item">
        {{ s.label }}
        <b>{{ q.summary[s.key] }}</b>
      </span>
    </div>

    <div class="grid">
      <RadarQualityTable
        title="优质 · 可按投资逻辑处理"
        en="QUALITY CORE"
        :rows="q.top"
        accent="var(--rd-cyan)"
      />
      <RadarQualityTable
        title="情绪/投机 · 只按交易逻辑处理"
        en="SPECULATIVE"
        :rows="q.speculative"
        accent="var(--rd-amber)"
      />
    </div>

    <div class="rd-callout">
      <span class="key rd-cyan">结论</span>
      <span class="txt">{{ q.conclusion }}</span>
    </div>
  </div>
</template>

<style scoped>
.method {
  margin-bottom: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  line-height: 1.7;
  color: var(--text-dim);
}
.dist {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 16px;
  margin-bottom: 8px;
  padding: 7px 12px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-muted);
}
.dist-n {
  font-family: var(--font-mono);
}
.dist-item b {
  margin-left: 4px;
  font-family: var(--font-mono);
  color: var(--text);
}
.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
/* 质量表内含 min-width:680px 的宽表；不加 min-width:0 会被它撑破轨道 */
.grid > * {
  min-width: 0;
}
@media (min-width: 1100px) {
  .grid {
    grid-template-columns: 1fr 1fr;
  }
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