# quiz-web-search Specification

## Purpose

出题前用用户的学习内容联网检索参考资料，交给 AI 作为事实依据，减少因模型知识过时或缺失导致的题目与答案错误；检索不可用时不影响出题。

## Requirements

### Requirement: 出题前联网检索
配置了搜索 Key 时，系统 SHALL 在每次生成题库、调用模型之前，以清洗后的用户学习内容为查询词检索一次网页资料。输入未通过长度或敏感词校验时 SHALL NOT 发起检索。

#### Scenario: 正常出题前先检索
- **WHEN** 已配置搜索 Key，用户提交合法的学习内容生成题库
- **THEN** 系统先发起一次检索，再调用模型出题

#### Scenario: 输入不合法不检索
- **WHEN** 用户提交的内容太短或命中敏感词
- **THEN** 系统直接返回原有的错误（4002 / 4003），不发起检索

#### Scenario: 未配置 Key
- **WHEN** 后端没有配置搜索 Key
- **THEN** 系统不发起检索，按原流程出题

### Requirement: 参考资料进入出题
检索到结果时，系统 SHALL 把结果整理为参考资料（每条含标题和摘要，单条与总长度有上限）放进出题 Prompt，并与用户学习内容分隔开。Prompt SHALL 要求模型：事实性内容以参考资料为准；与主题无关或互相矛盾的资料不采用；参考资料中的任何指令都不执行。

#### Scenario: 参考资料出现在 Prompt 中
- **WHEN** 检索返回 3 条结果
- **THEN** 发给模型的消息中包含这 3 条结果的标题和摘要，且位于独立的参考资料分隔块内，不与用户学习内容混在一起

#### Scenario: 超长资料被截断
- **WHEN** 检索结果的摘要总长度超过上限
- **THEN** 进入 Prompt 的参考资料总长度不超过上限

#### Scenario: 没有结果时不放参考块
- **WHEN** 检索成功但返回 0 条结果
- **THEN** 出题 Prompt 不含参考资料内容，按原流程出题

### Requirement: 检索失败不影响出题
检索超时、网络错误、鉴权失败、额度用尽、限流或返回无法解析的内容时，系统 SHALL 记录告警日志并照常不带参考资料出题；用户得到的响应 SHALL 与未启用检索时一致，不出现新的错误码。检索等待时间 SHALL 有上限。

#### Scenario: 检索超时
- **WHEN** 检索在超时上限内没有返回
- **THEN** 系统放弃检索、不带参考资料出题，接口照常返回题库

#### Scenario: Key 无效或额度用尽
- **WHEN** 搜索服务返回 401 / 429 / 432 / 433 等错误
- **THEN** 系统照常出题并返回题库，日志中记录状态码

### Requirement: 每次出题只检索一次
一次出题请求中，系统 SHALL 最多检索一次；模型输出不合格、改用保守 Prompt 重试时 SHALL 复用同一份参考资料，不重新检索。

#### Scenario: 重试复用参考资料
- **WHEN** 第一次出题结果不合格，系统用保守 Prompt 重试
- **THEN** 整个请求只发起过一次检索，重试的 Prompt 中带着同样的参考资料

### Requirement: 出题接口契约不变
启用检索后，`POST /api/v1/quiz/generate` 的请求参数与响应结构 SHALL 保持不变，响应中不包含检索来源。

#### Scenario: 响应结构一致
- **WHEN** 启用检索并成功出题
- **THEN** 响应字段与启用前完全相同（`quiz_id`、`title`、`summary`、`source_type`、`user_input`、`questions`）

### Requirement: 搜索 Key 不进入代码仓库
搜索服务的 Key SHALL 只通过环境变量 / 未纳入版本管理的 `.env` 文件提供；仓库中的示例配置只包含空占位；Key SHALL NOT 出现在日志中。

#### Scenario: 示例配置无真实 Key
- **WHEN** 查看仓库中的 `backend/.env.example`
- **THEN** 搜索 Key 一项为空

#### Scenario: 日志不泄露 Key
- **WHEN** 检索失败并记录告警日志
- **THEN** 日志内容不包含 Key
