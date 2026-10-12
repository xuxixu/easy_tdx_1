// 顶栏「主题 / 全局异常」E2E：两条纯前端能力，用 mock 后端即可跑通。
//
// 覆盖点：
//   1. 主题：弹窗可开、点卡片即切、CSS 变量真的落到 <html>、刷新后仍沿用
//   2. 全局异常：window.onerror / unhandledrejection / console.error 三条
//      捕获路径都能落库、未读角标出现、复制/清空可用
//
// 两条用例都会先清掉 localStorage 里的主题与异常痕迹：这两样都是持久化的，
// 不清会让上一条用例的残留记录让断言假通过。

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const THEME_BTN = 'button[aria-label="切换主题"]'
const ERROR_BTN = 'button[aria-label="查看全局异常"]'

/** 挂 initScript 清掉持久化痕迹（须在 goto 之前调用）。
 *
 *  用 sessionStorage 做哨兵而不是无条件清：initScript 每次导航都会重跑，
 *  无条件清会把「刷新后仍沿用上次主题」这条断言自己抹掉。sessionStorage
 *  按标签页隔离且能跨 reload 存活，正好用来标记「本用例已清过一次」。 */
async function resetStorage(page: Page) {
  await page.addInitScript(() => {
    if (sessionStorage.getItem('__e2e_reset')) return
    sessionStorage.setItem('__e2e_reset', '1')
    for (const k of ['easytdx.theme', 'easytdx.errors.v1', 'easytdx.errors.seenAt.v1']) {
      localStorage.removeItem(k)
    }
  })
}

test('主题弹窗切换后立即生效并持久化', async ({ page }) => {
  await resetStorage(page)
  await page.goto('/')

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

  await page.locator(THEME_BTN).click()
  const modal = page.locator('.modal-overlay')
  await expect(modal).toBeVisible()
  await expect(modal.locator('.theme-card')).toHaveCount(4)

  // 点「晴昼」应立刻切到浅色变量（token 写到 <html> 的 inline style 上）
  await modal.locator('.theme-card', { hasText: '晴昼' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(244, 246, 250)')

  // 反向切回深色：走的是图表 dispose 后按新主题重建的同一路径
  await modal.locator('.theme-card', { hasText: '深空' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(modal.locator('.theme-card.active')).toContainText('深空')

  // 最后停在浅色，刷新后应仍沿用（localStorage 持久化）
  await modal.locator('.theme-card', { hasText: '晴昼' }).click()
  await modal.getByRole('button', { name: '完成' }).click()
  await expect(modal).toBeHidden()

  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
})

test('全局异常捕获三类来源并支持复制与清空', async ({ page, context }) => {
  await resetStorage(page)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/')

  // 三条捕获路径各造一条：未捕获异常 / 未处理 reject / 仅打印的 console.error
  await page.evaluate(() => {
    setTimeout(() => {
      throw new Error('E2E 同步未捕获异常')
    }, 0)
    void Promise.reject(new Error('E2E 未处理拒绝'))
    console.error('E2E 仅打印的 console 错误')
  })

  // 顶栏出现未读角标（具体条数可能夹带页面自身的偶发日志，不写死）
  const badge = page.locator(ERROR_BTN).locator('.badge')
  await expect(badge).toBeVisible()

  await page.locator(ERROR_BTN).click()
  const modal = page.locator('.modal-overlay')
  await expect(modal).toBeVisible()

  const SYNC = 'E2E 同步未捕获异常'
  const REJECT = 'E2E 未处理拒绝'
  const LOGGED = 'E2E 仅打印的 console 错误'
  for (const msg of [SYNC, REJECT, LOGGED]) {
    await expect(modal.locator('.item', { hasText: msg })).toHaveCount(1)
  }

  // 打开即视为已读：角标消失
  await expect(badge).toBeHidden()

  // 按来源筛选：Promise 只剩未处理拒绝那一条
  await modal.locator('.chip', { hasText: 'Promise' }).click()
  await expect(modal.locator('.item')).toHaveCount(1)
  await expect(modal.locator('.item').first()).toContainText(REJECT)
  await modal.locator('.chip', { hasText: '全部' }).click()

  // 展开看堆栈
  await modal.locator('.item', { hasText: SYNC }).locator('.row1').click()
  await expect(modal.locator('.item', { hasText: SYNC }).locator('.stack')).not.toBeEmpty()

  // 复制全部 → 剪贴板含三条
  await modal.getByRole('button', { name: '复制全部' }).click()
  await expect(modal.locator('.hint')).toContainText('已复制全部')
  const clip = await page.evaluate(() => navigator.clipboard.readText())
  expect(clip).toContain(SYNC)
  expect(clip).toContain(REJECT)
  expect(clip).toContain(LOGGED)

  // 清空：确认框过掉后列表归零
  page.once('dialog', (d) => void d.accept())
  await modal.getByRole('button', { name: '清空' }).click()
  await expect(modal.locator('.empty')).toContainText('暂无异常记录')
})
