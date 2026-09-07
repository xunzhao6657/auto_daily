---
name: ashare-daily-report
title: A股每日报告生成（盘前晨报 v4.2 + 收盘复盘 · 云端适配版）
version: v4.2-cloud.1
source: 迁移自本地 dsh 链路 prompts/morning-brief-v4-prompt.md、post-market-review-prompt.md、multi-dim-scoring-v3-prompt.md（2026-09-08 打包）
---

# A股每日报告生成 Skill（云端版）

本 skill 沉淀了本地日报链路迭代到 v4.2 的完整提示词方法论，供 `scripts/generate_report.py`
与 `app.py` 在云端（Streamlit / GitHub Actions）调用 DeepSeek 时加载，保证云端报告与本地
dsh 链路同源同质。

## 文件清单

| 文件 | 用途 |
|---|---|
| `prompts/system.md` | 系统提示词：角色设定、三条铁律、写作规范（红涨绿跌/禁编造/时间口径） |
| `prompts/am.md` | 盘前晨报任务提示词（v4.2 结构：TL;DR 决策卡 / 多维窄区间预测 / 情景表 / 决策树 / 昨日预测多维评判 / 修正闭环） |
| `prompts/pm.md` | 收盘复盘任务提示词（当日市场定性 / 盘面结构 / 情绪观察 / 晨报预测初步对照 / 明日关注点） |
| `prompts/scoring-v3.md` | 多维评判·精细连续评分规则 v3（9 维度 0.00-1.00 连续分，方向对≠高分），am.md 内已内嵌浓缩版，此处为完整规则存档 |
| `correction-library.md` | 修正建议库（自修正闭环的记忆体）：记录错误归因与修正建议，晨报生成时引用最近 5 条。从本地 daily-reports/logs/correction-library.md 同步而来，报告中的新修正建议应人工或脚本追加回来 |

## 占位符约定（脚本注入，非 LLM 生成）

提示词文件用 `<<占位符>>` 形式（不用 `{}`，避免与提示词正文中的花括号冲突）：

- `<<DATE>>` 报告日期（YYYY-MM-DD（周X））
- `<<DIGEST>>` 数据底稿（东财接口抓取的行情数据）
- `<<YESTERDAY_REPORT>>`（仅 am）上一交易日的晨报原文，用于"昨日预测多维评判"小节
- `<<TODAY_REPORT>>`（仅 pm）当日晨报原文，用于"晨报预测初步对照"小节
- `<<CORRECTION_LIBRARY>>`（仅 am）修正建议库最近若干条

## 与本地链路的差异（云端数据边界）

- 数据源由 Wind + 中金点睛 换为 东方财富公开接口：指数/美股/港股行情、涨跌家数、行业板块榜、
  主力资金净流入、两融余额可覆盖；**中金研报观点、宏观日历数值、南向资金明细、涨停/炸板/连板情绪
  不在覆盖范围**，提示词已要求这些项目一律标注"（未获取）"严禁编造——这是与本地版报告的主要质量差距所在；
- 本地版由 dsh agent 多步取数，云端为单次 API 调用：底稿由脚本注入，不做工具调用；
- 昨日晨报评判：云端从 `reports/` 目录读取上一份 am 报告注入；无存档时该小节标注"未获取"。

## 加载方式

`generate_report.py` 提供：

```python
load_prompt(name)        # 读取 prompts/{name}.md，失败回退到内置精简版
build_user_prompt(rtype, now, digest)  # 组装完整 user 消息（含上下文注入）
load_system_prompt()     # 读取 prompts/system.md
```

修正建议库位置：`skills/ashare-daily-report/correction-library.md`（云端报告产生的
"修正建议"小节内容，应回填到此文件形成闭环；Streamlit 容器为临时文件系统，持久化需提交回仓库）。

## 版本演进

- v4.2（本地 2026-09-04）：精细预测（中心值+窄区间）+ 比例量化评判 + 自修正闭环 + 港股模块
- v4.2-cloud.1（2026-09-08）：适配东财数据源与单次 API 调用模式，打包进仓库供云端使用
