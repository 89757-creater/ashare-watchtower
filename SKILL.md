---
name: ashare-watchtower
description: 一键搭建 A 股个人监控看板系统（Kimi Work / Daimon Blueprint）。包含四个联动组件：持仓哨兵（实时行情+涨跌停/止损止盈预警）、ETF 动量榜（每日收盘动量排名）、舆情雷达（新浪 7×24 电报的板块冲击规则初判）、每日收盘三联日报（定时任务+桌面通知）。当用户要求搭建/安装/复刻 A 股监控看板、持仓预警、ETF 动量跟踪、舆情盯盘、收盘日报，或提到「哨兵」「动量榜」「舆情雷达」「三联日报」时使用。
---

# A股瞭望塔 · 个人监控看板系统

把四个生产验证过的组件安装为用户的 Blueprint 资产：3 个 Widget + 5 个 Automation（2 个 cron 定时任务、3 个 widget 任务）。所有数据源为免费公开接口（腾讯行情、新浪 7×24），无需 API Key。

## 安装流程（严格按顺序）

### 1. 收集用户配置

| 配置项 | 示例 | 用于 |
|---|---|---|
| 持仓标的（sh/sz+代码）、份额、成本价 | sh588170, 600, 1.059 | 哨兵 |
| 止损价、止盈价、涨跌停幅度 | 0.85, 1.05, 0.20 | 哨兵+预警 |
| ETF 观察池（≤21 只） | 用脚本默认池或用户自选 | 动量榜 |
| 刷新频率偏好 | 默认见下文 cron | 全部 |

缺省直接用脚本默认值，只替换持仓标的即可跑通。

### 2. 填写配置

编辑 `scripts/` 中每个文件的「用户配置区」注释块（sentinel_quote.py / sentinel_alert.py / conditions/should_fire.py 三处持仓配置必须保持一致）。

### 3. 创建 Widget（3 个）

每个 Widget：`Widget.create`（slots.main schema 见 `references/wiring.md`）→ 把对应 `assets/widget-*/index.html` 完整写入其 workspace 根目录 → `Widget.validate`。标题里的标的名称按用户持仓调整。

### 4. 创建 Automation（5 个）

按 `references/wiring.md` 的契约逐个创建，脚本从 `scripts/` 复制到各 Automation 的 assetsRoot。通用规则：先 manual 触发创建并实测跑通，再 update 成定时，最后确认 enabled。

| 任务 | 类型 | 脚本 | 推荐触发 |
|---|---|---|---|
| 哨兵·行情刷新 | code | sentinel_quote.py | cron `13,43 9-15 * * 1-5` |
| 哨兵·关键位预警 | code + condition | sentinel_alert.py + conditions/should_fire.py | condition every 30m |
| ETF 动量榜 | code | etf_momentum.py | cron `43 15 * * 1-5` |
| 舆情雷达 | code | news_radar.py | cron `17 9-21 * * *` |
| 三联日报 | agent local_conversation | prompt 模板见 wiring.md | cron `47 15 * * 1-5`，桌面通知 |

### 5. 接线与验证

`Binding.create`（automation_widget）连 3 对：哨兵刷新→哨兵 Widget、动量榜→动量榜 Widget、舆情→舆情 Widget。预警任务**只接通知、不接 Widget**（一个 slot 只能有一条有效 Binding，重复绑定会顶掉旧线）。

每对Binding：跑一次 Automation → 确认 run `succeeded` 且 `deliveryResults` 有该 bindingId 的 succeeded 行 → `Widget.read` 看到 `latestData.main`。

### 6. 放置看板

`Canvas.placeWidget`：哨兵 + 动量榜放同一个桌面 Canvas（grid 5x8），舆情雷达单独一个 Canvas（grid 6x10）。

### 7. 交付说明（必须告知用户）

- 定时任务只在 Kimi Work 应用运行时执行，关闭/休眠不补跑
- 预警时刻精度为 ±30 分钟（condition 轮询间隔）
- 舆情方向是关键词规则初判，不构成投资建议

## 关键契约与踩坑

读 `references/wiring.md`：run(ctx) 返回契约、各 artifact schema、腾讯行情两个接口的坑（GBK 解码、ifzq K线必须带 `,qfq` 后缀）、新浪电报字段、后台 agent 故障时的降级策略、cron 避开整点/半点。
