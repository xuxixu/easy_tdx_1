// 美股期权结构（PCR + 成交最密集行权价）——静态 mock 数据。
//
// ⚠ 数据现状：项目后端目前没有任何期权数据源（港美股快照只做到行情层，
//   没有期权链接口），所以这里先落一份静态样例把 UI 立住。类型按「后端可直出」
//   的形状写好：接真实接口时把 US_OPTION_CHAINS 换成 fetchOptionChains() 的
//   返回值即可，页面 / 右栏 / 组件都不用改。
//
// 口径（与参考站一致，务必保留说明，否则容易被读成净方向）：
//   PCR(量) = 看跌成交量 / 看涨成交量。<1 说明 call 端成交更拥挤（偏多头预期）
//   热点    = 成交最密集的 3 个行权价，只表示「钱打了多少」，不表示方向
//   成交量不区分开平仓，因此 PCR ≠ 净多空，别拿它直接当持仓成本判断

export interface OptionStrike {
  /** 行权价 */
  strike: number
  /** 该行权价的合约成交量（张） */
  volume: number
}

export interface OptionChain {
  ticker: string
  name: string
  /** 该标的在本页的角色，一句话说明为什么选它 */
  role: string
  /** 到期日 YYYY-MM-DD */
  exp: string
  /** 期权链数据日期 YYYY-MM-DD（可能早于到期日，受数据源更新节奏影响） */
  chainDate: string
  /** 现货价（官方收盘） */
  spot: number
  /** 当月到期看涨合约总成交量（张） */
  callVol: number
  /** 当月到期看跌合约总成交量（张） */
  putVol: number
  /** PCR(量) = putVol / callVol */
  pcr: number
  /** 看涨成交最密集的 3 个行权价 */
  hotCalls: OptionStrike[]
  /** 看跌成交最密集的 3 个行权价 */
  hotPuts: OptionStrike[]
}

export const US_OPTION_CHAINS: OptionChain[] = [
  {
    ticker: 'INTC',
    name: 'Intel Corporation',
    role: '常驻焦点',
    exp: '2026-10-16',
    chainDate: '2026-09-21',
    spot: 123.86,
    callVol: 134059,
    putVol: 66039,
    pcr: 0.49,
    hotCalls: [
      { strike: 110, volume: 26190 },
      { strike: 120, volume: 13126 },
      { strike: 130, volume: 12499 },
    ],
    hotPuts: [
      { strike: 100, volume: 10588 },
      { strike: 110, volume: 6708 },
      { strike: 90, volume: 5020 },
    ],
  },
  {
    ticker: 'META',
    name: 'Meta Platforms, Inc.',
    role: 'AI叙事主角·超买风控样本',
    exp: '2026-10-16',
    chainDate: '2026-09-21',
    spot: 736.6,
    callVol: 179384,
    putVol: 53495,
    pcr: 0.3,
    hotCalls: [
      { strike: 765, volume: 20698 },
      { strike: 800, volume: 18440 },
      { strike: 775, volume: 16203 },
    ],
    hotPuts: [
      { strike: 650, volume: 4124 },
      { strike: 700, volume: 4024 },
      { strike: 600, volume: 2986 },
    ],
  },
  {
    ticker: 'NVDA',
    name: 'NVIDIA Corporation',
    role: '大盘/AI龙头·风向锚',
    exp: '2026-10-16',
    chainDate: '2026-09-21',
    spot: 228.87,
    callVol: 195295,
    putVol: 62702,
    pcr: 0.32,
    hotCalls: [
      { strike: 220, volume: 68507 },
      { strike: 250, volume: 20393 },
      { strike: 230, volume: 16276 },
    ],
    hotPuts: [
      { strike: 215, volume: 7163 },
      { strike: 200, volume: 6918 },
      { strike: 220, volume: 6647 },
    ],
  },
  {
    ticker: 'AMD',
    name: 'Advanced Micro Devices, Inc.',
    role: 'CPU重估·半导体弹性',
    exp: '2026-10-16',
    chainDate: '2026-09-21',
    spot: 623.77,
    callVol: 47985,
    putVol: 31198,
    pcr: 0.65,
    hotCalls: [
      { strike: 700, volume: 5886 },
      { strike: 600, volume: 5460 },
      { strike: 630, volume: 3518 },
    ],
    hotPuts: [
      { strike: 500, volume: 4467 },
      { strike: 600, volume: 3317 },
      { strike: 550, volume: 2057 },
    ],
  },
  {
    ticker: 'QCOM',
    name: 'Qualcomm Incorporated',
    role: 'CPU重估·补涨',
    exp: '2026-10-16',
    chainDate: '2026-09-21',
    spot: 198.27,
    callVol: 16763,
    putVol: 4815,
    pcr: 0.29,
    hotCalls: [
      { strike: 200, volume: 4780 },
      { strike: 210, volume: 3206 },
      { strike: 190, volume: 1684 },
    ],
    hotPuts: [
      { strike: 180, volume: 1213 },
      { strike: 160, volume: 512 },
      { strike: 170, volume: 491 },
    ],
  },
  {
    ticker: 'MSTR',
    name: 'MicroStrategy Incorporated',
    role: '加密情绪·高Beta',
    exp: '2026-10-16',
    chainDate: '2026-09-21',
    spot: 167.33,
    callVol: 42759,
    putVol: 27807,
    pcr: 0.65,
    hotCalls: [
      { strike: 200, volume: 9347 },
      { strike: 150, volume: 6421 },
      { strike: 180, volume: 4220 },
    ],
    hotPuts: [
      { strike: 115, volume: 6394 },
      { strike: 120, volume: 4284 },
      { strike: 100, volume: 2875 },
    ],
  },
  {
    ticker: 'PANW',
    name: 'Palo Alto Networks, Inc.',
    role: '网络安全龙头·拥挤度极高',
    exp: '2026-10-16',
    chainDate: '2026-09-21',
    spot: 374.57,
    callVol: 2737,
    putVol: 2046,
    pcr: 0.75,
    hotCalls: [
      { strike: 410, volume: 882 },
      { strike: 380, volume: 297 },
      { strike: 400, volume: 235 },
    ],
    hotPuts: [
      { strike: 320, volume: 451 },
      { strike: 360, volume: 398 },
      { strike: 350, volume: 143 },
    ],
  },
]

