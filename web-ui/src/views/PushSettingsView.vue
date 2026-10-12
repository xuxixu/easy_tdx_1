<script setup lang="ts">
// 推送设置页：买卖信号 key-only 推送（Server酱 / WXPush / 百度云推送 / MobPush / Webhook）。
// 表单 ⇆ ~/.easy_tdx/push.json；key 脱敏回显，留空/原样回传不覆盖已存 key。
import { onMounted, ref } from 'vue'
import { fetchPushConfig, savePushConfig, testPush, formatError } from '../api'
import type { PushChannel, PushProviderInfo } from '../types'

interface Row extends PushChannel {
  showKey: boolean
}

const providers = ref<PushProviderInfo[]>([])
const rows = ref<Row[]>([])
const configPath = ref('')
const configured = ref(false)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const message = ref('')
const error = ref('')
const testResult = ref('')

const ENDPOINT_HINT: Record<string, string> = {
  serverchan: 'Server酱无需 endpoint（固定 sctapi.ftqq.com）',
  wxpush: 'WXPush：你的 Worker 地址，留空用默认兼容入口',
  baidu: '百度云推送：必填网关地址（直连需 ak+sk 双签，走网关转发）',
  mob: 'MobPush：REST 地址，留空用默认入口',
  webhook: '通用 Webhook：必填完整 URL（企业微信/钉钉/Bark 均可）',
}

function blankRow(provider = 'serverchan'): Row {
  return { provider, key: '', endpoint: '', enabled: true, showKey: false }
}

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetchPushConfig()
    providers.value = resp.providers
    configPath.value = resp.config_path
    configured.value = resp.configured
    rows.value = resp.config.channels.map((c) => ({ ...c, showKey: false }))
    if (rows.value.length === 0) rows.value = [blankRow()]
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

function addRow() {
  if (rows.value.length >= 5) return
  const used = new Set(rows.value.map((r) => r.provider))
  const free = providers.value.map((p) => p.id).find((id) => !used.has(id)) ?? 'webhook'
  rows.value.push(blankRow(free))
}

function delRow(i: number) {
  rows.value.splice(i, 1)
  if (rows.value.length === 0) rows.value = [blankRow()]
}

async function save() {
  saving.value = true
  error.value = ''
  message.value = ''
  testResult.value = ''
  try {
    const resp = await savePushConfig(
      rows.value
        .filter((r) => r.provider)
        .map((r) => ({ provider: r.provider, key: r.key, endpoint: r.endpoint, enabled: r.enabled })),
    )
    configured.value = resp.configured
    rows.value = resp.config.channels.map((c) => ({ ...c, showKey: false }))
    if (rows.value.length === 0) rows.value = [blankRow()]
    message.value = `已保存到 ${resp.config_path}`
  } catch (e) {
    error.value = formatError(e)
  } finally {
    saving.value = false
  }
}

