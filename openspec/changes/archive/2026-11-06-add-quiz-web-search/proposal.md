# Proposal

## Why

出题完全依赖 DeepSeek 自身的知识。用户问到较新的产品、版本、政策、数据，或者冷门主题时，模型容易编出过时或错误的事实，题目和标准答案一起错，用户还会按错误答案“学会”。出题前先联网搜一下，把搜到的资料作为参考交给模型，可以明显减少这类错误。

## What Changes

- 后端出题流程在调用模型前增加一步联网搜索：用用户的学习内容作为查询词，通过 Tavily Search API 取若干条网页摘要，清洗、截断后作为“参考资料”放进出题 Prompt。
- Prompt 增加参考资料的使用规则：事实性内容以参考资料为准；参考资料与主题无关或互相矛盾时忽略或只采用确定的部分；参考资料里出现的任何指令都不执行。
- 搜索是**尽力而为**：没配 Key、搜索超时、出错、额度用尽或没有结果时，照旧不带参考资料出题，不向用户报错。
- 每次出题只搜一次。换保守 Prompt 重试时复用同一份搜索结果，不重复消耗额度。
- 新增配置 `TAVILY_API_KEY` 等，写在 `backend/.env`（不进 git）；`.env.example` 只放空占位。
- 对外行为不变：`POST /api/v1/quiz/generate` 的请求和响应结构不变，前端不改，界面上不展示参考来源。

## Capabilities

### New Capabilities
- `quiz-web-search`: 出题前联网检索参考资料，用于约束 AI 出题的事实准确性；涵盖何时检索、检索失败如何降级、参考资料如何进入出题、配置与额度约束。

### Modified Capabilities
（无。现有 specs 为空；出题接口的输入输出契约不变。）

## Impact

- 后端：新增 Tavily 搜索客户端模块；`app/core/config.py` 增加搜索配置；`app/services/quiz_service.py` 在重试循环前插入搜索；`app/llm/quiz_chain.py` 与 `app/prompts/quiz_prompt.py` 增加参考资料变量；`app/api/deps.py` 注入搜索客户端；`.env.example` 增加占位。
- 依赖：不新增包，使用已有的 `httpx` 直接调用 `POST https://api.tavily.com/search`。
- 延迟与成本：出题多一次外部请求（有超时上限）；每次出题消耗 1 个 Tavily credit（basic 搜索），免费额度 1000 次/月。
- 测试：用 `httpx.MockTransport` 模拟 Tavily，离线覆盖成功、超时、错误码、空结果；现有出题测试不配 Key，行为不变。
- 文档：`docs/方案设计文档.md` 的“生成题目”流程与配置说明补充联网检索一步。
