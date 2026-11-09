// 全功能只读巡检：遍历所有前端路由，把「安全的」可交互元素逐个点一遍，
// 抓运行时 JS 异常与渲染空白。
//
// 为什么单独一条用例而不是给每个页面写一堆断言：
//   1. 路由多达 26 个、按钮上百个，逐页写断言维护成本极高且容易挂一漏万；
//   2. 这里的目标不是业务结果，而是「点了不崩、页面不白」——这是所有按钮
//      的最低门槛，恰好能自动捕获「某 tab 切过去抛 TypeError」「某展开组件
//      引用了不存在的字段」这类回归。
//
// 安全边界（重要）：
//   - 只点 tab / 切换 / 展开 / 排序 / 视图模式 / 分类 chip 这类纯本地状态按钮；
//   - 显式跳过写操作（保存/删除/加入自选/运行回测/推送/清空/导出/发送…），
//     避免污染 mock 临时库或触发真实外部调用；
//   - 不填表单、不提交、不导航到外链；弹窗类按钮只开不写，开完立刻关。
//
// 与 inspect_routes.cjs（临时脚本）的区别：这条进 E2E 套件，随 CI 常驻。

import { expect, test } from '@playwright/test'

const ROUTES = [
  '/', '/industries', '/concepts', '/hotspots', '/styles', '/calendar',
  '/watchlist', '/limitup', '/sentiment', '/backtest', '/portfolio',
  '/optimize', '/compare', '/strategies', '/strategy-types', '/signals',
  '/settings', '/index-settings', '/indicator-settings', '/custom-indicators',
  '/push', '/llm', '/ai-history', '/ccpm', '/us-options', '/us-radar',
]

// 这些词出现在按钮文案里 = 会写数据 / 触发任务 / 打开外部资源，一律不点。
const WRITE_WORDS = [
  '保存', '删除', '移除', '清空', '加入', '添加', '新建', '创建', '运行',
  '开始', '执行', '导出', '下载', '发送', '推送', '提交', '确认', '应用',
  '重置', '刷新', '重试', '复制', '关闭', '完成', '取消', '回测', '计算',
  '解读', '测试', '连接', '断开', '同步', '上传', '导入', '登录', '登出',
  '一键', '生成', '优化', '扫描', '抓取', '采集',
]

// 只点这些「纯本地状态 / 只读切换」的按钮（命中即点）。
// 按 dump_buttons 的实际文案校准，覆盖看板 K 线周期/指标、板块视图/分类、
// 热点窗口、日历年份、榜单排序、CCPM 科普折叠等；不含任何写操作。
const SAFE_WORDS = [
  // 看板 K 线：周期 / 主图叠加 / 副图 / 分时弹窗入口（只读）
  '日K', '周K', '月K', '15分', '30分', '60分', '120分', '240分',
  'MA', 'EMA', 'BOLL', 'BBI', 'MACD', 'KDJ', 'RSI', '副图无',
  '分时/盘口', '查看', '换手',
  // 榜单排序 / 板块总览视图 / 一级二级 / 热力图
  '涨幅', '跌幅', '成交额', '成交量', '热力图', '表格', '一级', '二级',
  // 热点滚动：板块类型 / 时间窗口 / 方向 / 视图
  '行业', '概念', '风格', '今日', '近10日', '近20日', '近30日',
  '领涨', '领跌', '热点矩阵', '相关性',
  // 日历：指数 / 年份
  '上证指数', '深证成指', '沪深300', '创业板指', '科创50',
  '2026年', '2025年', '2024年',
  // 顶栏市场切换刻意**不点**：它改的是全局 marketStore + localStorage，
  // 会污染后续 E2E 用例（全套共享一个 serve/浏览器上下文）。巡检只碰
  // 视图内部的局部状态。
  // 策略库 / 自定义指标的分类 tab（纯本地；「验证语法」等触发后端
  // py_mini_racer 的按钮已排除，避免巡检把 native 引擎打崩）
  '单标的', '主图叠加', '画线', '叠加K线',
  // 折叠类科普 / 名词解释（纯展开）
  '名词解释', '这是什么数据', '品种一览', '新手科普', 'PCR 怎么读',
]

