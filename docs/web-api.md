# Web API（REST + WebSocket）

## 概述

将 easy-tdx 暴露为 REST + WebSocket 服务，供前端、其他语言或远程调用。无需额外注册，零配置启动。

## 安装

```bash
# 标准安装
pip install easy-tdx[web]

# 开发模式（从源码安装，支持热重载）
pip install -e ".[web]"
```

## 快速启动

```bash
# 启动 Web API 服务器（自动连接最优 TDX 服务器）
easy-tdx serve

# 启动后浏览器打开 http://127.0.0.1:8000/docs 查看完整 API 文档（Swagger UI）
# 也可以访问 http://127.0.0.1:8000/redoc 查看 ReDoc 格式文档

# 指定端口和 TDX 服务器
easy-tdx serve --port 8080 --tdx-host 119.147.212.81

# 开发模式（代码修改后自动重载）
easy-tdx serve --reload
```

> 💡 启动后访问 **http://127.0.0.1:8000/docs** 可以看到完整的交互式 API 文档，支持在线调试每个接口。

## REST API 示例

```bash
# ── 基础行情 ──
# 获取深圳市场证券数量
curl "http://localhost:8000/api/v1/security/count?market=SZ"

# 获取股票K线
curl "http://localhost:8000/api/v1/bars?market=SZ&code=000001&category=DAY&count=100"

# 批量获取实时行情
curl -X POST "http://localhost:8000/api/v1/quotes" \
  -H "Content-Type: application/json" \
  -d '{"stocks": [{"market": "SZ", "code": "000001"}, {"market": "SH", "code": "600000"}]}'

# 市场统计
curl "http://localhost:8000/api/v1/market/stat"

# 全市场强势股排名（基于本地 vipdoc 数据，扫描约 30-60 秒）
# steady = 中长期稳健 / breakout = 近期妖股 / balanced = 均衡
curl "http://localhost:8000/api/v1/market/strength?preset=breakout&top_n=20"

# 自定义权重 + 过滤低流动性（日均成交额 ≥ 5000 万）
curl "http://localhost:8000/api/v1/market/strength?w5=0.5&w20=0.3&w60=0.2&min_amount=50000000&top_n=30"

# 板块信息（标准协议）
curl "http://localhost:8000/api/v1/block?filename=block_gn.dat"

# ── 板块分析（MAC 协议）──
# 行业板块列表
curl "http://localhost:8000/api/v1/board-mac/list?board_type=HY&count=50"

# 板块成分股（按涨幅排序）
curl "http://localhost:8000/api/v1/board-mac/members?board_symbol=881001&count=20"

# 个股所属板块
curl "http://localhost:8000/api/v1/board-mac/belong?market=SZ&code=000001"

# 板块摘要（含主力净流入、涨跌家数）
curl "http://localhost:8000/api/v1/board-mac/summary?board_symbol=881001"

# 行业板块涨幅排名 Top 10
curl "http://localhost:8000/api/v1/board-mac/ranking?board_type=HY&top_n=10"

# 板块 20 日涨幅排行
curl "http://localhost:8000/api/v1/board-mac/change-ranking?board_type=HY&days=20&top_n=10"

# ── 资金 / 信息 ──
# 个股资金流向（主力/散户净流入）
curl "http://localhost:8000/api/v1/mac/capital-flow?market=SH&code=600519"

# 个股基本信息快照
curl "http://localhost:8000/api/v1/mac/symbol-info?market=SZ&code=000001"

# 服务器交易时段信息
curl "http://localhost:8000/api/v1/mac/server-info"

# ── 公告检索（巨潮资讯网，独立数据源）──
# 检索公司公告（无需 TDX 行情服务器）
curl "http://localhost:8000/api/v1/announcements?code=688017&count=30&page=1"
# 返回每条含 url（4 参数可直点打开）和 pdf_url（PDF 直链）：
# {"data": [{"title":"...","type":"...","date":"...","url":".../detail?stockCode=...","pdf_url":"http://static.cninfo.com.cn/.../xxx.PDF",...}], "count": 30}

# ── 财报三表（新浪财经，独立数据源）──
# 利润表（type: lrb/fzb/llb）
curl "http://localhost:8000/api/v1/sina/financial-report?code=600519&type=lrb&num=8"
# 返回每行一期（最新在前），列为科目名（float）+ {科目}_同比（如有）：

# ── 排行 / 竞价 / 异动 ──
# 全 A 涨幅排行前 20
curl "http://localhost:8000/api/v1/mac/quote-list?category=A&count=20&sort_type=CHANGE_PCT"

# 集合竞价数据
curl "http://localhost:8000/api/v1/mac/auction?market=SZ&code=000001"

# 市场异动行情
curl "http://localhost:8000/api/v1/mac/unusual?market=SH&count=50"

# ── 扩展市场（期货/港股/美股）──
# 港股 K 线
curl "http://localhost:8000/api/v1/ex/bars?market=HK_MAIN_BOARD&code=00700&category=DAY&count=30"

# 美股实时报价
curl "http://localhost:8000/api/v1/ex/quote?market=US_STOCK&code=AAPL"

# ── 板块（A股 HY/GN + 港美股 HK_HY/HK_GN/US_HY/US_GN，走对应协议栈）──
# 港股行业板块列表
curl "http://localhost:8000/api/v1/board-mac/list?board_type=HK_HY&count=200"

# 美股概念板块列表
curl "http://localhost:8000/api/v1/board-mac/list?board_type=US_GN&count=50"

# 港股板块总览（当日涨跌幅 + 领涨股 + 多周期，15s 缓存）
curl "http://localhost:8000/api/v1/board-mac/overview?board_type=HK_HY&metrics=SPEED,CHANGE_3D,CHANGE_5D,CHANGE_20D,YTD"

# 港股板块成分股
curl "http://localhost:8000/api/v1/board-mac/members?board_symbol=HK0285&count=100"

# 美股热点矩阵（building 轮询）
curl "http://localhost:8000/api/v1/board-mac/hotspot?board_type=US_HY&days=20&mode=top&per_day=5"

# ── 港股 / 美股（一等公民市场：与 A 股同走 /bars /minute /quotes /watchlist /backtest）──
# 市场元信息（顶栏切换器用：各市场可用性/标的数/货币）
curl "http://localhost:8000/api/v1/overseas/meta"

# 搜索标的（服务端索引，毫秒级；symbol 形如 HK:00700 / US:AAPL）
curl "http://localhost:8000/api/v1/overseas/symbols?market=HK&keyword=腾讯&limit=10"
curl "http://localhost:8000/api/v1/overseas/symbols?market=US&keyword=AAPL&limit=10"

# 批量报价（五档 + 成交额等）
curl "http://localhost:8000/api/v1/overseas/quotes?market=HK&codes=00700,09988"

# 全市场榜单（涨幅/跌幅/成交额/成交量 Top30 + 涨跌家数；首次 building，前端轮询至 ready）
curl "http://localhost:8000/api/v1/overseas/rank?market=HK"

# 港股/美股 K 线·分时·逐笔（与 A 股同端点，market=HK/US）
curl "http://localhost:8000/api/v1/bars?market=HK&code=00700&category=DAY&count=30"
curl "http://localhost:8000/api/v1/minute?market=US&code=AAPL"

# 港股/美股回测（symbol 形如 HK:00700 / US:AAPL；美股分钟线自动只留盘中）
curl -X POST "http://localhost:8000/api/v1/backtest/run/async" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "HK:00700", "strategy": "ma_cross", "params": {}, "category": "DAY", "count": 250}'

# ── 真指数（TDX 18 台服务器全无，走免费接口；与 A 股同端点）──
# 港股：恒生/国企/恒科（HK:HSI/HSCEI/HSTECH）
# 美股：道指/纳指综合/标普500/纳指100（US:DJI/IXIC/SPX/NDX）
# K线优先级：akshare 全历史(日/周/月) → 腾讯快照(仅最新1根)
# 报价优先级：新浪(延时约15分钟) → 腾讯
# 响应每行带 source 字段标注实际来源：tdx / ak / sina / qq
curl "http://localhost:8000/api/v1/bars?market=HK&code=HSCEI&category=DAY&count=30"
curl "http://localhost:8000/api/v1/bars?market=US&code=NDX&category=DAY&count=800"
curl "http://localhost:8000/api/v1/minute?market=US&code=DJI"
curl "http://localhost:8000/api/v1/overseas/quotes?market=US&codes=DJI,IXIC,SPX,NDX"

# 美股时段（前端 夜盘/盘前/盘中/盘后 按钮；北京时间，夏令）
#   盘前 16:00-21:30 · 盘中 21:30-04:00 · 盘后 04:00-08:00 · 夜盘无分钟数据

# ── 策略库修改 / 信号定向扫描 ──
# 部分更新一条策略（名称/策略类型/参数/备注/标签/上下文）
curl -X PUT "http://localhost:8000/api/v1/strategies/<id>" \
  -H "Content-Type: application/json" \
  -d '{"name": "新名称", "params": {"fast": 5, "slow": 20}}'

# 定向扫描：某只股票 × 某几个保存策略（只给买入/卖出信号）
curl -X POST "http://localhost:8000/api/v1/backtest/signal-scan/run/async" \
  -H "Content-Type: application/json" \
  -d '{"window_bars": 5, "symbols": ["US:AAPL"], "strategy_ids": ["<id>"]}'

# ── 技术指标 ──
# 列出所有可用指标
curl "http://localhost:8000/api/v1/indicator/list"

# 计算 MACD + KDJ 指标
curl -X POST "http://localhost:8000/api/v1/indicator/compute" \
  -H "Content-Type: application/json" \
  -d '{"data": [{"open":10,"close":10.5,"high":11,"low":9.5,"vol":1000}], "indicators": ["MACD", "KDJ"]}'

# ── 缠论分析 ──
curl -X POST "http://localhost:8000/api/v1/chanlun/analyze" \
  -H "Content-Type: application/json" \
  -d '{"market": "SZ", "code": "000001", "category": "DAY", "count": 200}'

# ── 板块总览（一次取全部板块：当日涨跌幅 + 涨速 + 3/5/20日/YTD 涨幅 + 领涨股，服务端 15s 缓存）──
# board_type: HY 行业一级 / HY2 行业二级 / GN 概念 / FG 风格 / DQ 地区
curl "http://localhost:8000/api/v1/board-mac/overview?board_type=HY"
curl "http://localhost:8000/api/v1/board-mac/overview?board_type=GN"

# ── 回测任务（WebUI 回测工作台同款后端）──
# 列出内置策略及参数 schema
curl "http://localhost:8000/api/v1/backtest/strategies"
# 提交异步回测（strategy 见 /backtest/strategies；完整字段与 portfolio/multi/optimize/wf/evaluate
# 各端点的请求体以 /docs 的 Swagger 为准），返回 task_id
curl -X POST "http://localhost:8000/api/v1/backtest/run/async" \
  -H "Content-Type: application/json" \
  -d '{"strategy": "ma_cross", "symbol": "SZ:000001", "category": "DAY", "count": 2000}'
# 轮询任务结果（对比页/导出亦走 /backtest/tasks）
curl "http://localhost:8000/api/v1/backtest/tasks/<task_id>"
# 删除已终态任务（运行中 409 拒绝；结果对比页清理用）
curl -X DELETE "http://localhost:8000/api/v1/backtest/tasks/<task_id>"

# ── 策略类型（内置浏览 + 自定义类型增删改；自定义=基于内置的命名预设包）──
curl "http://localhost:8000/api/v1/backtest/strategies"  # 全部类型（含 custom 标记）
curl "http://localhost:8000/api/v1/strategy-types"       # 自定义类型存储记录（含基准名）
curl -X POST "http://localhost:8000/api/v1/strategy-types" \
  -H "Content-Type: application/json" \
  -d '{"label": "双均线·短线版", "base": "ma_cross", "description": "", "default_params": {"fast": 5, "slow": 20}, "preset_grid": {}}'
curl -X PUT "http://localhost:8000/api/v1/strategy-types/custom_<id>" \
  -H "Content-Type: application/json" \
  -d '{"label": "新名称", "base": "ema_cross", "description": "", "default_params": {}, "preset_grid": {}}'
curl -X DELETE "http://localhost:8000/api/v1/strategy-types/custom_<id>"  # 内置类型拒绝 400

# ── 策略库（保存的策略持久化 SQLite）──
curl "http://localhost:8000/api/v1/strategies"

# ── 自选股 ──
curl "http://localhost:8000/api/v1/watchlist"
curl -X POST "http://localhost:8000/api/v1/watchlist" \
  -H "Content-Type: application/json" -d '{"market": "SH", "code": "600519", "name": "贵州茅台"}'

# 自选「近 3 日 / 近 1 周 / 近 2 周」涨跌幅锚点（窗口固定为 3,5,10；交易日偏移口径）
# T = 上证指数日线（交易日历）中 <= 今天的最后一天；D_n = T 往前 n 个交易日；
# 锚点 = 个股日线（/bars 同款 QFQ，count 按窗口推导 ≈20 根，MAC 单页请求）中 date <= D_n 的最后一根 bar。
# 只回锚点收盘价：涨跌幅由前端用实时价现算（盘中随 SSE 跳动，无需轮询本接口）。
# 个股日线与日历都走进程内缓存（当日不变、次日失效），同一天重复刷新零行情请求。
curl "http://localhost:8000/api/v1/watchlist/returns"
# 实测样例（2026-09-11 盘中）：
# {"trade_date":"2026-09-11",
#  "items":{"SH600519":{"last_close":1272.95,"last_date":"2026-09-11","stale_days":0,
#                       "anchors":[{"days":3,"close":1309.3,"date":"2026-09-08"},
#                                  {"days":5,"close":1330.0,"date":"2026-09-04"},
#                                  {"days":10,"close":1297.4,"date":"2026-08-28"}]},
#           "SZ301999":{"error":"no_data"}}}
# 注：anchors[].close 是**锚点收盘价**（不是涨跌幅），前端 (实时价/锚点 − 1)×100 得该列。
# 容错：今日非交易日 → T 回退；锚点日停牌 → 退到最近一根并回实际 date；数据不足
# （次新）→ anchors[].close 为 null（前端显示 '-'）；长期停牌 → last_date +
# stale_days；单只失败只在该 key 落 error（no_data/fetch_failed），不影响整表。
# 无 MAC 连接时按 /bars 语义降级标准协议（不复权，除权日可能出现假跌幅，日志标注）。

# ── AI 解读（模型 Key 只存本地 ~/.easy_tdx/llm.json）──
curl "http://localhost:8000/api/v1/llm/config"                                # 当前配置 + Provider 预设
curl -X POST "http://localhost:8000/api/v1/llm/chat/async" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "解读这份回测报告：..."}'                                    # 后台任务，GET /llm/chat/tasks/{id} 轮询

# ── 服务器设置（候选行情服务器增删改 + 测速切换）──
curl "http://localhost:8000/api/v1/server/hosts"                             # 列出候选 + 当前 host
curl -X POST "http://localhost:8000/api/v1/server/hosts" \
  -H "Content-Type: application/json" -d '{"host": "180.153.18.170"}'        # 新增（去重追加）
curl -X DELETE "http://localhost:8000/api/v1/server/hosts/180.153.18.170"    # 删除（至少保留 1 台）
curl -X POST "http://localhost:8000/api/v1/server/test" \
  -H "Content-Type: application/json" -d '{}'                                # 全部测速（多服务器容灾选最优）

# ── 成交量排名（A/港/美 Top30）──
# A 股：MAC 排行 VOLUME 排序（多服务器自动容灾，前端市场看板「成交量」tab）
curl "http://localhost:8000/api/v1/mac/quote-list?category=A&count=30&sort_type=VOLUME&sort_order=DESC"
# 港/美：全市场榜单 by_vol（与 gainers/losers/by_amount 同快照，Top30；首次 building 轮询至 ready）
curl "http://localhost:8000/api/v1/overseas/rank?market=HK"

# ── 推送服务（买卖信号 key-only 推送：Server酱/WXPush/百度云推送/MobPush/Webhook）──curl "http://localhost:8000/api/v1/push/config"                              # 当前配置（key 脱敏）+ 通道表
curl -X PUT "http://localhost:8000/api/v1/push/config" \
  -H "Content-Type: application/json" \
  -d '{"channels": [{"provider": "serverchan", "key": "SCTxxxx", "endpoint": "", "enabled": true}]}'
curl -X POST "http://localhost:8000/api/v1/push/test"                        # 发测试消息验通道
curl -X POST "http://localhost:8000/api/v1/push/send-signal" \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"symbol": "SH:600519", "latest_signal": "BUY"}], "window_bars": 5}'

# ── 交易时段（自动刷新门控用）──
curl "http://localhost:8000/api/v1/market/session"
```

