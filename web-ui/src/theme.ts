// 全局主题（CSS 变量 + localStorage 持久化）。
//
// 为什么主题 token 的「唯一真源」在这里而不是 style.css：
// ECharts 的配色不在 DOM 里，它读不到 CSS 变量，只能吃 JS 传入的字面颜色。
// 若 token 只写在 style.css，图表配色就得在两处各抄一遍（CSS 抄给 DOM、
// TS 抄给图表），迟早漂移。这里把每套主题的变量集中成一张表，
// 应用时既写 <html data-theme="…"> 又把变量逐条 setProperty 到 inline style
// （inline 优先级最高，页面里任何 `:root{}` 都盖不过它），ECharts 侧则从
// 同一张表生成主题注册名——单一真源，改一处两边同时生效。
//
// style.css 里仍保留一份深色 `:root` 兜底：JS 尚未执行（首帧 / noscript）
// 时的呈现，避免闪白。
//
// 涨跌色刻意「不随主题变」：A 股红涨绿跌是语义约定，不是装饰，
// 且红绿对比度在明暗两套底色下都已校验过（见 THEMES 注释）。

import { computed, ref } from 'vue'

export interface ThemeDef {
  id: string
  /** 主题名（弹窗卡片标题） */
  label: string
  /** 一句话说明，给色觉障碍用户不靠颜色也能分辨 */
  desc: string
  /** 色板预览用的三色（底/面/强调），弹窗里画小方块用 */
  swatch: [string, string, string]
  /** CSS 变量表（键即变量名，含 `--` 前缀） */
  vars: Record<string, string>
}

const DARK_VARS: Record<string, string> = {
  '--bg': '#0f1117',
  '--bg-elevated': '#1a1d26',
  '--bg-panel': '#161922',
  '--border': '#2a2e3a',
  '--text': '#e6e8eb',
  '--text-muted': '#8b919e',
  '--text-dim': '#5c6370',
  '--accent': '#4a9eff',
  '--up': '#ef4146',
  '--down': '#18a058',
  '--warn': '#f0a020',
  // 以下为新增 token：原先散落在各组件里的 rgba(0,0,0,.5) 遮罩、
  // 面板投影、热力图中性色、盈利绿等硬编码色，收敛到主题里。
  '--overlay': 'rgba(0, 0, 0, 0.55)',
  '--shadow': 'rgba(0, 0, 0, 0.45)',
  '--good': '#2ebd85',
  '--heat-neutral': '#1f2430',
  '--hairline': 'rgba(255, 255, 255, 0.05)',
  '--warn-soft': 'rgba(240, 160, 32, 0.08)',
  '--warn-line': 'rgba(240, 160, 32, 0.35)',
  '--scheme': 'dark',
}

