# easy-tdx Web UI

行情终端 + 回测工作台的前端（Vue 3 + Vite + TypeScript + Pinia + ECharts）。

生产环境下前端已编译进 `web-ui/dist/`，由后端 FastAPI **同源托管**——`easy-tdx serve` 一条命令后浏览器打开 `http://localhost:8000` 即可，无需单独跑前端。本文件说的是开发模式下的跑法。

## 快速开始（开发）

需要两个进程：后端 FastAPI（行情 + 回测 API）+ 前端 Vite dev server。

```bash
# 1. 启动后端（仓库根目录，使用 venv）
.venv/Scripts/python -m easy_tdx serve --host 127.0.0.1 --port 8000 --no-open-browser

# 2. 启动前端（本目录）
npm install      # 首次
npm run dev      # http://localhost:5173
```

浏览器打开 `http://localhost:5173`（用 `localhost`，别用 `127.0.0.1`）。开发期 `/api` 请求由 vite proxy 转发到后端 `127.0.0.1:8000`，无需处理跨域。

## 页面一览

顶栏可一键在 **A 股 / 港股 / 美股** 间切换，各市场独立指数条与交易时段判定。

- **行情**：市场看板 / 行业总览 / 概念总览 / 热点滚动 / 大盘日历 / 涨停生态 / 市场情绪 / 自选行情 / 期货持仓排名 / 美股期权（`/us-options`）/ **美股观测雷达**（`/us-radar`）
- **分析**：单标的回测 / 组合回测 / 参数寻优 / 结果对比 / 策略库 / 策略类型 / 信号雷达 / AI 解读历史
- **系统**：服务器设置 / 指数设置 / 技术指标 / 自定义指标 / 推送设置 / AI 设置

两个页面值得单独说明：

- **美股观测雷达**（`/us-radar`）：分区复盘美股的静态快照页，数据由后端管线（`src/easy_tdx/radar/`，入口 `scripts/build_us_radar.py`）从免费源实算成 `public/data/us-radar.json`，前端运行时 `fetch` 拉取（[data/usRadar.ts](src/data/usRadar.ts) + [views/UsRadarView.vue](src/views/UsRadarView.vue) + 27 个 [components/radar/](src/components/radar/) 组件）。取不到源的区渲染「数据源不可用 + 原因」并在页头汇总「N 区缺源」。
- **美股期权**（`/us-options`）：期权链结构视图，**当前为示例数据**（[data/usOptions.ts](src/data/usOptions.ts)）并在页头标注——后端还没有期权链数据源，页面已按真实接口的返回形状写好。

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 框架 | Vue 3.5 + TypeScript 6 | Composition API + `<script setup>` |
| 构建 | Vite 8 | dev proxy 解决跨域；路由级 `() => import()` 拆包（echarts 独立 chunk） |
| 状态 | Pinia 3 | 报价 SSE 缓存 / 回测任务 / 策略与自选 |
| 路由 | Vue Router 4 | 25 个视图，首屏看板静态、其余按路由懒加载 |
| 图表 | ECharts 6（按需引入） | K 线 / 分时 / 热力图 / 净值回撤 / 雷达图 |

## 目录结构

```
src/
├── main.ts / App.vue / router.ts     # 入口、根布局、路由（含懒加载拆包）
├── api.ts                            # REST/SSE 封装（全部后端端点集中在此，BASE = /api/v1）
├── types.ts                          # 后端 schema 的 TS 镜像
├── market.ts                         # 市场判定（A股/港股/美股、交易时段、指数 ETF 代理表）
├── errors.ts                         # 全局异常捕获（未捕获异常 / Promise 拒绝 / console.error / Vue）
├── theme.ts / style.css / echarts-setup.ts
├── views/                            # 25 个页面（*View.vue）
├── components/                       # 48 个组件
│   ├── radar/                        # 27 个美股观测雷达区块组件
│   └── ...                           # K 线 / 分时 / 盘口 / 净值 / 指标表等
├── data/                             # 雷达与期权的数据层（类型 + 口径工具）
├── stores/                           # Pinia：报价 / 回测任务 / 策略
├── utils/                            # asyncGuard（序号守卫 + 可中止 sleep）等
├── grading/                          # 评级权重与计算
└── __tests__/                        # node:test 单测
```

## 测试与构建

```bash
npm test        # node --test src/__tests__/*.test.ts
npm run test:e2e   # playwright（见 e2e/README.md，需先起后端）
npm run build   # vue-tsc -b && vite build，产物在 dist/
```

## 注意事项

- **取行情需要后端能连通行情服务器**：`/api/v1/bars` 等走 TDX 协议取真实行情；无网络时回测路由仍可用，但取行情会失败。
- **A 股配色惯例**：红涨绿跌（与 ECharts 默认相反），见 `echarts-setup.ts`。
- **美股分钟线只有盘中**：TDX 与东财免费源都只给美东 09:30–16:00，盘前/盘后/夜盘无数据（`market.ts` 里有实测结论，别按「含盘前盘后」的旧前提排查）。
- **指数分时**：港股指数原生（腾讯分时），美股指数无原生分时 → 以 SPY / QQQ / DIA 代理并在界面明示；`INDEX_ETF_PROXY` 是唯一的代理映射表。
