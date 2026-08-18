# 接线契约与踩坑记录

## 目录
- Blueprint code Automation 契约
- 三个 Widget 的 slots.main schema
- 数据源接口细节
- 三联日报 prompt 模板
- 降级策略

## Blueprint code Automation 契约

托管 Python 运行器要求模块定义 `def run(ctx):` 并**返回** JSON 可序列化数据；顶层脚本代码不会执行。返回结构必须是 `{"artifact": {...}}`，artifact 匹配 result.schema。

condition 触发器要求 `conditions/should_fire.py` 暴露 `def should_fire(ctx) -> bool`（30 秒限时、无副作用；用 ctx["taskDir"] 下的状态文件去重，每个事件每天最多报一次）。

高频 schedule（如每小时）创建前必须先向用户说明每日运行次数并获明确确认。cron 分钟避开 0 和 30（用 7-23 / 37-53 区间），时区显式给 Asia/Shanghai。

## slots.main schema（Automation result.schema 与之保持一致）

### 哨兵 Widget
required: 无强制；properties（全部 number/string）：price, change_pct, date, time, shares, cost, market_value, float_pnl, float_pnl_pct, day_high, day_low, stop_loss, take_profit, alert（none/near_stop/near_target/stop_loss/take_profit）, note, limit_up, limit_down, limit_state（none/hit_up/hit_down）, limit_time。

### 动量榜 Widget
required: ["as_of", "etfs"]。as_of string；market: [{code,name,close,pct,ret5,ret20}]；etfs: [{code,name,close,pct,ret5,ret20,vol_ratio,dd20,low20,high20,pos20,signal,tag,holding}]，tag ∈ 放量突破/趋势向上/超跌反弹/企稳回升/弱势整理；signal ∈ 低吸窗口/低位磨底/高抛窗口/高位回落/中段观望（pos20=现价在 20 日收盘区间位置，≤30 低位、≥75 高位）；picks: [{code,name,close,pos20,signal,low20,high20,holding,reason}] 低吸潜力榜（≤3 只，参考低吸价=20 日最低收盘、高抛价=20 日最高收盘）；note string。

### 舆情雷达 Widget
required: ["as_of", "events"]。sentiment ∈ 偏多/偏空/中性；overview string；events: [{title,direction,impact,summary,source,time,heat(1-5),sectors[],etfs[{code,name,direction,holding}],holding_relevant,logic,watch}]，direction ∈ 利多/利空/中性，impact ∈ 高/中/低。

## 数据源接口细节

### 腾讯实时行情（哨兵）
`https://qt.gtimg.cn/q=sh588170`：必须 GBK 解码；`~` 分隔，p[3] 现价、p[4] 昨收、p[30] 时间（YYYYMMDDHHMMSS）、p[32] 涨幅%、p[33] 最高、p[34] 最低。请求头带 Referer: https://gu.qq.com/。

### 腾讯日 K（动量榜）
`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh588170,day,,,30,qfq`：**指数也必须带 `,qfq` 后缀**，否则 `bad params`；返回键为 `qfqday` 或 `day`，行格式 [date, open, close, high, low, volume, ...]。近5日=close[-1]/close[-6]-1，量能比=近5日均量/前20日均量。

### 新浪 7×24 电报（舆情雷达）
`https://zhibo.sina.com.cn/api/zhibo/feed?page={n}&page_size=20&zhibo_id=152&tag_id=0&dire=f&dpc=1&id=0&_={ts}`：JSON，`result.data.feed.list`，`rich_text` 为正文（标题在【】内），`create_time` 是 `"YYYY-MM-DD HH:MM:SS"` 字符串（不是时间戳）。

## 三联日报 prompt 模板

```
生成每日收盘三联日报。按顺序执行：
第一步：Automation.readRunArtifact 读 {动量榜automationId} 最新成功运行的 artifact。
第二步：Automation.readRunArtifact 读 {舆情automationId} 最新成功运行的 artifact。
第三步：Automation.readRunArtifact 读 {哨兵automationId} 最新成功运行的 artifact。
第四步：汇总写成中文 Markdown 日报，保存到 {workspace}\日报\日报-YYYYMMDD.md。
结构：1) 持仓哨兵（现价/浮盈亏/止损止盈/预警状态）2) 动量榜 TOP5 及持仓标的榜中位置
3) 舆情倾向与全部「高」影响事件 4) 明日观察要点 ≤3 条。
第五步：对话里汇报要点（10 行以内）。
某 artifact 读取失败则对应段落写「本次数据缺失」并继续。
```

execution：`{"kind":"agent","mode":"local_conversation","workspace":{"kind":"path","path":"<用户工作区>"}}`，result `{"kind":"conversation"}`，delivery 加桌面 notification。日报 cron 安排在动量榜刷新之后（如动量榜 15:43 → 日报 15:47）。

## 降级策略

- 后台 agent（mode: background）执行器曾出现平台级故障（`run.logs[2] must be a non-empty string`）：舆情研判因此固定走 code 规则引擎，不要改回 background agent，除非平台修复后重新验证。
- iFinD 数据源若返回 `EMPTY_DATA`，聚源 gildata fin_query 每次调用最多 3 个实体，仅适合零星补数，不适合每日批量任务——批量行情坚持用腾讯接口。
- 任一数据源失败：artifact 里写 note 说明缺失，不要让 run 失败导致 Widget 数据断更。