## WebSocket 实时行情

`/api/v1/ws/realtime/{symbol}`（v1.28 起接通数据源）：连接即订阅指定标的，服务端
经 `RealtimeDataFeed`（按 `interval` 秒轮询五档快照 → `EventBus`）推送 tick 帧；
连接断开自动退订，无人订阅时完全停止轮询。盘外时段默认只睡不拉（交易时段过滤），
本地冒烟/演示可配合 `EASY_TDX_E2E_MOCK=1` 的合成行情随时验证（见
`scripts/ws_smoke.py`）。

```javascript
const ws = new WebSocket("ws://localhost:8000/api/v1/ws/realtime/SZ000001");

ws.onmessage = (event) => {
    const frame = JSON.parse(event.data);
    if (frame.type === "tick") {
        // {type:"tick", symbol:"SZ000001", market:"SZ", code:"000001",
        //  price:10.5, volume:12345, ts:1760000000.0,
        //  open, high, low, pre_close, amount, name}
        console.log(frame.symbol, frame.price, frame.ts);
    } else if (frame.type === "ping") {
        // 服务端 30s 空闲心跳，忽略即可（客户端无须回包）
    }
};

// 动态订阅更多标的（服务端回 {"type":"status","msg":"subscribed SH600000"}）
ws.send(JSON.stringify({action: "subscribe", symbol: "SH600000"}));
// 退订
ws.send(JSON.stringify({action: "unsubscribe", symbol: "SH600000"}));
```

