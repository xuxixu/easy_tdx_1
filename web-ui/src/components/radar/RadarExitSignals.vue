<script setup lang="ts">
// 12 兑现 / 风控信号：7 张信号卡（3 列网格），每张卡有触发口径与命中的标的。
//
// 卡片的 hint 写的是「这条信号为什么值得信 / 凭什么不采纳」——比信号名本身
// 更重要：非趋势突破之所以默认不采纳，是因为回测为负期望，而不是因为它少见。
// 卡片顶部强调色即信号性质（琥珀=风控/观察、绿=离场、红=机会）。
import { computed } from 'vue'

import { fmtNum, fmtPct, type ExitsBlock, type SignalRow } from '../../data/usRadar'

const props = defineProps<{ d: ExitsBlock }>()

interface Card {
  title: string
  en: string
  accent: string
  hint: string
  rows: SignalRow[]
  /** 每行右侧的补充说明 */
  extra: (r: SignalRow) => string
}

const cards = computed<Card[]>(() => {
  const d = props.d
  // 量比类信号共用的说明：「涨跌 + 量比」两行里最重要的两个数
  const volExtra = (r: SignalRow) => `${fmtPct(r.d1)} 量${fmtNum(r.vol_ratio)}`
  return [
    {
      title: '超买乖离 · 一等风控',
      en: 'OVEREXTENDED · V2提权',
      accent: 'var(--rd-amber)',
      hint: 'RSI>80 → 提前减仓区，不必等大阴线（回测10日看空胜率58.8%，当前最有效风控信号）',
      rows: d.overext,
      extra: (r) => `乖离${fmtPct(r.bias5, 1)} RSI${fmtNum(r.rsi, 0)}`,
    },
    {
      title: '高位放量阴线',
      en: 'DISTRIBUTION CANDLE',
      accent: 'var(--down)',
      hint: '跌幅≥3% + 量比≥1.5 + 处于高位 → 出货特征',
      rows: d.dist_candle,
      extra: (r) => `${fmtPct(r.d1)} 量${fmtNum(r.vol_ratio)} 距高${fmtPct(r.from_hi, 0)}`,
    },
    {
      title: '放量破位 · 趋势外',
      en: 'BREAKDOWN · V2执行级',
      accent: 'var(--down)',
      hint: '跌破20日低点 + 量比≥1.5 + 价<MA50（趋势已坏） → 执行离场',
      rows: d.breakdown_vol,
      extra: volExtra,
    },
    {
      title: '恐慌破位 · 观察',
      en: 'PANIC WATCH · V2新增',
      accent: 'var(--rd-amber)',
      hint: '上升趋势中的放量破位：回测显示5日内平均反弹+4.4%，等1-2日确认再决策，不立即执行',
      rows: d.panic_watch ?? [],
      extra: volExtra,
    },
    {
      title: '放量突破 · 趋势内',
      en: 'BREAKOUT · V2过滤后',
      accent: 'var(--up)',
      hint: '放量过20日高点 + 价>MA50且MA50上行 → 突破候选',
      rows: d.breakout_vol,
      extra: volExtra,
    },
    {
      title: '非趋势突破 · 存疑',
      en: 'WEAK BREAKOUT · V2新增',
      accent: 'var(--text-dim)',
      hint: 'MA50下方的放量突破：回测为负期望，默认视为假突破，不采纳',
      rows: d.breakout_weak ?? [],
      extra: volExtra,
    },
    {
      title: '跌破MA5',
      en: 'LOST MA5 · 沿5日线卖的触发',
      accent: 'var(--down)',
      hint: '昨日收在MA5上方，今日跌破 → 右侧仓止盈纪律日',
      rows: d.lost_ma5,
      extra: (r) => `${fmtPct(r.d1)} MA5=${r.ma5 ? fmtNum(r.ma5, 1) : '—'}`,
    },
  ]
})
</script>

<template>
  <div>
    <div class="grid">
      <div
        v-for="c in cards"
        :key="c.en"
        class="card"
        :style="{ borderTop: `2px solid ${c.accent}` }"
      >
        <div class="card-head">
          <span class="card-title">{{ c.title }}</span>
          <span class="card-en">{{ c.en }}</span>
        </div>
        <p class="card-hint">{{ c.hint }}</p>

        <div v-if="c.rows.length === 0" class="card-empty">今日无触发</div>
        <div v-else class="card-rows">
          <span v-for="r in c.rows" :key="r.ticker" class="chip">
            <b>{{ r.ticker }}</b>
            <span class="chip-extra">{{ c.extra(r) }}</span>
          </span>
        </div>
      </div>
    </div>

    <div class="rd-callout">
      <span class="key rd-cyan">结论</span>
      <span class="txt">{{ d.conclusion }}</span>
    </div>
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
.card {
  padding: 12px 14px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.card-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.card-title {
  font-size: 13px;
  font-weight: 600;
}
.card-en {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}
.card-hint {
  margin: 2px 0 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  line-height: 1.6;
  color: var(--text-dim);
}
.card-empty {
  padding: 4px 0;
  font-size: 11px;
  color: var(--text-dim);
}
.card-rows {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding: 3px 6px;
  border: 1px solid var(--border);
  border-radius: 2px;
  background: color-mix(in srgb, var(--bg) 60%, transparent);
  font-family: var(--font-mono);
  font-size: 10px;
}
.chip b {
  font-weight: 600;
}
.chip-extra {
  color: var(--text-dim);
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