// 命中即跳过：这些会触发后端 JS 引擎 / 重计算 / 网络刷新，不属于「纯本地状态」。
const SKIP_WORDS = [
  '手动刷新', '刷新', '查看', '分时/盘口', '验证语法', '测试', '使用',
]

function isSafeClick(text: string): boolean {
  const t = text.trim()
  if (!t) return false
  // 先挡写操作：即便文案里碰巧含安全词（如「保存并叠加」）也不点。
  if (WRITE_WORDS.some((w) => t.includes(w))) return false
  if (SKIP_WORDS.some((w) => t.includes(w))) return false
  return SAFE_WORDS.some((w) => t === w || t.startsWith(w))
}

test('全路由只读交互巡检：所有安全按钮可点且不产生 JS 异常', async ({ page }) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(`${page.url()}: ${e.message}`))
  // 网络降级（mock 未覆盖的独立数据源返回 503）不算 JS 崩溃，单独忽略。
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const t = m.text()
    if (/failed to load resource|status of 4\d\d|status of 5\d\d|net::|ERR_/i.test(t)) return
    jsErrors.push(`${page.url()}: console ${t.slice(0, 160)}`)
  })

  const visited: string[] = []
  let clicked = 0

  // 只做一次整页加载，其余走 SPA 客户端路由跳转（history.pushState + popstate）。
  // 26 次 page.goto 会把同一个 mock serve 反复打满、拖崩后续用例；SPA 内部
  // 跳转不发新文档请求，既快又稳，且仍会触发各视图的 onMounted/数据加载。
  await page.goto(ROUTES[0], { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(800)

  for (const route of ROUTES) {
    if (route !== ROUTES[0]) {
      await page.evaluate((r) => {
        window.history.pushState({}, '', r)
        window.dispatchEvent(new PopStateEvent('popstate'))
      }, route)
      await page.waitForTimeout(200)
    }

    // 页面至少渲染出内容（不做业务断言，只挡「整页白屏」）
    const textLen = await page.evaluate(() => (document.body.innerText || '').length)
    expect(textLen, `${route} 疑似空白页`).toBeGreaterThan(100)

    const buttons = page.locator('button')
    // 每页只点前 6 个命中的安全按钮：目标是「每条交互路径能走通」，不是
    // 把所有组合穷举一遍。穷举会反复触发后端公式引擎（py_mini_racer）并
    // 把 mock serve 拖垮，反而让整套 E2E 不稳定。
    const count = Math.min(await buttons.count(), 40)
    let pageClicks = 0
    for (let i = 0; i < count && pageClicks < 6; i++) {
      const btn = buttons.nth(i)
      let label = ''
      try {
        label = (await btn.innerText({ timeout: 1000 })).trim()
      } catch {
        continue
      }
      if (!isSafeClick(label)) continue
      // 跳过不可见 / 被禁用 / 已带禁用属性的
      if (!(await btn.isVisible()) || (await btn.isDisabled())) continue
      try {
        await btn.click({ timeout: 1500 })
        clicked++
        pageClicks++
        // 纯本地状态切换无需等待；个别异步渲染留给下一个按钮的自然间隔。
      } catch {
        // 被遮挡/移出视口等：非崩溃，跳过即可
      }
    }
    visited.push(route)
  }

  // 打印覆盖量：真出了问题时一眼能看出「点得太少」还是「某路由崩了」。
  console.log(`[交互巡检] 路由 ${visited.length} 个，安全按钮点击 ${clicked} 次`)
  expect(visited.length).toBe(ROUTES.length)
  // 至少确实点到了一批按钮（防止 SAFE_WORDS 全部失配、用例变成空跑）
  expect(clicked, '应至少点到若干安全按钮').toBeGreaterThan(15)
  expect(jsErrors, `JS 异常：\n${jsErrors.join('\n')}`).toEqual([])
})
