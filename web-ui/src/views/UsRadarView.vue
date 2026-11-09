<script setup lang="ts">
// 美股观测雷达 —— 整页复刻（18 个区块 + 信号专列 + 顶栏 + 页脚口径）。
//
// 为什么这页是「一个超长滚动页」而不是像站内其它页那样拆成多个路由：
// 原站的设计前提就是「一屏接一屏往下读」，18 个区块按
// 环境 → 题材 → 个股 → 择时 → 验证 排列，前后区块互为上下文
// （比如信号专列的预警就来自第 11/12 区块）。拆成独立路由会把这个上下文切断。
//
// 数据是收盘后日线构建的一份快照（public/data/us-radar.json），不是盘中实时
// 行情——页脚与页头都标注了 asOf，避免被当成可交易的实时终端。开发运行态
// 由后端 RadarRebuilder 每日收盘后定时重建，前端轮询版本探测自动刷新；
// EXE/纯静态托管态沿用打包时的快照（见 docs/us-radar-rebuild.md）。
import { onBeforeUnmount, onMounted, ref } from 'vue'

import RadarCongressBoard from '../components/radar/RadarCongressBoard.vue'
import RadarCrowdingBoard from '../components/radar/RadarCrowdingBoard.vue'
import RadarDailyBoard from '../components/radar/RadarDailyBoard.vue'
import RadarDivergenceBoard from '../components/radar/RadarDivergenceBoard.vue'
import RadarDriversBoard from '../components/radar/RadarDriversBoard.vue'
import RadarExitSignals from '../components/radar/RadarExitSignals.vue'
import RadarFocusBoard from '../components/radar/RadarFocusBoard.vue'
import RadarGeoOilBoard from '../components/radar/RadarGeoOilBoard.vue'
import RadarHeader from '../components/radar/RadarHeader.vue'
import RadarIndexBoard from '../components/radar/RadarIndexBoard.vue'
import RadarIndexTrend from '../components/radar/RadarIndexTrend.vue'
import RadarLeftRadar from '../components/radar/RadarLeftRadar.vue'
import RadarNewsBoard from '../components/radar/RadarNewsBoard.vue'
import RadarOptionsBoard from '../components/radar/RadarOptionsBoard.vue'
import RadarQualityBoard from '../components/radar/RadarQualityBoard.vue'
import RadarReviewBoard from '../components/radar/RadarReviewBoard.vue'
import RadarSection from '../components/radar/RadarSection.vue'
import RadarSectorBoard from '../components/radar/RadarSectorBoard.vue'
import RadarSignalPriority from '../components/radar/RadarSignalPriority.vue'
import RadarSubsectorBoard from '../components/radar/RadarSubsectorBoard.vue'
import RadarThemeTrend from '../components/radar/RadarThemeTrend.vue'
import RadarTickerBanner from '../components/radar/RadarTickerBanner.vue'
import RadarUnavailable from '../components/radar/RadarUnavailable.vue'
import RadarVolumeBoard from '../components/radar/RadarVolumeBoard.vue'
import RadarWatchlistTable from '../components/radar/RadarWatchlistTable.vue'
import {
  fetchUsRadar,
  fetchUsRadarVersion,
  triggerUsRadarRebuild,
  type RadarData,
  type RadarRebuildState,
} from '../data/usRadar'

import LoadingState from '../components/LoadingState.vue'

import './usRadar.css'

const data = ref<RadarData | null>(null)
const error = ref('')
const loading = ref(true)

/** 定时重建状态（null = 后端未提供版本接口，沿用纯静态快照）。 */
const rebuild = ref<RadarRebuildState | null>(null)
/** 手动触发重建的瞬时反馈。 */
const rebuildMsg = ref('')
const rebuilding = ref(false)
/** 右上角唯一的「最新时间戳」：每次成功加载/重建完成刷新时更新。 */
const updatedAt = ref('')

// 用 AbortController：这张 JSON 有 465KB，用户在加载途中切走页面时应当取消，
// 否则回调仍会回来写已卸载组件的状态。
let ac: AbortController | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null
let alive = true
/** 已加载快照的 builtAt：版本探测发现它变了才重拉全文。 */
let loadedBuiltAt = ''

const POLL_MS = 60_000
/** 重建进行中/刚触发时加密探测，让「完成后自动刷新」尽快生效。 */
const FAST_MS = 5_000

