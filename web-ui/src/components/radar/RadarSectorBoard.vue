<script setup lang="ts">
// 04 板块轮动：12 个板块 ETF，点行展开该板块在观测池内的成分。
//
// 月动量用「中轴双向条」：全表共用一个归一化上限（各板块 |m1| 的最大值），
// 这样不同板块的条长可以横向比较。只按各行自身归一的话，每根条都一样长，
// 反而看不出谁强谁弱——这是这类图表最容易做错的地方。
import { computed, ref } from 'vue'

import RadarConsTable from './RadarConsTable.vue'
import { dirCls, fmtNum, fmtPct, type Num, type RadarData } from '../../data/usRadar'

const props = defineProps<{ data: RadarData }>()

/** 展开中的板块 ticker；null = 全部收起 */
const open = ref<string | null>(null)

/** 全表归一上限：|月涨幅| 的最大值，保证条长可横向比较 */
const maxM1 = computed(() =>
  Math.max(...props.data.sectors.map((s) => Math.abs(s.m1 ?? 0)), 1),
)

/** 单行的条：长度 = |m1|/max * 50%，方向按正负从中轴展开 */
function momentumBar(m1: Num) {
  const v = m1 ?? 0
  const half = Math.min(Math.abs(v) / maxM1.value, 1) * 50
  return {
    width: `${half}%`,
    left: v > 0 ? '50%' : `${50 - half}%`,
    background: v > 0 ? 'var(--up)' : 'var(--down)',
    // 轻微辉光让中轴两侧的红绿在密集表格里更跳一点
    boxShadow: v > 0 ? '0 0 8px var(--rd-up-dim)' : '0 0 8px var(--rd-down-dim)',
  }
}

function toggle(ticker: string) {
  open.value = open.value === ticker ? null : ticker
}
</script>

<template>
  <div class="wrap">
    <div class="scroll">
      <table class="rd-table sec">
        <thead>
          <tr>
            <th>板块ETF（点击展开观测池成分）</th>
            <th>日</th>
            <th>周</th>
            <th>月</th>
            <th class="axis-col">月度动量（以月中轴）</th>
            <th>3月</th>
            <th title="相对强度 = 板块月涨幅 − SPY月涨幅">RS·1月</th>
            <th>量比</th>
            <th>距高点</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(s, i) in data.sectors" :key="s.ticker">
            <tr
              class="rd-drill sec-row"
              :class="{ open: open === s.ticker }"
              @click="toggle(s.ticker)"
            >
              <td>
                <span class="idx-no">{{ String(i + 1).padStart(2, '0') }}</span>
                <span class="caret" :class="{ on: open === s.ticker }">▶</span>
                <b class="tk">{{ s.ticker }}</b>
                <span class="nm">{{ s.name }}</span>
                <span class="cnt">{{ s.constituents?.length ?? 0 }}只</span>
              </td>
              <td :class="dirCls(s.d1)">{{ fmtPct(s.d1) }}</td>
              <td :class="dirCls(s.w1)">{{ fmtPct(s.w1) }}</td>
              <td :class="[dirCls(s.m1), 'strong']">{{ fmtPct(s.m1) }}</td>
              <td>
                <div class="axis">
                  <div class="axis-mid" />
                  <div class="axis-bar" :style="momentumBar(s.m1)" />
                </div>
              </td>
              <td :class="dirCls(s.m3)">{{ fmtPct(s.m3) }}</td>
              <td :class="[dirCls(s.rs_1m), 'strong']">{{ fmtPct(s.rs_1m) }}</td>
              <!-- 量比阈值 1.25 与全站一致，超阈值用青色（异常而非涨跌） -->
              <td>
                <span :class="(s.vol_ratio ?? 0) >= 1.25 ? 'rd-cyan' : 'rd-flat'">
                  {{ fmtNum(s.vol_ratio) }}
                </span>
              </td>
              <td :class="dirCls(s.from_hi)">{{ fmtPct(s.from_hi, 1) }}</td>
            </tr>
            <tr v-if="open === s.ticker" class="expand-row">
              <td colspan="9" class="expand-cell">
                <RadarConsTable :rows="s.constituents ?? []" show-theme />
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <p class="note">
      读法：RS&gt;0 表示跑赢标普500。成分为观测池内按GICS归类的个股（SMH为半导体相关细分合集），
      点击任意板块行展开。量比≥1.25 高亮（5日均量/20日均量）。
    </p>
  </div>
</template>

<style scoped>
.wrap {
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.scroll {
  overflow-x: auto;
}
.sec {
  min-width: 860px;
  font-size: 11.5px;
}
.sec .rd-table th {
  font-size: 9.5px;
  letter-spacing: 0.15em;
}
.sec-row > td {
  padding: 7px 10px;
}
.sec-row.open {
  background: var(--rd-cyan-dim);
}
.idx-no {
  display: inline-block;
  width: 18px;
  margin-right: 6px;
  color: var(--text-dim);
}
.caret {
  display: inline-block;
  margin-right: 4px;
  font-size: 9px;
  color: var(--text-dim);
  transition: transform 0.15s ease;
}
.caret.on {
  transform: rotate(90deg);
}
.tk {
  margin-right: 4px;
  font-weight: 600;
}
.nm {
  font-family: inherit;
  color: var(--text-muted);
}
.cnt {
  margin-left: 5px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
}
.strong {
  font-weight: 600;
}
.axis-col {
  text-align: center;
}
.axis {
  position: relative;
  display: flex;
  align-items: center;
  height: 14px;
}
.axis-mid {
  position: absolute;
  left: 50%;
  top: 0;
  width: 1px;
  height: 100%;
  background: color-mix(in srgb, var(--text-dim) 60%, transparent);
}
.axis-bar {
  position: absolute;
  top: 3px;
  height: 8px;
  border-radius: 1px;
  opacity: 0.85;
}
.expand-cell {
  padding: 8px 10px !important;
  background: color-mix(in srgb, var(--bg) 30%, transparent);
}
.note {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  font-size: 10.5px;
  line-height: 1.7;
  color: var(--text-dim);
}
</style>