<script setup lang="ts">
// 03 油价 · 地缘风险：WTI/布伦特/天然气区间条 + 事件时间线 + 传导路径。
//
// 区间条用琥珀色而不是涨跌色：它表示「价格处在 6 月区间的哪个位置」，
// 是位置而非涨跌，用红绿会让人误读成今天的涨跌方向。
import { dirCls, fmtNum, fmtPct, type GeoOilBlock } from '../../data/usRadar'

defineProps<{ d: GeoOilBlock }>()
</script>

<template>
  <div>
    <div class="oil-cards">
      <div v-for="p in d.prices" :key="p.ticker" class="oil">
        <div class="oil-name">{{ p.name }}</div>
        <div class="oil-price">
          <span class="oil-close">{{ fmtNum(p.close) }}</span>
          <span :class="dirCls(p.d1)">{{ fmtPct(p.d1, 1) }}</span>
        </div>
        <div class="oil-chg">
          <span>周 <b :class="dirCls(p.w1)">{{ fmtPct(p.w1, 1) }}</b></span>
          <span>月 <b :class="dirCls(p.m1)">{{ fmtPct(p.m1, 1) }}</b></span>
        </div>
        <div v-if="p.pos !== null" class="oil-range">
          <div class="rd-track">
            <i :style="{ width: `${p.pos}%`, background: 'var(--rd-amber)', opacity: 0.8 }" />
          </div>
          <div class="oil-range-legend">
            <span>{{ p.lo }}</span>
            <span>6月区间 {{ p.pos }}%</span>
            <span>{{ p.hi }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="geo-cols">
      <div class="rd-panel">
        <div class="geo-head">
          <span>2026 美伊冲突 · 油价时间线</span>
          <span class="rd-pill rd-risk">风险：{{ d.risk_level }}</span>
        </div>
        <div class="tl">
          <!-- 最后一条用琥珀描边：最新进展是当前定价里最需要盯的那条 -->
          <div
            v-for="(t, i) in d.timeline"
            :key="t.date"
            class="tl-item"
            :class="{ last: i === d.timeline.length - 1 }"
          >
            <span class="tl-date">{{ t.date }}</span>
            <span class="tl-text">{{ t.event }}</span>
          </div>
        </div>
      </div>

      <div class="rd-panel">
        <div class="geo-head"><span>对美股的传导路径</span></div>
        <div class="trans">
          <div v-for="(t, i) in d.transmission" :key="i" class="trans-item">
            <span class="trans-no">{{ String(i + 1).padStart(2, '0') }}</span>
            <span>{{ t }}</span>
          </div>
        </div>
        <div v-if="d.equities.length" class="equity-note">
          能源股对照：
          <span v-for="e in d.equities" :key="e.ticker" class="equity-item">
            {{ e.name }} 周 <b :class="dirCls(e.w1)">{{ fmtPct(e.w1, 1) }}</b>
          </span>
          <span class="rd-amber">
            — 对比油价周{{ fmtPct(d.prices[0]?.w1 ?? null, 1) }}，看股油是否背离
          </span>
        </div>
      </div>
    </div>

    <div class="rd-callout mt">
      <span class="callout-key rd-cyan">结论</span>
      <span class="callout-text">{{ d.conclusion }}</span>
    </div>
  </div>
</template>

<style scoped>
.oil-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
@media (min-width: 760px) {
  .oil-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (min-width: 1200px) {
  .oil-cards {
    grid-template-columns: repeat(6, 1fr);
  }
}
.oil {
  padding: 10px 12px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
}
.oil-name {
  font-size: 9px;
  letter-spacing: 0.14em;
  color: var(--text-dim);
}
.oil-price {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-top: 4px;
  font-size: 10.5px;
}
.oil-close {
  font-size: 17px;
  font-weight: 700;
}
.oil-chg {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 9.5px;
  color: var(--text-dim);
}
.oil-range {
  margin-top: 6px;
}
.oil-range .rd-track {
  height: 4px;
}
.oil-range-legend {
  display: flex;
  justify-content: space-between;
  margin-top: 2px;
  font-size: 8.5px;
  color: var(--text-dim);
}
.geo-cols {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  margin-top: 8px;
}
@media (min-width: 1200px) {
  .geo-cols {
    grid-template-columns: 1fr 1fr;
  }
}
.geo-cols > * {
  min-width: 0;
}
.geo-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}
.rd-risk {
  background: var(--rd-amber-dim);
  color: var(--rd-amber);
}
.tl-item {
  display: flex;
  gap: 12px;
  padding: 0 0 10px 12px;
  border-left: 2px solid var(--border);
}
.tl-item.last {
  padding-bottom: 0;
  border-left-color: var(--rd-amber);
}
.tl-date {
  width: 64px;
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--rd-amber);
}
.tl-text {
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-muted);
}
.trans {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.trans-item {
  display: flex;
  gap: 8px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-muted);
}
.trans-no {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--rd-cyan);
}
.equity-note {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
.equity-item {
  margin-right: 12px;
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
  font-size: 12px;
  line-height: 1.7;
}
</style>