### 服务端推送帧（JSON）

| type | 触发 | 字段 |
|------|------|------|
| `tick` | 轮询到标的的最新快照（价格/量变化才推，约 `interval` 秒一拍） | `symbol`、`market`、`code`、`price`、`volume`、`ts`（epoch 秒）、`open`、`high`、`low`、`pre_close`、`amount`、`name` |
| `ping` | 连续 30s 未收到客户端消息的心跳 | —（客户端忽略即可，无须回包） |
| `status` | 客户端 subscribe/unsubscribe 的确认 | `msg`（如 `subscribed SH600000`） |
| `error` | 非法 JSON / 未知 action / 超出订阅上限 | `msg` |

### 客户端控制消息（JSON 文本帧）

```json
{"action": "subscribe", "symbol": "SH600000"}
{"action": "unsubscribe", "symbol": "SH600000"}
```

### 行为约定

- **连接即订阅** path 上的 symbol；断开自动退订全部标的。
- **按需轮询**：订阅集合为空时服务端不产生任何行情请求；去重后标的总数上限
  80（`get_stock_quotes` 协议约束）。
- **交易时段**：默认 A 股时段外只睡不拉（无 tick 帧，心跳照发）；mock 模式
  （`EASY_TDX_E2E_MOCK=1`）不受限制。
