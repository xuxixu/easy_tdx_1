// 个股分时图 E2E：打开弹窗 → 分时渲染 → 成交量副图有柱 → hover 不报错。
//
// 这条用例守着「分时图数据消失」这类回归：坐标轴索引一旦错位（如成交量
// series 的 yAxisIndex 指向了价格/涨跌幅轴），柱子会被画到量程外——图看着
// 还在、数据却没了，纯截图断言抓不到，必须断言 canvas 上确实画了东西。
//
// 依赖 mock 的 get_history_minute_time_data（多日分时走 /minute/history）。

import { expect, test } from '@playwright/test'

/** 统计 canvas 上非透明像素占比：用来判断「图上真的有东西」。 */
async function inkRatio(page: import('@playwright/test').Page, sel: string): Promise<number> {
  return page.evaluate((s) => {
    const c = document.querySelector(s) as HTMLCanvasElement | null
    if (!c) return -1
    const ctx = c.getContext('2d')
    if (!ctx) return -1
    const { data } = ctx.getImageData(0, 0, c.width, c.height)
    let ink = 0
    for (let i = 3; i < data.length; i += 4) if (data[i] > 0) ink++
    return ink / (data.length / 4)
  }, sel)
}

test('个股分时图渲染出价格线与成交量副图', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto('/')
  await page.waitForTimeout(2000)

  await page.locator('button[title="打开分时/盘口弹窗"]').click()
  await expect(page.locator('.dlg')).toBeVisible()
  // 分时默认页签；数据到达前是「加载中…」
  await expect(page.locator('.dlg-body canvas')).toBeVisible({ timeout: 30_000 })
  // 不能停在加载态或错误态
  await expect(page.locator('.chart-msg.error')).toHaveCount(0)
  await page.waitForTimeout(1500)

  // 图上确实画了东西（非空白 canvas）
  const ink = await inkRatio(page, '.dlg-body canvas')
  expect(ink).toBeGreaterThan(0.01)

  // 成交量副图（画布下半部分）必须有柱子：全透明说明数据没画出来
  const volInk = await page.evaluate(() => {
    const c = document.querySelector('.dlg-body canvas') as HTMLCanvasElement
    const ctx = c.getContext('2d')!
    // 副图 grid 在 74%~94% 高度，取该带
    const y0 = Math.floor(c.height * 0.76)
    const band = ctx.getImageData(0, y0, c.width, Math.floor(c.height * 0.16)).data
    let ink = 0
    for (let i = 3; i < band.length; i += 4) if (band[i] > 0) ink++
    return ink / (band.length / 4)
  })
  expect(volInk).toBeGreaterThan(0.005)

  // hover：触发 tooltip 与 axisPointer 联动（坐标系错配会在这里抛错）
  const box = await page.locator('.dlg-body canvas').first().boundingBox()
  expect(box).not.toBeNull()
  for (let i = 0; i < 10; i++) {
    await page.mouse.move(
      box!.x + box!.width * (0.25 + i * 0.04),
      box!.y + box!.height * 0.35,
    )
    await page.waitForTimeout(60)
  }

  expect(errors).toEqual([])
})

test('分时图多日拼接可切换且不报错', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto('/')
  await page.waitForTimeout(2000)

  await page.locator('button[title="打开分时/盘口弹窗"]').click()
  await expect(page.locator('.dlg-body canvas')).toBeVisible({ timeout: 30_000 })
  await page.waitForTimeout(1200)

  // 多日分时走 /minute/history —— 此前 mock 缺该方法，这里直接抛
  for (const label of ['3日', '5日']) {
    await page.locator('.dlg-body button', { hasText: label }).first().click()
    await page.waitForTimeout(1200)
    await expect(page.locator('.chart-msg.error')).toHaveCount(0)
    const ink = await inkRatio(page, '.dlg-body canvas')
    expect(ink).toBeGreaterThan(0.01)
  }

  expect(errors).toEqual([])
})