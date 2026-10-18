<script setup lang="ts">
// 18 自选总表：299 只观测池的全字段表，支持搜索 / 题材筛选 / 质地筛选 / 点表头排序。
//
// 这是整页的兜底表——前 17 个区块都是「筛选后的结论」，这里是「原始数据」，
// 用来核对结论对不对。所以列给得全（质地分、机构持股、距支撑/压力、量比…），
// 且默认按月涨幅降序：最新一期最值得看的排在最前面。
//
// 排序细节：null 一律沉底（不分升降序）。若把 null 当 0 处理，
// 缺失数据的票会混在中间甚至冒充「跌幅最小」。
import { computed, ref } from 'vue'

import {
  QUALITY_COLOR,
  SIGNAL_META,
  dirCls,
  fmtNum,
  fmtPct,
  type WatchRow,
} from '../../data/usRadar'

const props = defineProps<{ rows: WatchRow[]; note?: string }>()

const keyword = ref('')
const theme = ref('全部')
const quality = ref('全部')
const sortKey = ref<SortKey>('m1')
const asc = ref(false)

type SortKey =
  | 'ticker'
  | 'close'
  | 'd1'
  | 'w1'
  | 'm1'
  | 'rsi'
  | 'quality_score'
  | 'inst'
  | 'dist_sup'
  | 'dist_res'
  | 'vol_ratio'
  | 'from_hi'
  | 'rs_1m'

interface Col {
  key: SortKey
  label: string
  /** 数字列右对齐且参与排序 */
  num?: boolean
  title?: string
}

const COLS: Col[] = [
  { key: 'ticker', label: '代码' },
  { key: 'close', label: '收盘', num: true },
  { key: 'd1', label: '日', num: true },
  { key: 'w1', label: '周', num: true },
  { key: 'm1', label: '月', num: true },
  { key: 'rsi', label: 'RSI', num: true, title: 'RSI14 · >70过热 <35超卖' },
  {
    key: 'quality_score',
    label: '质地',
    num: true,
    title: '基本面质地分：增长+盈利+现金流+资产负债表+估值+分析师',
  },
  { key: 'inst', label: '机构%', num: true, title: 'Yahoo Finance当前机构持股比例；非13F逐季仓位' },
  { key: 'dist_sup', label: '距支撑', num: true, title: '最近规律支撑位（6个月局部低点聚类）的距离' },
  { key: 'dist_res', label: '距压力', num: true, title: '最近压力位（6个月局部高点聚类）的距离' },
  { key: 'vol_ratio', label: '量比', num: true, title: '5日均量 / 20日均量' },
  { key: 'from_hi', label: '距高点', num: true },
  { key: 'rs_1m', label: 'RS·月', num: true, title: '相对强度：个股月涨幅 − SPY月涨幅' },
]

const themes = computed(() => [
  '全部',
  ...Array.from(new Set(props.rows.map((r) => r.theme))).sort(),
])

const QUALITY_OPTIONS = ['全部', '优质', '中性', '情绪/投机', 'ETF', '数据不足']

const filtered = computed<WatchRow[]>(() => {
  const kw = keyword.value.trim().toUpperCase()
  const rows = props.rows.filter(
    (r) =>
      (theme.value === '全部' || r.theme === theme.value) &&
      (quality.value === '全部' || (r.quality ?? '数据不足') === quality.value) &&
      (!kw || r.ticker.toUpperCase().includes(kw)),
  )
  const dir = asc.value ? 1 : -1
  const key = sortKey.value
  return [...rows].sort((a, b) => {
    const x = a[key] as number | string | null | undefined
    const y = b[key] as number | string | null | undefined
    // 缺失值恒沉底，不参与方向翻转
    if (x === null || x === undefined) return 1
    if (y === null || y === undefined) return -1
    if (typeof x === 'string' || typeof y === 'string') {
      return dir * String(x).localeCompare(String(y))
    }
    return dir * (Number(x) - Number(y))
  })
})

/** 点同一列切换升降序；切到新列时默认降序（看「谁最强」比「谁最弱」更常用） */
function onSort(k: SortKey) {
  if (sortKey.value === k) asc.value = !asc.value
  else {
    sortKey.value = k
    asc.value = k === 'ticker'
  }
}
</script>

