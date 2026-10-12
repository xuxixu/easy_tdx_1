// 市场令牌与标的代码工具。
//
// 设计前提：**代码格式无法推断市场归属**。
//   - 港股指数 CES100 与美股 ticker AAPL 同形，都是字母
//   - 港股基金 00405 与主板 00001 同形，都是 5 位数字
//   - 5 位数字在 A 股语境下非法，在港股语境下是最常见的代码
// 所以 detectMarket 只在 A 股 6 位数字这一种无歧义场景下才做规则推断；
// 港美股一律由调用方带着明确的市场来（这就是后端 make_symbol/parse_symbol
// 的"每个标的自带市场标识"约定在前端的对应物）。

export type AShareMarket = 'SH' | 'SZ' | 'BJ'
export type ExMarketToken = 'HK' | 'US'
export type Market = AShareMarket | ExMarketToken

/** 是否为 A 股市场（沪/深/北）。接受宽松字符串，未知值返回 false。 */
export function isAShare(market: string): boolean {
  return market === 'SH' || market === 'SZ' || market === 'BJ'
}

/** 是否为扩展市场（港股/美股，走 7727 协议栈）。接受宽松字符串。 */
export function isExMarket(market: string): boolean {
  return market === 'HK' || market === 'US'
}

/** 该市场的默认样本标的，用于顶栏市场说明与空状态引导。 */
export const MARKET_SAMPLE: Record<Market, { code: string; name: string }> = {
  SH: { code: '600519', name: '贵州茅台' },
  SZ: { code: '000001', name: '平安银行' },
  BJ: { code: '430047', name: '诺思兰德' },
  HK: { code: '00700', name: '腾讯控股' },
  US: { code: 'AAPL', name: '苹果' },
}

/**
 * A 股 6 位代码 → 市场智能识别。
 *
 * 规则（按优先级，先匹配到的为准）：
 *   - 北交所(BJ)：43/83/87/92/93/920（小盘/三板）或 4xx/8xx 开头
 *   - 沪市(SH) ：6/9 开头（主板 60/68 科创、B 股 900）或 5 开头（基金 50/51/56/58）
 *   - 其余归深市(SZ)：000/001/002/003/300/301 创业板、200 B股 等
 *
 * 只对 6 位纯数字调用；港美股代码请走显式 market，不经过这里。
 *
 * @param code 6 位股票代码（纯数字）
 * @returns 市场代码 SH/SZ/BJ；无法判断时默认深市（覆盖面最广）
 */
export function detectAShareMarket(code: string): AShareMarket {
  const c = code.trim()
  if (!/^\d{6}$/.test(c)) return 'SZ'

  // 通达信板块指数（沪市）：880 统计 / 881 行业 / 885 概念等
  if (/^88[0-9]/.test(c)) return 'SH'

  // 北交所：43/83/87/92(含920段)/93 + 4xx/8xx（三板/小盘）
  if (/^(43|83|87|92|93|4|8)/.test(c)) return 'BJ'

  // 沪市：6xx（主板/科创板 60/68）、9xx（B股）、5xx（沪市基金 50/51/56/58/50ETF 等）
  if (/^[695]/.test(c)) return 'SH'

  // 其余归深市：000/001/002/003/300/301/200 等
  return 'SZ'
}

/**
 * 兼容旧调用点：等价于 {@link detectAShareMarket}。
 * 新代码请显式写明 A 股语义，避免在港美股语境里误用。
 */
export const detectMarket = detectAShareMarket

/**
 * 把代码转成后端要求的 "市场:代码" 格式。
 *
 * @param code 证券代码（A 股 6 位 / 港股 4-5 位 / 美股字母）
 * @param market 港美股必须显式传；A 股省略时按 {@link detectAShareMarket} 推断
 */
export function toSymbol(code: string, market?: Market): string {
  const m = market ?? detectAShareMarket(code)
  return `${m}:${code.trim().toUpperCase()}`
}

/**
 * 裸代码自动识别市场并拼成 "MARKET:CODE"（A股6位/港股4-5位/美股字母）。
 * 抛错条件：空串或三种形状都不像。
 */
export function toSymbolAuto(raw: string): string {
  const s = (raw ?? '').trim().toUpperCase()
  if (!s) throw new Error('空代码')
  if (s.includes(':')) {
    const [m, c] = parseSymbol(s)
    if (!m || !c) throw new Error(`无法解析：${raw}`)
    return `${m}:${c}`
  }
  if (/^\d{6}$/.test(s)) return `${detectAShareMarket(s)}:${s}`
  if (/^\d{4,5}$/.test(s)) return `HK:${s}`
  if (/^[A-Z][A-Z0-9.\-]{0,11}$/.test(s) && !/^\d+$/.test(s)) return `US:${s}`
  throw new Error(`无法识别：${raw}`)
}