- **背压**：消费过慢时丢最旧快照保最新，不积压。
- 环境变量：`EASY_TDX_WS_INTERVAL`（轮询间隔秒数，默认 3.0）。

浏览器接入建议（自动重连 + 心跳容忍）：`onclose` 后指数退避重连（参考
`web-ui/src/stores/quotes.ts` 对 SSE 的同类处理）；`{"type":"ping"}` 心跳帧直接
忽略、不回包；连续 N 秒无任何帧（含 ping）再视为僵死连接主动重连。

### 前端接入方式（自动重连 + 心跳容忍）

```typescript
function connectRealtime(symbol: string, onTick: (f: TickFrame) => void) {
  let retry = 0
  let ws: WebSocket | null = null
  const open = () => {
    ws = new WebSocket(`ws://${location.host}/api/v1/ws/realtime/${symbol}`)
    ws.onmessage = (e) => {
      const frame = JSON.parse(e.data)
      if (frame.type === 'tick') { retry = 0; onTick(frame) }  // ping/status 忽略
    }
    ws.onclose = () => {
      retry += 1
      setTimeout(open, Math.min(1000 * 2 ** (retry - 1), 30_000))  // 指数退避
    }
  }
  open()
  return () => ws?.close()
}
```

> 说明：看板/自选页的实时刷新已由 SSE `/stream/quotes`（全量快照、单连接共享）
> 承担；WS 通道定位是**按需订阅单标的 tick 事件**（后续实时策略信号的接入点），
> 两条链路按场景选用，不要求同时连接。手动冒烟见 `scripts/ws_smoke.py`。


## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 编程 API

```python
from easy_tdx.web import create_app
import uvicorn

app = create_app(host="119.147.212.81", port=7709)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

