<script setup lang="ts">
// 技术指标管理页（系统分组）：
// 上：预置指标管理（MA/EMA/BOLL/MACD/KDJ/RSI = 锁定的通达信公式，
//     只调周期/倍数，公式文本由参数生成、只读展示）；修改即时生效
//     并落 localStorage 全局共用。
// 中：自定义指标管理（新增/编辑/删除，保存后出现在各 K 线图标题栏）。
// 下：公式指标（通达信公式 → 后端引擎计算 → 叠加绘制）。
// 预置与自定义同走后端公式引擎计算；主图叠加/副图的切换在各 K 线图标题栏。
import { onUnmounted, ref } from 'vue'

import PresetList from '../components/PresetList.vue'
import {
  DEFAULT_INDICATOR_PARAMS,
  loadIndicatorParams,
  subscribeIndicatorParams,
  type IndicatorParams,
} from '../indicatorParams'

const params = ref<IndicatorParams>(loadIndicatorParams())
const savedAt = ref('')

const unsubscribe = subscribeIndicatorParams((p) => {
  params.value = { ...p }
  savedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
})
onUnmounted(unsubscribe)
</script>

<template>
  <div class="indicator-settings">
    <section class="card manage-card">
      <h2>技术指标 · 管理</h2>
      <p class="hint">
        预置指标由后端公式引擎统一计算（与自定义公式同路径），修改即时生效 ·
        全局共用。所有 K 线（个股/板块弹窗、市场看板、港美股面板）共用同一套配置，
        保存在浏览器本地。主图叠加与副图的切换在各 K 线图标题栏。
        「恢复默认」只重置参数与选择，自定义指标保留。
      </p>
      <PresetList v-model="params" />
      <div v-if="savedAt" class="message">✓ 已自动保存 {{ savedAt }}</div>
    </section>

    <section class="card info-card">
      <h3>说明</h3>
      <ul class="desc">
        <li>预置公式锁定，只能调周期/倍数；自定义指标请到「系统 → 自定义指标」新增/编辑/删除，删除后其在各图的选择态自动清理。</li>
        <li>主图叠加（MA/EMA/BOLL/自定义主图，可多选）与副图（MACD/KDJ/RSI/自定义副图/副图无）的切换在各 K 线图标题栏，自定义项为虚线边框。</li>
        <li>副图里列名含 HIST/柱/量的输出画 bar，其余画线。</li>
        <li>KDJ 的 K/D 平滑固定 3/1（国内通用口径）。</li>
      </ul>
      <h3>默认口径</h3>
      <table class="default-table">
        <tbody>
          <tr>
            <td>MA 周期</td>
            <td class="mono">{{ DEFAULT_INDICATOR_PARAMS.maPeriods.join(', ') }}</td>
          </tr>
          <tr>
            <td>EMA 快 / 慢</td>
            <td class="mono">{{ DEFAULT_INDICATOR_PARAMS.emaFast }} / {{ DEFAULT_INDICATOR_PARAMS.emaSlow }}</td>
          </tr>
          <tr>
            <td>BOLL 周期 / 倍数</td>
            <td class="mono">{{ DEFAULT_INDICATOR_PARAMS.bollN }} / {{ DEFAULT_INDICATOR_PARAMS.bollP }}</td>
          </tr>
          <tr>
            <td>MACD 快 / 慢 / 信号</td>
            <td class="mono">
              {{ DEFAULT_INDICATOR_PARAMS.macdFast }} / {{ DEFAULT_INDICATOR_PARAMS.macdSlow }} /
              {{ DEFAULT_INDICATOR_PARAMS.macdSignal }}
            </td>
          </tr>
          <tr>
            <td>KDJ 周期</td>
            <td class="mono">{{ DEFAULT_INDICATOR_PARAMS.kdjN }}</td>
          </tr>
          <tr>
            <td>RSI 周期</td>
            <td class="mono">{{ DEFAULT_INDICATOR_PARAMS.rsiPeriods.join(', ') }}</td>
          </tr>
        </tbody>
      </table>
    </section>

  </div>
</template>

<style scoped>
.indicator-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  overflow-y: auto;
}
.card {
  padding: 16px;
}
.manage-card h2 {
  margin: 0 0 8px;
  font-size: 15px;
}
.hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0 0 14px;
  line-height: 1.6;
}
.message {
  margin-top: 12px;
  font-size: 12px;
  color: var(--up);
}
.info-card h3 {
  margin: 0 0 8px;
  font-size: 13px;
}
.desc + h3 {
  margin-top: 16px;
}
.desc {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.8;
}
.default-table {
  border-collapse: collapse;
  font-size: 12px;
}
.default-table td {
  padding: 4px 12px 4px 0;
  color: var(--text-muted);
}
.default-table td.mono {
  color: var(--text);
}
</style>