/** 本地「最后更新」时刻（完整时间戳，右上角主显示）。 */
function stamp(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 应用一份新快照并刷新右上角时间戳。 */
function applySnapshot(snap: RadarData) {
  data.value = snap
  loadedBuiltAt = snap.meta.builtAt ?? ''
  updatedAt.value = stamp()
}

function schedulePoll(ms: number) {
  if (!alive) return
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = setTimeout(() => void poll(), ms)
}

/** 一次版本探测：built_at 变化就重拉全文；据「是否在重建」动态调整下次间隔。 */
async function poll() {
  if (!alive) return
  const v = await fetchUsRadarVersion()
  if (v) {
    rebuild.value = v.rebuild ?? null
    const remote = v.built_at || ''
    if (remote && remote !== loadedBuiltAt) {
      try {
        applySnapshot(await fetchUsRadar())
      } catch {
        // 原子替换的极短窗口全文暂不可读：下轮重试，不弹错。
      }
    }
  }
  // 接口不可用（纯静态托管）时按常速空转探测，成本仅一次轻量 HEAD 级请求
  schedulePoll(rebuild.value?.running || rebuilding.value ? FAST_MS : POLL_MS)
}

onMounted(async () => {
  ac = new AbortController()
  alive = true
  let versionOk = false
  try {
    // 打开即读最新：全文 no-store + 版本探测并行，二者都是磁盘上的最新态
    const [snap, v0] = await Promise.all([
      fetchUsRadar(ac.signal),
      fetchUsRadarVersion(ac.signal),
    ])
    applySnapshot(snap)
    if (v0) {
      versionOk = true
      rebuild.value = v0.rebuild ?? null
      // 校对：若原子替换恰好发生在两次请求之间，以版本接口为准再拉一次
      if (v0.built_at && v0.built_at !== loadedBuiltAt) {
        applySnapshot(await fetchUsRadar(ac.signal))
      }
    }
  } catch (e) {
    // 主动取消不算错误，别弹提示
    if (e instanceof DOMException && e.name === 'AbortError') return
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }

  // 「两者结合」：读到已有最新后，后台再触发一次重建（不阻塞页面）。
  // 未启用（EXE/纯静态）/已在跑/接口不可用时后端返回 409，静默沿用已有数据。
  if (versionOk && rebuild.value?.enabled && !rebuild.value.running) {
    void triggerUsRadarRebuild()
      .then(() => schedulePoll(FAST_MS)) // 加密探测等它完成
      .catch(() => {
        /* 静默：可能已在跑或未启用，不打扰读者 */
      })
  }
  schedulePoll(POLL_MS)
})

/** 手动触发一次后端重建；触发后靠加密轮询自动感知新快照。 */
async function requestRebuild() {
  rebuilding.value = true
  rebuildMsg.value = ''
  try {
    await triggerUsRadarRebuild()
    rebuildMsg.value = '重建已开始，完成后页面会自动更新'
    schedulePoll(FAST_MS)
  } catch (e) {
    rebuildMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    rebuilding.value = false
  }
}

onBeforeUnmount(() => {
  alive = false
  ac?.abort()
  ac = null
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
})

// 分区被写成 null（无可达数据源）时，把 meta.degraded 里登记的原因取出来，
// 交给 RadarUnavailable 显示。留空会被读成「今天没信号」，比空缺更误导。
function why(section: string): string | undefined {
  return data.value?.meta.degraded?.[section]
}
</script>

<template>
  <div class="radar-page">
    <template v-if="data">
      <RadarHeader
        :meta="data.meta"
        :updated-at="updatedAt"
        :rebuild="rebuild"
        :rebuilding="rebuilding"
        :rebuilding-msg="rebuildMsg"
        @rebuild="requestRebuild"
      />
      <RadarTickerBanner :data="data" />

      <main class="radar-main">
        <RadarSignalPriority :data="data" />

        <RadarSection
          id="daily"
          index="01"
          title="每日三板斧 · 指数走势"
          en="INDEX & DAILY AXES"
          note="先判断指数，再判断主线——美股/港股主要指数用对应ETF实时走势，下面保留三板斧技术指标"
        >
          <RadarIndexTrend />
          <RadarDailyBoard :d="data.daily" />
        </RadarSection>

        <RadarSection
          id="env"
          index="02"
          title="大盘环境"
          en="MARKET REGIME"
          note="指数 · 利率 · 宏观资产：决定总仓位与风险预算"
        >
          <RadarIndexBoard :data="data" />
        </RadarSection>

        <RadarSection
          id="geo"
          index="03"
          title="油价 · 地缘风险"
          en="OIL & GEOPOLITICS"
          note="WTI/布伦特/天然气 + 美伊冲突时间线 + 对美股传导路径"
        >
          <RadarUnavailable
            v-if="!data.geo_oil"
            section="geo_oil"
            title="油价 · 地缘风险"
            :reason="why('geo_oil')"
          />
          <RadarGeoOilBoard v-else :d="data.geo_oil" />
        </RadarSection>

        <RadarSection
          id="rotation"
          index="04"
          title="板块轮动"
          en="SECTOR ROTATION"
          note="11大板块ETF + 半导体SMH · 点击行展开观测池成分"
        >
          <RadarSectorBoard :data="data" />
        </RadarSection>

        <RadarSection
          id="subsectors"
          index="05"
          title="细分板块轮动"
          en="SUBSECTOR ROTATION"
          note="科技内部 + 全行业24个细分：每天最强/最弱细分是谁 · 点击下钻"
        >
          <RadarDivergenceBoard :d="data.divergence" />
          <RadarSubsectorBoard :d="data.subsectors" />
        </RadarSection>

        <RadarSection
          id="drivers"
          index="06"
          title="涨跌驱动归因"
          en="MOVE ATTRIBUTION"
          note="为什么涨/跌：实质事件、板块轮动、宏观传导还是纯情绪"
        >
          <RadarDriversBoard :d="data.drivers" />
        </RadarSection>

        <RadarSection
          id="themes"
          index="07"
          title="题材趋势筛选"
          en="THEME TREND FILTER"
          note="趋势占比 + 周涨幅：区分真趋势与单日情绪 · 点击下钻"
        >
          <RadarThemeTrend :d="data.theme_trend" :watchlist="data.watchlist" />
        </RadarSection>

        <RadarSection
          id="crowding"
          index="08"
          title="拥挤度 · 机构集中度"
          en="INSTITUTIONAL CROWDING"
          note="真实机构持股字段 + 动量/趋势/量能代理，识别买盘枯竭风险 · 点击下钻"
        >
          <RadarCrowdingBoard :c="data.crowding" :watchlist="data.watchlist" />
        </RadarSection>

        <RadarSection
          id="quality"
          index="09"
          title="基本面质地分层"
          en="QUALITY vs SENTIMENT"
          note="先分清公司质地，再决定按投资逻辑还是交易逻辑处理"
        >
          <RadarUnavailable
            v-if="!data.quality"
            section="quality"
            title="基本面质地分层"
            :reason="why('quality')"
          />
          <RadarQualityBoard v-else :q="data.quality" />
        </RadarSection>

        <RadarSection
          id="congress"
          index="10"
          title="国会山持仓"
          en="CAPITOL TRADES"
          note="特朗普 · 佩洛西 · 活跃议员：披露持仓与调仓动向（滞后30-45天）"
        >
          <RadarUnavailable
            v-if="!data.congress"
            section="congress"
            title="国会山持仓"
            :reason="why('congress')"
          />
          <RadarCongressBoard v-else :c="data.congress" :watchlist="data.watchlist" />
        </RadarSection>

        <RadarSection
          id="left"
          index="11"
          title="左侧雷达 · 回踩支撑"
          en="LEFT-SIDE WATCH"
          note="趋势 + 规律支撑 + 失效位：个股择时入口"
        >
          <RadarLeftRadar :d="data.left" />
        </RadarSection>

        <RadarSection
          id="exits"
          index="12"
          title="兑现 / 风控信号"
          en="EXIT & RISK SIGNALS"
          note="跌破MA5 · 高位放量阴线 · 放量破位 · 放量突破"
        >
          <RadarExitSignals :d="data.exits" />
        </RadarSection>

        <RadarSection
          id="focus"
          index="13"
          title="焦点个股"
          en="FOCUS STOCKS"
          note="INTC常驻 + 当日监测自动选取3只：形态/期权/基本面全自动计算，策展点评逐期补充"
        >
          <RadarFocusBoard :f="data.focus" />
        </RadarSection>

        <RadarSection
          id="options"
          index="14"
          title="期权结构 · 代表股"
          en="OPTIONS POSITIONING"
          note="每日6只代表标的：用资金博弈验证价格判断"
        >
          <RadarUnavailable
            v-if="!data.options"
            section="options"
            title="期权结构 · 代表股"
            :reason="why('options')"
          />
          <RadarOptionsBoard v-else :o="data.options" />
        </RadarSection>

        <RadarSection
          id="volume"
          index="15"
          title="量能异动"
          en="VOLUME ANOMALIES"
          note="量比≥1.25 且 当日|涨跌|≥3%"
        >
          <RadarVolumeBoard :data="data" />
        </RadarSection>

        <RadarSection
          id="news"
          index="16"
          title="新闻实质判断"
          en="NEWS: SIGNAL vs NOISE"
          note="实质性 / 偏情绪 / 混合 / 事件预告"
        >
          <RadarUnavailable
            v-if="!data.news"
            section="news"
            title="新闻实质判断"
            :reason="why('news')"
          />
          <RadarNewsBoard v-else :news="data.news" :watchlist="data.watchlist" />
        </RadarSection>

        <RadarSection
          id="review"
          index="17"
          title="周期复盘 · 回测"
          en="REVIEW & BACKTEST"
          note="近1个月主窗口回测（3个月参照）+ 判断登记自动对账：对不对、为什么、怎么改"
        >
          <RadarReviewBoard :r="data.review" />
        </RadarSection>

        <RadarSection
          id="watchlist"
          index="18"
          title="自选总表"
          en="WATCHLIST · FULL TABLE"
          :note="data.meta.universe"
        >
          <RadarWatchlistTable :rows="data.watchlist" />
        </RadarSection>
      </main>

      <footer class="radar-foot">
        <p>
          <span class="rd-amber">数据口径：</span>{{ data.meta.asOf }} · 数据来源
          {{ data.meta.source ?? 'Yahoo Finance' }}，{{ data.meta.delay }}。支撑/压力位为6个月局部高低点聚类算法结果，
          RSI为14日，信号为规则触发而非预测；拥挤度为动量·趋势·量能代理指标，非13F真实仓位。
          本页为构建时点的静态快照，非实时行情。
        </p>
        <p>
          <span class="rd-amber">使用边界：</span>本系统为观测工具，不构成投资建议；所有模块按
          「环境 → 题材 → 个股 → 择时 → 验证」组织，触发≠必须操作。盘前盘后流动性低、点差大，
          价格仅供参考。实际下单前请以券商/同花顺实时行情为准。
        </p>
        <p class="radar-build">
          US MARKET OBSERVATION RADAR · BUILT {{ data.meta.builtAt }} · RED = UP / GREEN = DOWN（同花顺习惯）
        </p>
      </footer>
    </template>

    <LoadingState v-else-if="loading" label="雷达快照加载中…" hint="读取最新收盘后构建的观测数据" />
    <div v-else class="radar-state err">
      {{ error || '雷达快照加载失败' }}
      <p class="radar-state-hint">
        快照文件位于 <code>web-ui/public/data/us-radar.json</code>。若文件缺失，重新运行
        <code>npm run dev</code> 或 <code>npm run build</code> 让 Vite 把它复制进产物。
      </p>
    </div>
  </div>
</template>

<style scoped>
/* 页头 sticky（48px 顶栏）已占一行，主内容区从它下面开始滚 */
.radar-page {
  /* 页面根必须是滚动容器，否则被 App 布局 .app-main 的 overflow:hidden 裁掉，
     整页 1 万多像素的内容全部溢出到视口外、滚都滚不动。
     与其他整页滚动 view（DashboardView 的 .dash）同构：height:100% 填满
     .app-main > :last-child，overflow-y:auto 让自身内容在内部滚动。
     sticky 顶栏 .rd-head 在这个滚动容器内吸顶，行为不变。 */
  height: 100%;
  overflow-y: auto;
}
.radar-main {
  display: flex;
  flex-direction: column;
  gap: 32px;
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px 24px 40px;
}
.radar-foot {
  padding: 16px 24px 20px;
  background: var(--rd-panel);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.radar-foot p {
  max-width: 1440px;
  margin: 0 auto;
  width: 100%;
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-dim);
}
.radar-build {
  font-family: var(--font-mono);
  letter-spacing: 0.16em;
}
.radar-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  font-size: 13px;
  color: var(--text-muted);
}
.radar-state.err {
  color: var(--warn);
}
.radar-state-hint {
  max-width: 520px;
  text-align: center;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-dim);
}
.radar-state-hint code {
  font-family: var(--font-mono);
  padding: 1px 4px;
  border-radius: 2px;
  background: var(--bg-elevated);
}
</style>