/** 本页结论：把各标的 PCR 串起来的一句话判读 */
export const US_OPTION_CONCLUSION =
  '成交量口径：INTC PCR 0.49、META PCR 0.30，call 端极度拥挤，与两只票同时触发超买风控互相印证——' +
  '短线情绪亢奋到极值，回调概率上升。INTC 热门 call 集中在 110/120/130（现货 123.86，' +
  '110 为深度实值、属既有获利盘），META 热门 call 在 765/800（现货 736.6，纯虚值博弈盘）。'

/** 数据边界：明确口径与已知局限，避免被当成精确的持仓成本 */
export const US_OPTION_NOTE =
  '数据源 OI/IV 字段不可靠已弃用，以下为成交量口径：PCR = 看跌/看涨成交量比，' +
  '热点 = 成交最密集行权价。成交量不区分开平仓，不能等同净方向。链数据日期见每张卡片底部。'

/** 页头/页脚提示：这份数据是 mock，接真实接口前先讲清楚 */
export const US_OPTION_MOCK_NOTICE =
  '当前为静态样例数据（项目后端尚无期权数据源）。卡片结构、PCR 分档与热点口径已按真实接口的返回形状写好，接入真实行情后无需改动页面。'

/** PCR 分档判定 */
export type PcrTone = 'strong-bull' | 'bull' | 'balanced' | 'bear'

export interface PcrVerdict {
  label: string
  tone: PcrTone
}

/**
 * PCR 分档：≤0.5 强多头 / ≤0.75 偏多头 / ≤1 均衡 / >1 偏空头。
 * 边界取「=」归入更保守的一档（0.5 算强多头、1.0 算均衡），
 * 这样同一条数据在任何页面渲染出的分档是一致的。
 */
export function pcrVerdict(pcr: number): PcrVerdict {
  if (!Number.isFinite(pcr)) return { label: '数据缺失', tone: 'balanced' }
  if (pcr <= 0.5) return { label: '强多头', tone: 'strong-bull' }
  if (pcr <= 0.75) return { label: '偏多头', tone: 'bull' }
  if (pcr <= 1) return { label: '均衡', tone: 'balanced' }
  return { label: '偏空头', tone: 'bear' }
}

/** 看涨成交占比（0-100），驱动 call/put 比例条；无数据时给 50 保持条长稳定 */
export function callSharePct(chain: OptionChain): number {
  const total = chain.callVol + chain.putVol
  if (total <= 0) return 50
  return (chain.callVol / total) * 100
}

/** 成交量 → 「k」紧凑写法：134059 → "134.1k" */
export function fmtChainVol(v: number): string {
  if (!Number.isFinite(v)) return '-'
  return `${(v / 1e3).toFixed(1)}k`
}

/** 页面标题下的摘要：标的数 + PCR 极值，用一行说清这页在讲什么 */
export function summarizeChains(chains: OptionChain[]): string {
  if (chains.length === 0) return '暂无期权链数据'
  const pcrs = chains.map((c) => c.pcr).filter(Number.isFinite)
  if (pcrs.length === 0) return `${chains.length} 只标的 · PCR 数据缺失`
  const min = Math.min(...pcrs)
  const max = Math.max(...pcrs)
  return `${chains.length} 只代表标的 · PCR 区间 ${min.toFixed(2)} ~ ${max.toFixed(2)} · 按成交量口径判断 call/put 拥挤度`
}