<template>
  <div class="wt">
    <div class="toolbar">
      <input
        v-model="keyword"
        class="ctrl"
        placeholder="搜索代码…"
        aria-label="搜索代码"
      />
      <select v-model="theme" class="ctrl" aria-label="按题材筛选">
        <option v-for="t in themes" :key="t" :value="t">{{ t }}</option>
      </select>
      <select v-model="quality" class="ctrl" title="按基本面质地筛选" aria-label="按基本面质地筛选">
        <option v-for="q in QUALITY_OPTIONS" :key="q" :value="q">{{ q }}</option>
      </select>
      <span class="count">{{ filtered.length }} / {{ rows.length }} 只 · 点击表头排序 · 红涨绿跌</span>
    </div>

    <div class="scroll">
      <table class="rd-table grid-tbl">
        <thead>
          <tr>
            <th>主题</th>
            <th>信号</th>
            <th
              v-for="c in COLS"
              :key="c.key"
              :title="c.title"
              class="sortable"
              :class="[c.num ? 'num' : '', { on: sortKey === c.key }]"
              @click="onSort(c.key)"
            >
              {{ c.label }}<template v-if="sortKey === c.key">{{ asc ? ' ↑' : ' ↓' }}</template>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.ticker">
            <td class="theme" :title="r.theme">{{ r.theme }}</td>
            <td>
              <div class="sig-cell">
                <span
                  v-for="s in r.signals"
                  :key="s"
                  class="rd-pill sig"
                  :title="SIGNAL_META[s]?.text ?? s"
                  :style="{ color: SIGNAL_META[s]?.color ?? 'var(--text-dim)' }"
                >
                  {{ (SIGNAL_META[s]?.text ?? s).slice(0, 2) }}
                </span>
              </div>
            </td>
            <td class="tk">{{ r.ticker }}</td>
            <td class="num rd-flat">{{ fmtNum(r.close) }}</td>
            <td class="num" :class="dirCls(r.d1)">{{ fmtPct(r.d1) }}</td>
            <td class="num" :class="dirCls(r.w1)">{{ fmtPct(r.w1) }}</td>
            <td class="num strong" :class="dirCls(r.m1)">{{ fmtPct(r.m1) }}</td>
            <td class="num" :class="r.rsi != null && r.rsi >= 70 ? 'rd-amber' : r.rsi != null && r.rsi <= 35 ? 'rd-cyan' : 'rd-flat'">
              {{ r.rsi == null ? '—' : fmtNum(r.rsi, 1) }}
            </td>
            <td class="num" :title="r.quality_flags">
              <span
                v-if="r.quality"
                class="rd-pill q"
                :style="{ color: QUALITY_COLOR[r.quality] ?? 'var(--text-muted)' }"
              >
                {{ r.quality === '情绪/投机' ? '投机' : r.quality }}
              </span>
              <span v-else class="rd-dim">—</span>
              <span class="q-score rd-dim">{{ r.quality_score ?? '' }}</span>
            </td>
            <td class="num" :class="(r.inst ?? 0) >= 70 ? 'rd-cyan' : 'rd-flat'">
              {{ r.inst == null ? '—' : `${fmtNum(r.inst, 0)}%` }}
            </td>
            <td
              class="num"
              :class="[dirCls(r.dist_sup), r.sup_n === 1 ? 'weak' : '']"
              :title="r.sup ? `支撑位 ${r.sup}（${r.sup_n ?? 0} 次触碰${r.sup_n === 1 ? '，仅一次，强度弱' : ''}）` : ''"
            >
              {{ r.dist_sup == null ? '—' : fmtPct(r.dist_sup, 1) }}
            </td>
            <td class="num rd-flat" :title="r.res ? `压力位 ${r.res}` : ''">
              {{ r.dist_res == null ? '—' : fmtPct(r.dist_res, 1) }}
            </td>
            <td class="num" :class="(r.vol_ratio ?? 0) >= 1.25 ? 'strong rd-cyan' : 'rd-flat'">
              {{ fmtNum(r.vol_ratio) }}
            </td>
            <td class="num" :class="dirCls(r.from_hi)">{{ fmtPct(r.from_hi, 1) }}</td>
            <td class="num" :class="dirCls(r.rs_1m)">{{ fmtPct(r.rs_1m) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="note" class="note">{{ note }}</p>
  </div>
</template>

<style scoped>
.wt {
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
/* 题材下拉项很长，给个上限，否则会按最长项把工具条撑爆 */
.toolbar select:nth-of-type(1) {
  max-width: 190px;
}
.ctrl {
  /* 全局 input/select 规则里有 width:100%，表单控件默认撑满整行。
     工具条里的这三个要并排，必须显式收回 auto。 */
  width: auto;
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 11px;
  outline: none;
}
.ctrl:focus {
  border-color: var(--rd-cyan);
}
.count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  color: var(--text-dim);
}
.scroll {
  /* 68vh：表有 299 行，限高并让表头吸顶，否则滚到第 200 行就不知道列名是什么了 */
  max-height: 68vh;
  overflow: auto;
}
.grid-tbl {
  min-width: 1240px;
  font-size: 11.5px;
}
.grid-tbl .rd-table th {
  font-size: 9.5px;
  letter-spacing: 0.12em;
}
.grid-tbl .rd-table td {
  padding: 5px 10px;
}
/* 可排序表头：手型 + 悬停变青色，当前排序列常驻高亮 */
.sortable {
  cursor: pointer;
  user-select: none;
  transition: color 0.15s ease;
}
.sortable:hover {
  color: var(--rd-cyan);
}
.sortable.on {
  color: var(--rd-cyan);
}
.num {
  text-align: right;
}
.strong {
  font-weight: 600;
}
/* 只被触碰过一次的支撑位：保留读数但减淡，避免它看起来和被验证过的支撑同等可靠 */
.weak {
  opacity: 0.62;
}
.theme {
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: inherit;
  font-size: 10.5px;
  color: var(--text-dim);
  text-align: left;
}
.sig-cell {
  display: flex;
  gap: 2px;
}
.sig {
  background: color-mix(in srgb, var(--text) 5%, transparent);
}
.tk {
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  text-align: left;
}
.q {
  background: color-mix(in srgb, var(--text) 5%, transparent);
}
.q-score {
  margin-left: 4px;
  font-size: 9.5px;
}
.note {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  font-size: 10.5px;
  line-height: 1.7;
  color: var(--text-dim);
}
</style>