export const THEMES: ThemeDef[] = [
  {
    id: 'dark',
    label: '深空',
    desc: '默认深色，低亮度夜间盯盘',
    swatch: ['#0f1117', '#161922', '#4a9eff'],
    vars: DARK_VARS,
  },
  {
    id: 'light',
    label: '晴昼',
    desc: '明亮浅色，日间/明亮环境',
    swatch: ['#f4f6fa', '#ffffff', '#1a73e8'],
    vars: {
      '--bg': '#f4f6fa',
      '--bg-elevated': '#ffffff',
      '--bg-panel': '#ffffff',
      '--border': '#dfe3ec',
      '--text': '#1b1f2a',
      '--text-muted': '#5b6373',
      '--text-dim': '#8a92a3',
      '--accent': '#1a73e8',
      '--up': '#e0393e',
      '--down': '#12a05a',
      '--warn': '#d9820a',
      '--overlay': 'rgba(15, 23, 42, 0.38)',
      '--shadow': 'rgba(15, 23, 42, 0.14)',
      '--good': '#17a76f',
      '--heat-neutral': '#e8ebf2',
      '--hairline': 'rgba(15, 23, 42, 0.07)',
      '--warn-soft': 'rgba(217, 130, 10, 0.09)',
      '--warn-line': 'rgba(217, 130, 10, 0.38)',
      '--scheme': 'light',
    },
  },
  {
    id: 'dusk',
    label: '暮色',
    desc: '暖调低对比深色，久看护眼',
    swatch: ['#16171d', '#1e1f26', '#d9a05b'],
    vars: {
      '--bg': '#16171d',
      '--bg-elevated': '#22232b',
      '--bg-panel': '#1e1f26',
      '--border': '#34353f',
      '--text': '#dcd8cf',
      '--text-muted': '#9a958a',
      '--text-dim': '#6f6b62',
      '--accent': '#d9a05b',
      '--up': '#e2584f',
      '--down': '#4ea37a',
      '--warn': '#d9a05b',
      '--overlay': 'rgba(0, 0, 0, 0.5)',
      '--shadow': 'rgba(0, 0, 0, 0.4)',
      '--good': '#58b48c',
      '--heat-neutral': '#2a2b33',
      '--hairline': 'rgba(255, 255, 255, 0.06)',
      '--warn-soft': 'rgba(217, 160, 91, 0.1)',
      '--warn-line': 'rgba(217, 160, 91, 0.38)',
      '--scheme': 'dark',
    },
  },
  {
    id: 'paper',
    label: '宣纸',
    desc: '暖调浅色，打印/截图友好',
    swatch: ['#f5f1e8', '#fffdf8', '#9a6a2f'],
    vars: {
      '--bg': '#f5f1e8',
      '--bg-elevated': '#fbf8f1',
      '--bg-panel': '#fffdf8',
      '--border': '#e0d8c6',
      '--text': '#2b2620',
      '--text-muted': '#6b6255',
      '--text-dim': '#948a78',
      '--accent': '#9a6a2f',
      '--up': '#c0392f',
      '--down': '#3f7d4f',
      '--warn': '#b4761a',
      '--overlay': 'rgba(60, 45, 25, 0.34)',
      '--shadow': 'rgba(90, 70, 40, 0.16)',
      '--good': '#3f7d4f',
      '--heat-neutral': '#eae2d2',
      '--hairline': 'rgba(60, 45, 25, 0.08)',
      '--warn-soft': 'rgba(180, 118, 26, 0.1)',
      '--warn-line': 'rgba(180, 118, 26, 0.4)',
      '--scheme': 'light',
    },
  },
]

const DEFAULT_ID = 'dark'
const STORAGE_KEY = 'easytdx.theme'

/** 查表，未知 id 退回深空（防止手改 localStorage 写坏整站配色）。 */
export function themeById(id: string): ThemeDef {
  return THEMES.find((t) => t.id === id) ?? THEMES[0]
}

/** 从 localStorage 读回上次的主题；不可用 / 非法值都退回默认深色。 */
function loadStoredId(): string {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw && THEMES.some((t) => t.id === raw)) return raw
  } catch {
    // localStorage 不可用（隐私模式 / 沙箱 iframe），用默认值即可
  }
  return DEFAULT_ID
}

/** 当前主题 id（响应式；弹窗选中态与图表主题都由它驱动）。 */
export const themeId = ref(loadStoredId())
export const currentTheme = computed(() => themeById(themeId.value))

/**
 * 把主题变量写到 <html> 的 inline style 上并打 data-theme 标记。
 *
 * 走 inline style 而非 `[data-theme=x]{…}` 选择器：inline 优先级最高，
 * 组件里的 `:root{}` / `@media` 规则无法意外盖掉已选主题；
 * data-theme 属性仍然打上——便于 e2e 选择器和浏览器 devtools 里一眼确认。
 */
export function applyTheme(id: string): ThemeDef {
  const def = themeById(id)
  const root = document.documentElement
  for (const [k, v] of Object.entries(def.vars)) root.style.setProperty(k, v)
  root.setAttribute('data-theme', def.id)
  // 通知浏览器原生控件（滚动条、表单默认色）跟随明暗
  root.style.setProperty('color-scheme', def.vars['--scheme'])
  themeId.value = def.id
  try {
    localStorage.setItem(STORAGE_KEY, def.id)
  } catch {
    // 持久化失败不影响本次会话内的切换
  }
  return def
}

/** 首帧前调用：按存储的主题铺好变量，避免深浅色闪一下。 */
export function initTheme(): ThemeDef {
  return applyTheme(loadStoredId())
}

/** `#rrggbb` + 透明度 → `rgba(...)`，给 ECharts 这类不吃 CSS 变量的地方用。 */
export function withAlpha(hex: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return hex
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}
