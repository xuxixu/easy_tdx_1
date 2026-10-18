<script setup lang="ts">
// 06 涨跌驱动归因：市场层面 4 条 + 逐标的「为什么涨/跌」。
//
// 这一块的存在是为了挡住「看到涨了就去追」：每行都必须给出「发生了什么」
// 和性质判定（实质性 / 情绪为主 / 宏观），只有实质性才值得当作独立逻辑对待。
// 原站表里还有一列「依据与边界」，但它的数据字段在快照中并不存在（恒为空），
// 这里不保留那一列——空列比没有列更让人以为有内容。
import { driverVerdict, dirCls, fmtPct, type DriversBlock } from '../../data/usRadar'

defineProps<{ d: DriversBlock }>()
</script>

<template>
  <div>
    <div class="mkt">
      <div v-for="(m, i) in d.market" :key="i" class="mkt-row">
        <span class="mkt-no">市场{{ i + 1 }}</span>{{ m }}
      </div>
    </div>

    <div class="scroll">
      <table class="rd-table drv">
        <thead>
          <tr>
            <th>标的 / 方向</th>
            <th>周涨跌</th>
            <th>驱动类型</th>
            <th>发生了什么</th>
            <th class="mid">性质判定</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in d.items" :key="it.ticker">
            <td class="tk">{{ it.ticker }}</td>
            <td :class="[dirCls(it.w1), 'strong']">{{ fmtPct(it.w1, 1) }}</td>
            <td class="drv-type">{{ it.driver }}</td>
            <td class="what">{{ it.what }}</td>
            <td class="mid">
              <span
                class="rd-pill verdict"
                :style="{ color: driverVerdict(it.verdict).color }"
              >
                {{ driverVerdict(it.verdict).label }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="rd-callout">
      <span class="key rd-cyan">结论</span>
      <span class="txt">{{ d.conclusion }}</span>
    </div>
  </div>
</template>

<style scoped>
.mkt {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}
.mkt-row {
  padding: 9px 14px;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-muted);
}
.mkt-no {
  margin-right: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.18em;
  color: var(--rd-amber);
}
.scroll {
  overflow-x: auto;
  background: var(--rd-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.drv {
  min-width: 1020px;
  font-size: 11.5px;
}
.drv .rd-table th {
  font-size: 9px;
  letter-spacing: 0.14em;
}
.drv .rd-table td {
  padding: 9px 8px;
  /* 顶部对齐：长的「发生了什么」和短的判定词并排时不会各自垂直居中显得错位 */
  vertical-align: top;
}
.strong {
  font-weight: 600;
}
.tk {
  font-size: 11px;
  font-weight: 700;
}
.drv-type {
  font-family: inherit;
  font-size: 11.5px;
  color: var(--text-muted);
  text-align: left;
  white-space: normal;
}
.what {
  font-family: inherit;
  font-size: 11.5px;
  line-height: 1.6;
  text-align: left;
  white-space: normal;
}
.mid {
  text-align: center;
}
/* 描边药丸：性质判定是这一行的结论，需要与左侧长文本区分开 */
.verdict {
  border: 1px solid currentColor;
  white-space: nowrap;
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