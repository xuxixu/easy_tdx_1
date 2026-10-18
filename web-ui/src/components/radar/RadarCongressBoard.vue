<script setup lang="ts">
// 10 国会山持仓：几位重点议员/总统的披露持仓卡 + 与观测池重合的标的。
//
// 两层信息：上层是「谁说了/持有什么」的原文摘要与利益冲突提示，
// 下层是「这些票在我们池子里现在表现如何」。分开是因为披露滞后 30-45 天——
// 把持仓和当前价格并排放会让人误以为可以跟着买，所以重合区明确按本周表现排序，
// 只作为「这些票现在在动什么」来读。
//
// 页尾必须带 note：披露滞后是有时效性的事实，不是免责声明套话。
import { computed } from 'vue'

import { dirCls, fmtPct, type CongressBlock, type WatchRow } from '../../data/usRadar'

const props = defineProps<{ c: CongressBlock; watchlist: WatchRow[] }>()

/** 观测池索引：人物卡上的代码要回池子里取本周涨跌 */
const byTicker = computed(() => new Map(props.watchlist.map((w) => [w.ticker, w])))

/** 与观测池重合的标的，按本周表现从强到弱 */
const overlapped = computed(() =>
  props.c.overlap
    .map((t) => byTicker.value.get(t))
    .filter((w): w is WatchRow => !!w)
    .sort((a, b) => (b.w1 ?? -999) - (a.w1 ?? -999)),
)
</script>

<template>
  <div>
    <div class="grid">
      <div v-for="f in c.figures" :key="f.name" class="card">
        <div class="card-head">
          <span class="card-name">{{ f.name }}</span>
          <span class="card-role">{{ f.role }}</span>
        </div>
        <p class="summary">{{ f.summary }}</p>
        <div class="tickers">
          <span
            v-for="t in f.tickers"
            :key="t"
            class="tk"
            :title="byTicker.get(t) ? `周 ${fmtPct(byTicker.get(t)?.w1, 1)}` : ''"
          >
            {{ t }}<span v-if="byTicker.get(t)" :class="dirCls(byTicker.get(t)?.w1)">
              {{ fmtPct(byTicker.get(t)?.w1, 0) }}
            </span>
          </span>
        </div>
        <p class="stance">{{ f.stance }}</p>
      </div>
    </div>

    <div class="rd-panel overlap">
      <div class="ov-head">
        国会山相关标的 × 观测池（{{ overlapped.length }}只重合）· 按本周表现排序
      </div>
      <div class="ov-list">
        <span v-for="w in overlapped" :key="w.ticker" class="ov-item">
          <b>{{ w.ticker }}</b>
          <span :class="dirCls(w.w1)">{{ fmtPct(w.w1, 1) }}</span>
          <span class="ov-m1 rd-dim">/ {{ fmtPct(w.m1, 0) }}</span>
        </span>
      </div>
    </div>

    <div class="rd-callout">
      <span class="key rd-cyan">结论</span>
      <span class="txt">{{ c.conclusion }}</span>
    </div>
    <p class="boundary">数据边界：{{ c.note }}</p>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
@media (min-width: 1200px) {
  .grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
/* 人物卡的摘要长度差异很大，不给 min-width:0 会被最长的那张撑破轨道 */
.grid > * {
  min-width: 0;
}
.card {
  display: flex;
  flex-direction: column;
  padding: 12px 14px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.card-name {
  font-size: 13.5px;
  font-weight: 700;
}
.card-role {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.04em;
  color: var(--text-dim);
}
.summary {
  margin-top: 8px;
  /* 摘要长度差异很大，让它撑开卡片，同排卡片底部（立场）对齐 */
  flex: 1;
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-muted);
}
.tickers {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.tk {
  padding: 1px 6px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--text) 5%, transparent);
  font-family: var(--font-mono);
  font-size: 9.5px;
}
.stance {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  font-size: 10.5px;
  line-height: 1.6;
  color: color-mix(in srgb, var(--rd-amber) 90%, transparent);
}
.overlap {
  margin-top: 8px;
}
.ov-head {
  margin-bottom: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}
.ov-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ov-item {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 10px;
}
.ov-item b {
  font-weight: 700;
}
.ov-m1 {
  font-size: 9px;
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