<script setup lang="ts">
// 16 新闻实质判断：把新闻按「是否改变基本面」分四档。
//
// 这块的作用是过滤噪音：同一条消息，实质性（改变盈利/现金流/利率/供需的事实）
// 值得进模型，偏情绪（观点/言论）不值得。判定与影响方向分两套颜色：
// 判定=青/琥珀/灰/紫（性质），影响=涨跌色（方向），两者不能混用。
import { type NewsRow, type WatchRow } from '../../data/usRadar'

defineProps<{ news: NewsRow[]; watchlist?: WatchRow[] }>()

const VERDICT_STYLE: Record<string, { fg: string }> = {
  实质性: { fg: 'var(--rd-cyan)' },
  混合: { fg: 'var(--rd-amber)' },
  偏情绪: { fg: 'var(--text-muted)' },
  事件预告: { fg: 'var(--rd-violet)' },
}

function verdictFg(v: string): string {
  return VERDICT_STYLE[v]?.fg ?? 'var(--text-muted)'
}

/**
 * 影响方向 → 颜色。
 * 注意「利空能源/利好科技」这种复合判定：它同时含利好和利空，
 * 规则必须先判「含利好且不含利空」再判「含利空」，否则复合值会被错判成单一利空。
 */
function impactCls(impact: string): string {
  if (impact.includes('利好') && !impact.includes('利空')) return 'rd-up'
  if (impact.includes('利空')) return 'rd-down'
  if (impact.includes('不确定')) return 'rd-amber'
  return 'rd-cyan'
}
</script>

<template>
  <div>
    <div class="legend">
      <span>判定口径：</span>
      <span><i style="background: var(--rd-cyan)" />实质性 = 改变盈利/现金流/利率/供需的事实</span>
      <span><i style="background: var(--text-muted)" />偏情绪 = 观点/言论/短期资金行为，无基本面变化</span>
      <span><i style="background: var(--rd-amber)" />混合 = 两者兼有</span>
      <span><i style="background: var(--rd-violet)" />事件预告 = 未落地，等结果</span>
    </div>

    <div class="grid">
      <article
        v-for="(n, i) in news"
        :key="i"
        class="card"
        :style="{ borderLeftColor: impactCls(n.impact) }"
      >
        <div class="tags">
          <span class="rd-pill verdict" :style="{ color: verdictFg(n.verdict) }">
            {{ n.verdict }}
          </span>
          <span class="rd-pill" :class="impactCls(n.impact)">{{ n.impact }}</span>
          <span class="rd-pill scope">{{ n.scope }}</span>
          <span v-for="t in n.tickers" :key="t" class="ticker">{{ t }}</span>
        </div>

        <h3 class="title">{{ n.title }}</h3>
        <p class="note">{{ n.note }}</p>
      </article>
    </div>
  </div>
</template>

<style scoped>
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin-bottom: 12px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  color: var(--text-dim);
}
.legend i {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 4px;
  border-radius: 50%;
}
.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
@media (min-width: 1000px) {
  .grid {
    grid-template-columns: 1fr 1fr;
  }
}
.card {
  padding: 12px 14px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  /* 左条用影响方向色，与判定色区分开 */
  border-left-width: 3px;
  border-radius: var(--radius-sm);
}
.tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.verdict {
  border: 1px solid currentColor;
  background: color-mix(in srgb, var(--text) 4%, transparent);
}
.scope {
  background: color-mix(in srgb, var(--text) 4%, transparent);
  color: var(--text-dim);
}
.ticker {
  padding: 1px 6px;
  border-radius: 2px;
  background: var(--rd-panel2);
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--text-muted);
}
.title {
  margin-top: 8px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}
.note {
  margin-top: 6px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-muted);
}
</style>