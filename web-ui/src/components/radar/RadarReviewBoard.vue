<script setup lang="ts">
// 17 周期复盘 · 回测：主窗口（近1月）+ 参照窗口（滚动3月）的信号命中率。
//
// 这一块是整套系统的「可信度仪表盘」——前面 16 个区块给出的都是信号，
// 这里回答的是「这些信号历史上准不准」。所以它必须把样本数和置信区间一起显示：
// 命中率高但样本只有 3 次的规则，和命中率高且样本 556 次的规则，
// 根本不是一回事。低于 30 次样本的结论会显式标注「读数仅供参考」。
import {
  SIGNAL_META,
  dirCls,
  fmtNum,
  fmtPct,
  type Num,
  type ReviewBlock,
  type SignalStat,
} from '../../data/usRadar'

defineProps<{ r: ReviewBlock }>()

/** 样本数低于这个值，读数只作参考 */
const MIN_SAMPLE = 5

/** 有效性判定：先看样本量，再按 10 日胜率（缺失则退回 5 日）分四档 */
function verdict(s: SignalStat): { label: string; color: string } {
  if (s.note && s.samples < MIN_SAMPLE) return { label: '样本不足', color: 'var(--text-dim)' }
  const hit = s.hit10 ?? s.hit5 ?? 0
  if (hit >= 55) return { label: '有效', color: 'var(--rd-cyan)' }
  if (hit >= 50) return { label: '微弱', color: 'var(--text-muted)' }
  if (hit >= 45) return { label: '无效', color: 'var(--rd-amber)' }
  return { label: '反向', color: 'var(--down)' }
}

/** 均值列的着色：正为红、负为绿（与全站红涨绿跌一致） */
function avgCls(v: Num): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return 'rd-dim'
  return v > 0 ? 'rd-up' : v < 0 ? 'rd-down' : 'rd-flat'
}

/**
 * 胜率配色。看多信号命中率越高越红、看空信号越高越绿——
 * 「高命中」永远是好事，所以颜色必须跟着信号方向走，而不是固定红=高。
 */
function hitCls(hit: number | null | undefined, direction: string): string {
  if (hit === null || hit === undefined || !Number.isFinite(hit)) return 'rd-dim'
  const bull = direction === '看多'
  if (hit >= 55) return bull ? 'rd-up' : 'rd-down'
  if (hit >= 50) return 'rd-flat'
  return 'rd-amber'
}

function statusCls(s: string): string {
  return s === '待批准' ? 'rd-amber' : s === '已批准' ? 'rd-up' : 'rd-dim'
}
</script>

