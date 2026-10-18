<script setup lang="ts">
// 盘后快照滚动条：当日涨跌幅最大的 10 只 + 各板块 ETF 周涨跌，横向无缝滚动。
//
// 为什么是「渲染两遍再左移 -50%」：无缝跑马灯的标准做法。一份内容靠
// translateX 走完自身宽度就会露出空白，复制两份拼在一起、走完一半宽度
// 时第二份正好补上第一份让出的位置，视觉上永远接得上。
// 悬停暂停（鼠标移到条上才停），否则密集数字没法看。
import { computed } from 'vue'

import { dirCls, fmtPct, type Num, type RadarData } from '../../data/usRadar'

const props = defineProps<{ data: RadarData }>()

interface Tick {
  key: string
  label: string
  val: Num
  suffix: string
}

const ticks = computed<Tick[]>(() => {
  // 异动股按当日绝对涨跌幅排序取前 10——「谁在动」比「动了多少」更重要
  const movers = [...props.data.anomalies]
    .sort((a, b) => Math.abs(b.d1 ?? 0) - Math.abs(a.d1 ?? 0))
    .slice(0, 10)
    .map<Tick>((r) => ({ key: `m-${r.ticker}`, label: r.ticker, val: r.d1, suffix: ' 日' }))
  const sectors = props.data.sectors.map<Tick>((s) => ({
    key: `s-${s.ticker}`,
    label: `${s.ticker}·${s.name}`,
    val: s.w1,
    suffix: ' 周',
  }))
  return [...movers, ...sectors]
})
</script>

<template>
  <div class="rd-marquee">
    <div class="rd-marquee-track">
      <span v-for="copy in 2" :key="copy" class="rd-marquee-run">
        <span v-for="t in ticks" :key="`${copy}-${t.key}`" class="rd-marquee-item">
          <span class="rd-marquee-label">{{ t.label }}</span>
          <span :class="dirCls(t.val)">{{ fmtPct(t.val) }}</span>
          <span class="rd-marquee-suffix">{{ t.suffix }}</span>
          <span class="rd-marquee-div">│</span>
        </span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.rd-marquee {
  overflow: hidden;
  padding: 6px 0;
  background: var(--rd-panel);
  border-bottom: 1px solid var(--border);
}
.rd-marquee-track {
  display: inline-flex;
  white-space: nowrap;
  /* 60s 走完全程：数字滚动太快就没法读了，这个速度刚好能扫读 */
  animation: rd-marquee 60s linear infinite;
}
/* 悬停暂停——密集数字必须能停下来看 */
.rd-marquee:hover .rd-marquee-track {
  animation-play-state: paused;
}
.rd-marquee-run {
  display: inline-flex;
}
.rd-marquee-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 16px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.04em;
}
.rd-marquee-label {
  color: var(--text-muted);
}
.rd-marquee-suffix {
  color: var(--text-dim);
}
.rd-marquee-div {
  margin-left: 12px;
  color: var(--border);
}
/* 位移到 -50% = 正好一份内容的宽度，配合两份渲染实现无缝循环 */
@keyframes rd-marquee {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-50%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .rd-marquee-track {
    animation: none;
  }
}
</style>