/**
 * 解析 "市场:代码" 形式的标的令牌。
 * @returns [市场, 代码]；无冒号时返回 [null, 原始串]
 */
export function parseSymbol(symbol: string): [Market | null, string] {
  const s = (symbol ?? '').trim().toUpperCase()
  const i = s.indexOf(':')
  if (i < 0) return [null, s]
  const head = s.slice(0, i)
  const known: Market[] = ['SH', 'SZ', 'BJ', 'HK', 'US']
  return [known.includes(head as Market) ? (head as Market) : null, s.slice(i + 1)]
}

/** 市场中文显示名。 */
export function marketLabel(market: Market): string {
  switch (market) {
    case 'SH':
      return '沪市'
    case 'SZ':
      return '深市'
    case 'BJ':
      return '北交所'
    case 'HK':
      return '港股'
    case 'US':
      return '美股'
    default:
      return market
  }
}

/** 市场计价货币中文名。 */
export function currencyLabel(market: Market): string {
  switch (market) {
    case 'HK':
      return '港元'
    case 'US':
      return '美元'
    default:
      return '人民币'
  }
}

/** 该市场是否有数据源可供使用（决定顶栏是否允许选中）。 */
export function marketAvailable(market: Market, exAvailable: boolean): boolean {
  return isAShare(market) ? true : exAvailable
}

// ── 美股四态（盘前 / 盘中 / 盘后 / 夜盘）──────────────────────────────────────
// 与后端 us_session.py 同口径：美东 04:00–09:30 盘前、09:30–16:00 盘中、
// 16:00–20:00 盘后、其余夜盘；夏令(EDT)北京时间 21:30–04:00 盘中，冬令 +1h。

export type USSession = 'pre' | 'open' | 'after' | 'night'

export const US_SESSION_LABELS: Record<USSession, string> = {
  pre: '盘前',
  open: '盘中',
  after: '盘后',
  night: '夜盘',
}

/** 当年 3 月第 2 个周日的日（美夏令开始日，UTC 口径避免本地时区干扰）。 */
function usDstStartDay(year: number): number {
  const d = new Date(Date.UTC(year, 2, 1))
  let count = 0
  while (count < 2) {
    if (d.getUTCDay() === 0) count++
    if (count < 2) d.setUTCDate(d.getUTCDate() + 1)
  }
  return d.getUTCDate()
}

/** 当年 11 月第 1 个周日的日（美夏令结束日）。 */
function usDstEndDay(year: number): number {
  const d = new Date(Date.UTC(year, 10, 1))
  while (d.getUTCDay() !== 0) d.setUTCDate(d.getUTCDate() + 1)
  return d.getUTCDate()
}

/** 是否美夏令时（按美东日期：3 月第 2 个周日 ~ 11 月第 1 个周日）。 */
export function isUsDst(now = new Date()): boolean {
  // 美东日期：UTC - 5h（标准时基线；夏令期间日期边界差 1h 可忽略，日级判断足够）
  const et = new Date(now.getTime() - 5 * 3600_000)
  const y = et.getUTCFullYear()
  const cur = Date.UTC(y, et.getUTCMonth(), et.getUTCDate())
  return cur >= Date.UTC(y, 2, usDstStartDay(y)) && cur < Date.UTC(y, 10, usDstEndDay(y))
}

/** 当前美股四态。 */
export function usSession(now = new Date()): USSession {
  const dst = isUsDst(now)
  // 美东分钟数 = UTC 分钟 - 5h + 夏令 1h
  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes()
  const etMin = (utcMin - 5 * 60 + (dst ? 60 : 0) + 1440) % 1440
  const day = new Date(now.getTime() - (dst ? 4 : 5) * 3600_000).getUTCDay()
  if (day === 0 || day === 6) return 'night'
  if (etMin >= 4 * 60 && etMin < 9 * 60 + 30) return 'pre'
  if (etMin >= 9 * 60 + 30 && etMin < 16 * 60) return 'open'
  if (etMin >= 16 * 60 && etMin < 20 * 60) return 'after'
  return 'night'
}

// ── 美股分钟时段过滤（北京时间口径，夏令；冬令整体 +1h）────────────────────
// TDX 分钟线含盘前盘后，夜盘无数据。K线面板的时段切换按钮用它过滤分钟 bar。

export type USSessionFilter = 'all' | USSession

