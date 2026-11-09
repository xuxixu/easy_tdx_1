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
// K 线面板的时段切换按钮用它过滤分钟 bar。
//
// ⚠ 数据源限制（2026-10 实测，勿再按旧注释理解）：TDX 扩展行情栈的美股分钟线
// **只覆盖盘中**——美东 09:30–16:00，即北京 21:30–04:00，5 分钟线 78 根/日，
// 不含盘前/盘后/夜盘。东方财富 push2his 同样只有盘中，免费源普遍如此。
// 因此切「盘前 / 盘后 / 夜盘」时过滤结果为空，属数据源不提供而非代码缺陷；
// 界面按 `barsTooFew` 提示"K线不足"。

export type USSessionFilter = 'all' | USSession

/**
 * 可选的时段档位。
 *
 * **只保留「全部」与「盘中」**：盘前 / 盘后 / 夜盘在 TDX 与东财免费接口下
 * 均无数据（实测美股分钟线仅美东 09:30–16:00），摆出来只会让人点了看到空白。
 * `USSessionFilter` 类型仍保留四态，`inUsSessionFilter` 也仍能按四态判窗口，
 * 将来接入盘前盘后数据源时把档位加回来即可。
 */
export const US_SESSION_FILTERS: Array<{ value: USSessionFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'open', label: '盘中' },
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
 * 分时点/成交时间归一化为 ``HH:MM``。
 *
 * :func:`inUsSessionFilter` 用 ``^(\\d{1,2}):(\\d{2})`` 锚定开头解析，所以
 * 传进去的必须是纯时间。而不同数据源给的写法并不统一：扩展栈分时是
 * ``"21:30:00"``、A 股路径可能带日期 ``"2024-01-01 21:30:00"``。直接
 * ``slice(0, 5)`` 遇到带日期的串会得到 ``"2024-"``，时段过滤会**全部判 false**，
 * 表现为「切到任何时段都是空图」——很难排查，故统一在这里抽时间部分。
 *
 * @returns 形如 ``"21:30"``；解析不出时返回空串（调用方应跳过该点）。
 */
export function toHhmm(dt: string): string {
  const m = /(\d{1,2}):(\d{2})/.exec(dt)
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : ''
}

/**
 * 分时图 x 轴刻度的取样参数。
 */
export interface HourTickOptions {
  /** 绘图区宽度（px，扣掉左右轴标签后的可用宽度）。 */
  plotWidth: number
  /** 单档 "hh:mm" 的估算文字宽度（px）。 */
  labelWidth: number
  /** 刻度数硬上限（含首尾），默认 7。 */
  maxTicks?: number
}

/**
 * 分时图 x 轴刻度取样：以「整点」为锚，返回**点的索引**。
 *
 * 为什么按整点而不是固定索引：各市场分时点数与时段都不同（A 股 240 点
 * 09:30-14:59、港股 330 点 09:30-15:59 且午休断开、美股 390 点北京时间
 * 22:30-04:59 跨零点）。旧实现写死 ``[0, 60, 120, 121, 180, 239]`` 只对
 * A 股成立，港股/美股会落到毫无意义的分钟上。整点取样天然适配任何时段。
 *
 * 两条硬约束：
 * 1. 首尾两个点必留——开盘价与最新价的位置必须有时间参照；
 * 2. 相邻刻度至少隔一个 ``labelWidth``——否则窄图里 "hh:mm" 会叠成一团。
 *    整点候选并不等距：美股首点 22:30 与次档 23:00 只差半小时，按等距
 *    抽稀后仍可能撞上，故先按 ``maxTicks`` 抽稀、再按像素间距剔除。
 *
 * @param times 已归一化的 ``HH:MM`` 序列（见 :func:`toHhmm`）。
 */
export function pickHourTicks(times: string[], opts: HourTickOptions): number[] {
  const n = times.length
  if (n === 0) return []
  const last = n - 1
  const cands = [0]
  for (let i = 1; i <= last; i++) {
    if (times[i].endsWith(':00')) cands.push(i)
  }
  if (cands[cands.length - 1] !== last) cands.push(last)

  const cap = Math.max(2, Math.floor(opts.maxTicks ?? 7))
  let picked = cands
  if (cands.length > cap) {
    if (cap === 2) {
      picked = [cands[0], cands[cands.length - 1]]
    } else {
      // 在候选里等距取 cap 个：按比例舍入，两端必被取到。
      const step = (cands.length - 1) / (cap - 1)
      picked = []
      for (let k = 0; k < cap; k++) {
        const idx = cands[Math.round(k * step)]
        if (picked[picked.length - 1] !== idx) picked.push(idx)
      }
    }
  }

  // 像素间距过滤：末点优先（挤到前一个时顶掉前一个），首点始终保留。
  const pxPerIdx = last > 0 ? opts.plotWidth / last : opts.plotWidth
  const minGapPx = opts.labelWidth + 8
  const out = [picked[0]]
  for (let k = 1; k < picked.length; k++) {
    const idx = picked[k]
    const isLast = idx === picked[picked.length - 1] && k === picked.length - 1
    if ((idx - out[out.length - 1]) * pxPerIdx < minGapPx) {
      if (isLast && out.length > 1) out[out.length - 1] = idx
      continue
    }
    out.push(idx)
  }
  return out
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
// ── 指数的分钟级数据代理 ─────────────────────────────────────────────────────
// 美股**指数**（道指/纳指/标普）在 MAC/qq 扩展栈只回 1 根 qq 快照，没有完整分时，
// 因此下表把美股指数映射到高度相关的 ETF（DIA/QQQ/SPY），前端用 ETF 数据代理
// 渲染——走势形态一致，但点位不是指数本身，UI 必须明示。
//
// 港股**指数**（恒生 HSI / 国企 HSCEI / 恒科 HSTECH）实测 qq 源返回**完整分时**
// （指数点位、datetime 带日期），与 IntradayChart 直接兼容，**不需要代理**。
// 切勿把港股指数映射到港股 ETF（如 02800）：那是 tdx 源，datetime 是 HH:MM:SS
// 无日期、且点位是 ETF 价格，代理会让分时图 x 轴错乱、y 轴量级失衡。
export const INDEX_ETF_PROXY: Record<
  string,
  { market: Market; code: string; label: string }
> = {
  DJI: { market: 'US', code: 'DIA', label: 'DIA' },
  IXIC: { market: 'US', code: 'QQQ', label: 'QQQ' },
  NDX: { market: 'US', code: 'QQQ', label: 'QQQ' },
  SPX: { market: 'US', code: 'SPY', label: 'SPY' },
}