async function test() {
  testing.value = true
  error.value = ''
  testResult.value = ''
  try {
    await save()
    if (error.value) return
    const r = await testPush()
    if (r.ok) {
      testResult.value = `✓ 推送成功 · ${r.sent}/${r.total} 通道送达`
    } else {
      const errs = (r.results ?? []).filter((x) => !x.ok).map((x) => `${x.provider}:${x.error}`).join('；')
      testResult.value = `✗ 失败 · ${r.error ?? errs ?? '未知错误'}`
    }
  } catch (e) {
    error.value = formatError(e)
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <div class="push-settings">
    <aside class="config-panel">
      <h2>推送设置</h2>
      <p class="hint">
        填 key 即可把信号雷达的买入/卖出信号推出去。配置落盘到
        <code>{{ configPath || '~/.easy_tdx/push.json' }}</code>。
        key 脱敏回显，留空不修改，填 CLEAR 清除。
      </p>

      <div v-for="(r, i) in rows" :key="i" class="chan-card">
        <div class="chan-head">
          <select v-model="r.provider">
            <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
          <label class="en-toggle"><input v-model="r.enabled" type="checkbox" />启用</label>
          <button class="btn-mini-del" title="删除该通道" @click="delRow(i)">删</button>
        </div>
        <label class="field">
          <span>Key{{ r.provider === 'serverchan' ? '（SendKey）' : r.provider === 'wxpush' ? '（token）' : r.provider === 'mob' ? '（appKey）' : r.provider === 'baidu' ? '（ApiKey）' : '（可空，作 token）' }}</span>
          <div class="key-row">
            <input
              v-model="r.key"
              :type="r.showKey ? 'text' : 'password'"
              placeholder="已保存（留空不修改，填 CLEAR 清除）"
              autocomplete="off"
              spellcheck="false"
            />
            <button class="btn-eye" @click="r.showKey = !r.showKey">{{ r.showKey ? '隐' : '显' }}</button>
          </div>
        </label>
        <label class="field">
          <span>网关地址（endpoint）</span>
          <input v-model="r.endpoint" type="text" placeholder="https://…" spellcheck="false" />
        </label>
        <p class="ep-hint">{{ ENDPOINT_HINT[r.provider] ?? '' }}</p>
      </div>

      <button class="btn-ghost" :disabled="rows.length >= 5" @click="addRow">＋ 新增通道</button>

      <div class="actions">
        <button class="btn-primary" :disabled="saving || loading" @click="save">
          {{ saving ? '保存中…' : '保存配置' }}
        </button>
        <button class="btn-ghost" :disabled="testing || loading" @click="test">
          {{ testing ? '测试中…' : '保存并测试' }}
        </button>
      </div>

      <div v-if="message" class="message">{{ message }}</div>
      <div v-if="testResult" class="test-result" :class="{ ok: testResult.startsWith('✓') }">
        {{ testResult }}
      </div>
      <div v-if="error" class="error-banner">⚠ {{ error }}</div>
      <div v-if="!loading && !configured" class="warn-banner">
        尚未配置启用的推送通道——先填 key 并保存。
      </div>
    </aside>

    <main class="info-panel">
      <h3>通道说明</h3>
      <table class="provider-table">
        <thead>
          <tr>
            <th>通道</th>
            <th>填什么 key</th>
            <th>推到哪里</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Server酱</td>
            <td class="mono">SendKey（sct.ftqq.com）</td>
            <td>微信服务号/企业微信</td>
          </tr>
          <tr>
            <td>WXPush</td>
            <td class="mono">token + Worker 地址</td>
            <td>微信弹窗+声音（Cloudflare Workers）</td>
          </tr>
          <tr>
            <td>百度云推送</td>
            <td class="mono">ApiKey + 网关地址</td>
            <td>APP（经网关转发）</td>
          </tr>
          <tr>
            <td>MobPush</td>
            <td class="mono">appKey（+REST 地址）</td>
            <td>APP 多通道（别名/标签/分群）</td>
          </tr>
          <tr>
            <td>通用 Webhook</td>
            <td class="mono">完整 URL（key 可空）</td>
            <td>企业微信机器人/钉钉/Bark 等</td>
          </tr>
        </tbody>
      </table>
      <p class="hint">
        信号雷达页扫出买入/卖出信号后，点「推送信号」即经全部启用通道发出；
        标题自动汇总买/卖家数，正文列出标的×策略×日期×收盘（最多 50 条）。
      </p>
    </main>
  </div>
</template>

<style scoped>
.push-settings {
  display: flex;
  height: 100%;
  overflow: hidden;
}
.config-panel {
  width: 380px;
  flex-shrink: 0;
  padding: 20px;
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
  overflow-y: auto;
}
.config-panel h2 {
  font-size: 16px;
  margin-bottom: 12px;
}
.hint {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
}
.hint code {
  font-family: var(--font-mono);
  font-size: 11px;
  word-break: break-all;
}
.chan-card {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
}
.chan-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.chan-head select {
  flex: 1;
  padding: 5px 8px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 12px;
}
.en-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}
.btn-mini-del {
  padding: 2px 8px;
  font-size: 11px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-dim);
  cursor: pointer;
}
.btn-mini-del:hover {
  border-color: var(--red, #f44336);
  color: var(--red, #f44336);
}
.field {
  display: block;
  margin-top: 8px;
}
.field span {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.field input {
  width: 100%;
  padding: 6px 8px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 12px;
  font-family: var(--font-mono);
}
.key-row {
  display: flex;
  gap: 6px;
}
.btn-eye {
  padding: 0 10px;
  font-size: 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  cursor: pointer;
}
.ep-hint {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-dim);
}
.actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}
.btn-primary {
  flex: 1;
  padding: 9px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 13px;
}
.btn-ghost {
  flex: 1;
  padding: 9px;
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 13px;
  margin-top: 12px;
}
.actions .btn-ghost {
  margin-top: 0;
}
.message {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--accent-bg, rgba(0, 120, 212, 0.1));
  border-radius: var(--radius);
  font-size: 12px;
  color: var(--accent);
  word-break: break-all;
}
.test-result {
  margin-top: 10px;
  padding: 8px 12px;
  background: rgba(244, 67, 54, 0.08);
  border-radius: var(--radius);
  font-size: 12px;
  color: var(--red, #f44336);
  word-break: break-all;
}
.test-result.ok {
  background: rgba(76, 175, 80, 0.12);
  color: var(--green, #4caf50);
}
.error-banner {
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(244, 67, 54, 0.1);
  border-radius: var(--radius);
  font-size: 12px;
  color: var(--red, #f44336);
}
.warn-banner {
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(255, 193, 7, 0.1);
  border-radius: var(--radius);
  font-size: 12px;
  color: var(--warn, #ffc107);
}
.info-panel {
  flex: 1;
  overflow: auto;
  padding: 20px;
}
.info-panel h3 {
  font-size: 14px;
  margin-bottom: 12px;
}
.provider-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
  margin-bottom: 14px;
}
.provider-table th {
  text-align: left;
  padding: 7px 10px;
  border-bottom: 2px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
}
.provider-table td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
}
.mono {
  font-family: var(--font-mono);
  font-size: 11.5px;
}
</style>
