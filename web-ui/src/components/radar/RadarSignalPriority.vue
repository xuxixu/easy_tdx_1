<script setup lang="ts">
// 今日信号专列：把 18 个区块里「今天需要动手看」的行提到最前面。
//
// 为什么要单独提出来而不是让用户自己滚到第 12/11 区块找：风控信号和机会信号
// 分处两个区块（兑现信号 / 左侧雷达），但实际使用是同一个动作——今天先处理
// 哪几个。这里按「先风控后机会」并排，风控在前是因为亏损优先处理。
//
// 预警的优先级顺序也照原站口径：超买乖离 → 放量破位 → 高位放量阴线 →
// 恐慌观察 → 跌破MA5。越靠前越严重，所以只取前 8 条。
import { computed } from 'vue'

import {
  SIGNAL_META,
  dirCls,
  fmtNum,
  fmtPct,
  type RadarData,
  type SignalRow,
} from '../../data/usRadar'

const props = defineProps<{ data: RadarData }>()

interface AlertRow {
  key: string
  sig: string
  r: SignalRow
  /** 一句话说明「为什么触发」，比信号名本身更能帮人判断 */
  metric: string
}

const alerts = computed<AlertRow[]>(() => {
  const e = props.data.exits
  const out: AlertRow[] = [
    ...e.overext.map((r) => ({
      key: `overext-${r.ticker}`,
      sig: 'OVEREXT',
      r,
      metric: `RSI ${fmtNum(r.rsi, 1)} · 一等风控`,
    })),
    ...e.breakdown_vol.map((r) => ({
      key: `bdv-${r.ticker}`,
      sig: 'BREAKDOWN_VOL',
      r,
      metric: `量比 ${fmtNum(r.vol_ratio, 2)} · 执行级`,
    })),
    ...e.dist_candle.map((r) => ({
      key: `dc-${r.ticker}`,
      sig: 'DIST_CANDLE',
      r,
      metric: `距高点 ${fmtNum(r.from_hi, 1)}%`,
    })),
    ...(e.panic_watch ?? []).slice(0, 3).map((r) => ({
      key: `pw-${r.ticker}`,
      sig: 'PANIC_WATCH',
      r,
      metric: '趋势内急跌 · 观察',
    })),
    ...e.lost_ma5.slice(0, 4).map((r) => ({
      key: `ma5-${r.ticker}`,
      sig: 'LOST_MA5',
      r,
      metric: `乖离 ${fmtNum(r.bias5, 1)}%`,
    })),
  ]
  return out
})

const shownAlerts = computed(() => alerts.value.slice(0, 8))
const opps = computed(() => props.data.left.buy.slice(0, 6))
const shownBreakouts = computed(() => props.data.exits.breakout_vol.slice(0, 4))

/** 分化警报：板块内部子组价差触发的组数 */
const firedDivergences = computed(() =>
  (props.data.divergence?.rows ?? []).filter((r) => r.fired),
)
</script>