export const US_SESSION_FILTERS: Array<{ value: USSessionFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'pre', label: '盘前' },
  { value: 'open', label: '盘中' },
  { value: 'after', label: '盘后' },
  { value: 'night', label: '夜盘' },
];

/** 北京时间 HH:MM 是否落在指定美股时段（夏令；冬令调用方传 dst=false）。 */
export function inUsSessionFilter(hhmm: string, session: USSessionFilter, dst = true): boolean {
  if (session === 'all') return true
  const m = /^(\d{1,2}):(\d{2})/.exec(hhmm)
  if (!m) return false
  let mins = Number(m[1]) * 60 + Number(m[2])
  if (!dst) mins = (mins - 60 + 1440) % 1440 // 冬令窗口整体 +1h
  // 夏令窗口（北京时间）：盘前 16:00–21:30 · 盘中 21:30–04:00 · 盘后 04:00–08:00 · 夜盘 08:00–16:00
  // 边界：收盘那根 04:00 属于盘中（美东 16:00 收盘价），故盘中右端闭合、盘后左端开。
  switch (session) {
    case 'pre':
      return mins >= 16 * 60 && mins < 21 * 60 + 30
    case 'open':
      return mins >= 21 * 60 + 30 || mins <= 4 * 60
    case 'after':
      return mins > 4 * 60 && mins < 8 * 60
    case 'night':
      return mins >= 8 * 60 && mins < 16 * 60
    default:
      return true
  }
}

/**
 * 各市场看板默认展示的指数。
 *
 * 沪/深默认上证指数（深市沿用上证作为大盘代表）；北交所北证50；
 * 港股恒生指数（HSI）；美股纳指100ETF（QQQ）——通达信美股列表里没有
 * 真正的纳斯达克综合指数（IXIC），QQQ 是最接近的可用代理，名称如实标注。
 */
export const MARKET_DEFAULT_INDEX: Record<Market, { market: string; code: string; name: string }> = {
  SH: { market: 'SH', code: '000001', name: '上证指数' },
  SZ: { market: 'SH', code: '000001', name: '上证指数' },
  BJ: { market: 'BJ', code: '899050', name: '北证50' },
  HK: { market: 'HK', code: 'HSI', name: '恒生指数' },
  US: { market: 'US', code: 'IXIC', name: '纳斯达克综合指数' },
}

/**
 * 各市场指数条（看板顶部三卡 + 大盘日历切换共用）。
 *
 * 港股：恒生指数（HSI，TDX 有）+ 国企指数（HSCEI）+ 恒生科技（HSTECH）——
 * 后两者 TDX 无，走新浪/腾讯 HTTP 源。
 * 美股：道指（DJI）+ 纳指综合（IXIC）+ 标普500（SPX）——TDX 无，全走 HTTP 源。
 */
export const MARKET_INDEX_STRIP: Record<Market, { market: string; code: string; name: string }[]> = {
  SH: [
    { market: 'SH', code: '000001', name: '上证指数' },
    { market: 'SZ', code: '399001', name: '深证成指' },
    { market: 'SH', code: '000300', name: '沪深300' },
  ],
  SZ: [
    { market: 'SH', code: '000001', name: '上证指数' },
    { market: 'SZ', code: '399001', name: '深证成指' },
    { market: 'SZ', code: '399006', name: '创业板指' },
  ],
  BJ: [
    { market: 'BJ', code: '899050', name: '北证50' },
    { market: 'SH', code: '000001', name: '上证指数' },
    { market: 'SZ', code: '399001', name: '深证成指' },
  ],
  HK: [
    { market: 'HK', code: 'HSI', name: '恒生指数' },
    { market: 'HK', code: 'HSCEI', name: '国企指数' },
    { market: 'HK', code: 'HSTECH', name: '恒生科技指数' },
  ],
  US: [
    { market: 'US', code: 'DJI', name: '道琼斯指数' },
    { market: 'US', code: 'IXIC', name: '纳斯达克综合指数' },
    { market: 'US', code: 'SPX', name: '标普500指数' },
    { market: 'US', code: 'NDX', name: '纳斯达克100指数' },
  ],
}

/**
 * A 股市场切换选项（沪/深/北共用一套聚合接口，单独成一个下拉）。
 * 顶栏的市场切换器用它渲染下拉菜单。
 */
export const A_SHARE_MARKETS: AShareMarket[] = ['SH', 'SZ', 'BJ']

/** 扩展市场（港股/美股）切换选项。 */
export const EX_MARKETS: ExMarketToken[] = ['HK', 'US']