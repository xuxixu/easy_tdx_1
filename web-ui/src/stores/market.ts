// 全局市场模式（Pinia + localStorage 持久化）。
//
// 这是「A股 / 港股 / 美股」切换的唯一真源：顶栏切换器写它，各页面读它。
// 持久化到 localStorage 是因为切市场不是会话级操作——用户设一次美股，
// 下次打开还想看美股，不该每次重选。
//
// 为什么用全局 store 而不是每个页面自己存：
//   1. 顶栏在 App.vue，页面在 RouterView 里，不共享组件树上下文
//   2. A股专属页面（行业总览/涨停生态/市场情绪…）需要在切换时统一降级，
//      靠各自 watch 同一个 store 比逐个传参可靠

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { fetchOverseasMeta } from '../api'
import type { MarketMetaRow } from '../api'
import type { Market } from '../market'
import { isAShare } from '../market'

const STORAGE_KEY = 'easytdx.market'
const VALID: Market[] = ['SH', 'SZ', 'BJ', 'HK', 'US']

/** 从 localStorage 读回上次的市场，非法值退回 A 股沪市。 */
function loadMarket(): Market {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw && VALID.includes(raw as Market)) return raw as Market
  } catch {
    // localStorage 不可用（隐私模式 / 沙箱 iframe），退回默认值即可
  }
  return 'SH'
}

export type { MarketMetaRow }

export const useMarketStore = defineStore('market', () => {
  const market = ref<Market>(loadMarket())
  /** 后端 /overseas/meta 返回的全市场可用性。拉取前为 null。 */
  const meta = ref<Record<string, MarketMetaRow> | null>(null)
  const metaLoaded = ref(false)

  const isAShareMode = computed(() => isAShare(market.value))
  const currency = computed(() => meta.value?.[market.value]?.currency_label ?? '人民币')
  const marketLabel = computed(() => meta.value?.[market.value]?.label ?? market.value)
  const symbolCount = computed(() => meta.value?.[market.value]?.symbol_count ?? null)

  /** 港美股依赖 7727 扩展栈；未连上时这两个市场不可选。 */
  const exAvailable = computed(() => {
    if (!meta.value) return true // 乐观默认：先让用户能选，报错由取数层给出
    return Boolean(meta.value.HK?.available || meta.value.US?.available)
  })

  function setMarket(next: Market) {
    if (!VALID.includes(next)) return
    market.value = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
      // 记住 A 股内具体市场（顶栏只显示"A股"，切走再回来保持上次的沪/深/北）
      if (next === 'SH' || next === 'SZ' || next === 'BJ') {
        localStorage.setItem('easytdx.lastAshare', next)
      }
    } catch {
      // 持久化失败不影响本次会话内的切换
    }
  }

  async function loadMeta() {
    try {
      const payload = await fetchOverseasMeta()
      meta.value = payload.markets
      metaLoaded.value = true
    } catch {
      // 元信息拿不到就让它保持 null：顶栏仍可切换，取数失败由各页报错
      metaLoaded.value = false
    }
  }

  return {
    market,
    meta,
    metaLoaded,
    isAShareMode,
    currency,
    marketLabel,
    symbolCount,
    exAvailable,
    setMarket,
    loadMeta,
  }
})