<template>
  <section class="rd-signals">
    <header class="rd-signals-head">
      <h2 class="rd-signals-title">今日信号专列</h2>
      <span class="rd-tag">
        SIGNALS FIRST · 预警 {{ alerts.length }} · 机会 {{ opps.length + shownBreakouts.length }}
      </span>
      <span
        v-if="firedDivergences.length"
        class="rd-signals-alert"
      >
        ⚡ 分化警报×{{ firedDivergences.length }}：{{
          firedDivergences.map((r) => r.name.split(' vs ')[0]).join(' / ')
        }}
      </span>
    </header>

    <div class="rd-signals-grid">
      <!-- 风控列：先处理风险 -->
      <div>
        <div class="rd-signals-label rd-down">风控预警（先处理风险）</div>
        <div class="rd-signals-list">
          <div v-for="a in shownAlerts" :key="a.key" class="rd-sig-row">
            <span class="rd-sig-ticker">{{ a.r.ticker }}</span>
            <span
              class="rd-sig-badge"
              :style="{ color: SIGNAL_META[a.sig]?.color ?? 'var(--rd-down)' }"
            >
              {{ SIGNAL_META[a.sig]?.text ?? a.sig }}
            </span>
            <span class="rd-sig-metric">{{ a.metric }}</span>
            <span class="rd-sig-pct" :class="dirCls(a.r.d1)">{{ fmtPct(a.r.d1) }}</span>
          </div>
          <div v-if="shownAlerts.length === 0" class="rd-empty">今日无触发</div>
        </div>
      </div>

      <!-- 机会列：需各自满足触发条件，不是买入指令 -->
      <div>
        <div class="rd-signals-label rd-up">机会关注（需满足各自触发条件）</div>
        <div class="rd-signals-list">
          <div v-for="r in shownBreakouts" :key="`bo-${r.ticker}`" class="rd-sig-row">
            <span class="rd-sig-ticker">{{ r.ticker }}</span>
            <span class="rd-sig-badge rd-badge-cyan">放量突破</span>
            <span class="rd-sig-metric">
              量比 {{ fmtNum(r.vol_ratio, 2) }} · 距6月高点 {{ fmtNum(r.from_hi, 1) }}%
            </span>
            <span class="rd-sig-pct" :class="dirCls(r.d1)">{{ fmtPct(r.d1) }}</span>
          </div>
          <div v-for="r in opps" :key="`op-${r.ticker}`" class="rd-sig-row">
            <span class="rd-sig-ticker">{{ r.ticker }}</span>
            <span class="rd-sig-badge rd-badge-up">回踩支撑</span>
            <span class="rd-sig-metric">
              支撑 {{ fmtNum(r.sup, 2) }}（{{ r.sup_n }}次触碰）· 距
              {{ fmtNum(r.dist_sup, 1) }}%
            </span>
            <span class="rd-sig-pct" :class="dirCls(r.w1)">周{{ fmtPct(r.w1) }}</span>
          </div>
          <div v-if="opps.length + shownBreakouts.length === 0" class="rd-empty">
            今日无触发
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.rd-signals {
  padding: 14px;
  background: var(--rd-panel);
  border: 1px solid color-mix(in srgb, var(--rd-amber) 35%, var(--border));
  border-radius: var(--radius-sm);
}
.rd-signals-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  margin-bottom: 10px;
}
.rd-signals-title {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.rd-signals-alert {
  padding: 1px 6px;
  border-radius: 2px;
  background: var(--rd-amber-dim);
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 700;
  color: var(--rd-amber);
}
.rd-signals-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}
@media (min-width: 900px) {
  .rd-signals-grid {
    grid-template-columns: 1fr 1fr;
  }
}
.rd-signals-label {
  margin-bottom: 6px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.18em;
}
.rd-signals-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rd-sig-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
  border-radius: 3px;
  background: color-mix(in srgb, var(--bg) 40%, transparent);
}
.rd-sig-ticker {
  /* 定宽：不同代码长度不一，不定宽会让后面的标签列左右跳 */
  width: 48px;
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
}
.rd-sig-badge {
  flex-shrink: 0;
  padding: 1px 4px;
  border-radius: 2px;
  background: var(--rd-up-dim);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
}
/* 两枚徽标语义不同（放量突破=进攻 / 回踩支撑=左侧），给不同底色避免混读 */
.rd-badge-cyan {
  background: color-mix(in srgb, var(--rd-cyan) 12%, transparent);
  color: var(--rd-cyan);
}
.rd-badge-up {
  background: color-mix(in srgb, var(--up) 12%, transparent);
  color: var(--up);
}
.rd-sig-metric {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--text-dim);
}
.rd-sig-pct {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 10px;
}
.rd-empty {
  font-size: 10.5px;
  color: var(--text-dim);
}
</style>