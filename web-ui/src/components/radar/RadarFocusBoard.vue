<script setup lang="ts">
// 13 焦点个股：顶部代码切换 + 单只个股的四栏详情（形态/期权/基本面/催化剂）。
//
// 四栏的设计意图是「同一只票的四个独立视角互相对照」：形态说趋势、期权说资金预期、
// 基本面说估值、催化说事件。任何一栏与其它三栏冲突时（比如形态超买但基本面优秀），
// 那个矛盾本身就是判断依据，所以四栏必须并排出现而不是折叠。
import { computed, ref } from 'vue'

import {
  SIGNAL_META,
  dirCls,
  fmtNum,
  fmtPct,
  type FocusBlock,
  type FocusStock,
} from '../../data/usRadar'

const props = defineProps<{ f: FocusBlock }>()

const active = ref(0)
/** 越界保护：快照更新后 stocks 变少时不要渲染成 undefined */
const stock = computed<FocusStock | undefined>(() =>
  props.f.stocks[Math.min(active.value, props.f.stocks.length - 1)],
)
</script>

<template>
  <div>
    <div class="tabs">
      <button
        v-for="(s, i) in f.stocks"
        :key="s.ticker"
        class="tab"
        :class="{ on: i === active }"
        @click="active = i"
      >
        {{ s.ticker }}
        <span class="tab-d1" :class="dirCls(s.price.d1)">{{ fmtPct(s.price.d1) }}</span>
      </button>
      <span class="note">{{ f.note }}</span>
    </div>

    <article v-if="stock" class="card">
      <header class="head">
        <div>
          <div class="head-row">
            <span class="ticker">{{ stock.ticker }}</span>
            <span class="name">{{ stock.name }}</span>
            <span class="rd-pill reason">{{ stock.reason }}</span>
          </div>
          <div class="price-row">
            <span class="price">{{ fmtNum(stock.price.close, 2) }}</span>
            <span :class="dirCls(stock.price.d1)">日 {{ fmtPct(stock.price.d1) }}</span>
            <span :class="dirCls(stock.price.w1)">周 {{ fmtPct(stock.price.w1) }}</span>
            <span :class="dirCls(stock.price.m1)">月 {{ fmtPct(stock.price.m1) }}</span>
            <span :class="dirCls(stock.price.m3)">3月 {{ fmtPct(stock.price.m3) }}</span>
            <span class="rd-dim">量比 {{ fmtNum(stock.price.vol_ratio) }}</span>
          </div>
        </div>
        <div v-if="stock.signals.length" class="signals">
          <span
            v-for="s in stock.signals"
            :key="s"
            class="rd-pill sig"
            :style="{ color: SIGNAL_META[s]?.color ?? 'var(--text-dim)', borderColor: SIGNAL_META[s]?.color ?? 'var(--border)' }"
          >
            {{ SIGNAL_META[s]?.text ?? s }}
          </span>
        </div>
      </header>

      <div class="cols">
        <!-- 形态：自动计算 -->
        <section class="col">
          <div class="col-tag">TECHNICAL</div>
          <div class="col-title">形态（自动计算）</div>
          <div class="col-body">{{ stock.technicals.text }}</div>
          <div class="kv-grid">
            <div>MA20 <b>{{ fmtNum(stock.technicals.ma20) }}</b></div>
            <div>MA50 <b>{{ fmtNum(stock.technicals.ma50) }}</b></div>
            <div>20日高 <b>{{ fmtNum(stock.technicals.hi20) }}</b></div>
            <div>距离 <b :class="dirCls(stock.technicals.dist_hi20)">{{ fmtPct(stock.technicals.dist_hi20, 1) }}</b></div>
          </div>
        </section>

        <!-- 期权：样本不足时明确降级，不留空 -->
        <section class="col">
          <div class="col-tag">OPTIONS</div>
          <div class="col-title">期权 · {{ stock.options ? `${stock.options.exp} 到期` : '期权' }}</div>
          <template v-if="stock.options">
            <div class="col-body">{{ stock.options.text }}</div>
            <div class="pcr">
              PCR(量)
              <b :class="stock.options.pcr_vol <= 0.5 ? 'rd-up' : stock.options.pcr_vol <= 0.75 ? 'rd-up' : stock.options.pcr_vol <= 1 ? 'rd-amber' : 'rd-down'">
                {{ stock.options.pcr_vol.toFixed(2) }}
              </b>
            </div>
            <div class="rd-dim pcr-note">
              看涨 {{ stock.options.hot_calls }}<br />看跌 {{ stock.options.hot_puts }}
            </div>
          </template>
          <div v-else class="col-body rd-dim">
            本标的期权成交样本不足或未纳入代表池，参考代表池期权结构模块。
          </div>
        </section>

        <!-- 基本面 -->
        <section class="col">
          <div class="col-tag">FUNDAMENTAL</div>
          <div class="col-title">基本面（自动计算）</div>
          <div class="kv-list">
            <div>市值 <b>{{ stock.fundamentals.mktcap ?? '—' }}</b> · 远期PE <b>{{ stock.fundamentals.fwd_pe ?? '—' }}</b></div>
            <div>营收增速 <b class="rd-up">{{ stock.fundamentals.rev_growth ?? '—' }}</b></div>
            <div>{{ stock.fundamentals.margin_note ?? '—' }}</div>
            <div>分析师 <b>{{ stock.fundamentals.analysts ?? '—' }}</b></div>
            <div>
              目标均价
              <b>{{ stock.fundamentals.target_mean != null ? `$${stock.fundamentals.target_mean}` : '—' }}</b>
              （区间 {{ stock.fundamentals.target_range ?? '—' }}）
            </div>
            <div>
              空头占比
              <b>{{ stock.fundamentals.short_pct != null ? `${stock.fundamentals.short_pct}%` : '—' }}</b>
            </div>
          </div>
        </section>

        <!-- 催化剂与风险 -->
        <section class="col">
          <div class="col-tag">CATALYSTS</div>
          <div class="col-title">催化剂与风险</div>
          <div v-if="stock.catalysts.length + stock.risks.length > 0" class="cat">
            <div v-for="(c, i) in stock.catalysts.slice(0, 3)" :key="`c${i}`" class="cat-row">
              <span class="rd-up">▲</span><span>{{ c }}</span>
            </div>
            <div v-for="(r, i) in stock.risks.slice(0, 2)" :key="`r${i}`" class="cat-row">
              <span class="rd-down">▼</span><span>{{ r }}</span>
            </div>
          </div>
          <div v-else class="col-body rd-dim">
            策展点评未覆盖本标的——以形态/期权/基本面三栏数据为准，次日简报补充点评。
          </div>
        </section>
      </div>

      <div class="rd-callout">
        <span class="key rd-cyan">结论</span>
        <span class="txt">{{ stock.conclusion }}</span>
      </div>
    </article>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.tab {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: transparent;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  transition: all 0.15s;
}
.tab:hover {
  border-color: var(--text-dim);
}
.tab.on {
  border-color: var(--rd-cyan);
  background: var(--rd-cyan-dim);
  color: var(--rd-cyan);
}
.tab-d1 {
  margin-left: 6px;
  font-size: 9.5px;
  font-weight: 400;
}
.note {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
}
.card {
  padding: 16px 18px;
  background: var(--rd-panel);
  border: 1px solid color-mix(in srgb, var(--rd-cyan) 30%, var(--border));
  border-radius: var(--radius-sm);
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 12px;
}
.ticker {
  font-family: var(--font-mono);
  font-size: 26px;
  font-weight: 700;
}
.name {
  font-size: 13px;
  color: var(--text-muted);
}
.reason {
  background: var(--rd-amber-dim);
  color: var(--rd-amber);
}
.price-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 16px;
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
}
.price {
  font-size: 22px;
  font-weight: 700;
}
.signals {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.sig {
  border: 1px solid;
  background: color-mix(in srgb, var(--text) 4%, transparent);
}
.cols {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  margin-top: 16px;
}
@media (min-width: 1000px) {
  .cols {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (min-width: 1400px) {
  .cols {
    grid-template-columns: repeat(4, 1fr);
  }
}
.col {
  padding: 12px;
  background: color-mix(in srgb, var(--bg) 60%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.col-tag {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.2em;
  color: var(--rd-cyan);
}
.col-title {
  margin: 4px 0 6px;
  font-size: 12px;
  font-weight: 600;
}
.col-body {
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-muted);
}
.kv-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px 8px;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
.kv-grid b {
  color: var(--text);
  font-weight: 400;
}
.kv-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-dim);
}
.kv-list b {
  color: var(--text);
  font-weight: 400;
}
.pcr {
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--text-dim);
}
.pcr b {
  font-size: 14px;
  font-weight: 700;
}
.pcr-note {
  margin-top: 4px;
  font-size: 10px;
  line-height: 1.7;
}
.cat {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cat-row {
  display: flex;
  gap: 6px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-muted);
}
.key {
  margin-right: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.2em;
}
.txt {
  font-size: 12.5px;
  line-height: 1.7;
}
</style>