<template>
  <div>
    <p class="method">方法：{{ r.methodology }}</p>

    <div class="stats">
      <section
        v-for="win in [
          { rows: r.signal_stats, title: '主窗口 · 近1个月', sub: '近21个交易日内触发的信号；未来5/10日收益可算的计入统计，不可算的计入待验证（用户选定口径 2026-09-22）' },
          { rows: r.signal_stats_ref, title: '参照窗口 · 滚动3个月', sub: '仅供统计显著性对照，不作主结论' },
        ]"
        :key="win.title"
      >
        <div class="win-head">
          <b>{{ win.title }}</b>
          <span>{{ win.sub }}</span>
        </div>
        <div class="scroll">
          <table class="rd-table st">
            <thead>
              <tr>
                <th>信号规则</th>
                <th class="mid">方向</th>
                <th>样本数</th>
                <th>待验证</th>
                <th>5日均值</th>
                <th>5日胜率</th>
                <th>10日均值</th>
                <th>10日胜率</th>
                <th class="mid">有效性评价</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in win.rows" :key="s.signal">
                <td class="sig-name">
                  {{ SIGNAL_META[s.signal]?.text ?? s.signal }}
                  <div v-if="s.note && s.samples >= 3" class="sig-note">{{ s.note }}</div>
                </td>
                <td class="mid">
                  <span class="rd-pill dir" :class="s.direction === '看多' ? 'rd-up' : 'rd-down'">
                    {{ s.direction ?? '—' }}
                  </span>
                </td>
                <td class="rd-flat">{{ s.samples }}</td>
                <td class="rd-dim">{{ s.pending ?? 0 }}</td>
                <td :class="avgCls(s.avg5)">{{ fmtPct(s.avg5) }}</td>
                <td :class="['strong', hitCls(s.hit5, s.direction)]">
                  {{ s.hit5 != null ? `${fmtNum(s.hit5, 1)}%` : '—' }}
                </td>
                <td :class="avgCls(s.avg10)">{{ fmtPct(s.avg10) }}</td>
                <td :class="['strong', hitCls(s.hit10, s.direction)]">
                  {{ s.hit10 != null ? `${fmtNum(s.hit10, 1)}%` : '—' }}
                </td>
                <td class="mid">
                  <span
                    class="rd-pill vd"
                    :style="{ color: verdict(s).color, borderColor: verdict(s).color }"
                  >
                    {{ verdict(s).label }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- 判断登记：已登记但未到期的条目不参与命中率，这是它必须单列的原因 -->
    <div v-if="r.weekly" class="rd-panel ledger">
      <div class="lg-head">
        <span>判断登记 · 自动对账</span>
        <span>累计 <b>{{ r.weekly.total }}</b> 条</span>
        <span>待验证 <b class="rd-amber">{{ r.weekly.pending }}</b></span>
        <span>已对账 <b>{{ r.weekly.scored }}</b></span>
        <span v-if="r.weekly.hit_rate != null" class="lg-hit">
          命中率
          <b :class="r.weekly.hit_rate >= 55 ? 'rd-up' : r.weekly.hit_rate >= 50 ? 'rd-flat' : 'rd-down'">
            {{ fmtNum(r.weekly.hit_rate, 1) }}%
          </b>
        </span>
        <span class="lg-auto">每周六07:30自动生成系统周报</span>
      </div>
      <div v-if="r.weekly.recent.length > 0" class="lg-list">
        <div v-for="o in r.weekly.recent" :key="`${o.date}-${o.ticker}-${o.rule}`" class="lg-row">
          <span class="lg-mark" :class="o.status === 'hit' ? 'rd-up' : 'rd-down'">
            {{ o.status === 'hit' ? '对' : '错' }}
          </span>
          <span class="lg-ticker">{{ o.ticker }}</span>
          <span class="lg-text" :title="o.text">{{ o.text }}</span>
          <span :class="dirCls(o.ret)">{{ fmtPct(o.ret) }}</span>
          <span class="lg-date">{{ o.date }}</span>
        </div>
      </div>
      <div v-else class="lg-empty">
        首批判断已登记，到期（5/10个交易日）后自动对账并在此展示。
      </div>
    </div>

    <div class="cols">
      <div class="rd-panel">
        <div class="pn-head">本期发现（近1个月主窗口 + 3个月参照 · 观测池全标的逐日重算）</div>
        <div class="findings">
          <div v-for="(f, i) in r.findings" :key="i" class="finding">
            <span class="bullet rd-amber">•</span><span>{{ f }}</span>
          </div>
        </div>
      </div>

      <div class="rd-panel">
        <div class="pn-head">
          <span>规则修改提报（须批准后生效）</span>
          <span class="rd-pill rd-amber">
            {{ r.proposals.filter((p) => p.status === '待批准').length }}项待批准
          </span>
        </div>
        <div class="props">
          <div v-for="p in r.proposals" :key="p.change" class="prop">
            <div class="prop-head">
              <span class="prop-name">{{ p.change }}</span>
              <span class="rd-pill st" :class="statusCls(p.status)">{{ p.status }}</span>
            </div>
            <div class="prop-detail">{{ p.detail }}</div>
            <div class="prop-reason">依据：{{ p.reason }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="rd-callout">
      <span class="key rd-cyan">复盘结论</span>
      <span class="txt">{{ r.conclusion }}</span>
    </div>
    <p class="snap">快照：{{ r.snapshots.note }}（已存档 {{ r.snapshots.count }} 期）</p>
  </div>
</template>

<style scoped>
.method {
  margin-bottom: 10px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  line-height: 1.7;
  color: var(--text-dim);
}
.stats {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
/* 同上：内部是 min-width:960px 的统计表 */
.stats > * {
  min-width: 0;
}
.win-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 8px;
  margin-bottom: 6px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.04em;
  color: var(--text-dim);
}
.win-head b {
  font-size: 9.5px;
  letter-spacing: 0.14em;
  color: var(--text-muted);
}
.scroll {
  overflow-x: auto;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.st {
  min-width: 960px;
  font-size: 10.5px;
}
.st .rd-table th {
  font-size: 9px;
  letter-spacing: 0.14em;
}
.strong {
  font-weight: 700;
}
.mid {
  text-align: center;
}
.sig-name {
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  text-align: left;
  white-space: normal;
}
.sig-note {
  margin-top: 2px;
  font-family: var(--font-mono);
  font-size: 8.5px;
  font-weight: 400;
  color: var(--rd-amber);
}
.dir,
.vd,
.st {
  background: color-mix(in srgb, var(--text) 4%, transparent);
}
.vd,
.st {
  border: 1px solid;
}
.ledger {
  margin-top: 12px;
}
.lg-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 16px;
  margin-bottom: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}
.lg-auto {
  margin-left: auto;
}
.lg-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 4px;
}
@media (min-width: 760px) {
  .lg-list {
    grid-template-columns: 1fr 1fr;
  }
}
.lg-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
  border-radius: 3px;
  background: color-mix(in srgb, var(--bg) 40%, transparent);
  font-size: 10.5px;
}
.lg-mark {
  padding: 1px 4px;
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 700;
}
.lg-ticker {
  font-family: var(--font-mono);
  font-weight: 700;
}
.lg-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-muted);
}
.lg-date {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
}
.lg-empty {
  font-size: 10.5px;
  color: var(--text-dim);
}
.cols {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  margin-top: 8px;
}
@media (min-width: 1200px) {
  .cols {
    grid-template-columns: 1fr 1fr;
  }
}
/* 两栏都是 .rd-panel（内部含 min-width:960px 的统计表），不给 min-width:0
   的话左侧「本期发现」会被右侧的宽表挤成一条竖线 */
.cols > * {
  min-width: 0;
}
.pn-head {
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
.findings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.finding {
  display: flex;
  gap: 8px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-muted);
}
.props {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.prop {
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--bg) 40%, transparent);
}
.prop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.prop-name {
  /* min-width:0：状态药丸不可压缩，标题若不给 min-width:0 会被挤成每字一行的竖排 */
  min-width: 0;
  font-size: 11.5px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.prop-head .rd-pill {
  flex-shrink: 0;
}
.prop-detail {
  margin-top: 4px;
  font-size: 10.5px;
  line-height: 1.6;
  color: var(--text-muted);
}
.prop-reason {
  margin-top: 2px;
  font-size: 10px;
  line-height: 1.6;
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
.snap {
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.7;
  color: var(--text-dim);
}
</style>