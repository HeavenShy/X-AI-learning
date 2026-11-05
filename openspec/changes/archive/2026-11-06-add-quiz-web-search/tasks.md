# Tasks

## 1. 配置

- [x] 1.1 在 `app/core/config.py` 增加 `tavily_*` 与 `web_reference_*` 配置及 `web_search_enabled` 属性（见 design 决策 3）；`backend/.env.example` 增加 `TAVILY_API_KEY=`（空值）及注释；验证：新增配置测试断言默认关闭、配 Key 后开启，`.env.example` 中 Key 为空
- [x] 1.2 在本地 `backend/.env` 写入用户提供的 `TAVILY_API_KEY`；验证：`git check-ignore backend/.env` 命中，`git status` 不出现 `.env`

## 2. 搜索客户端

- [x] 2.1 新增 `app/services/web_search.py`：`SearchSnippet`、`WebSearcher`、`WebSearchError`、`TavilySearcher`（决策 2 的请求体、Bearer 鉴权、超时、错误转换）；验证：新增 `tests/test_web_search.py`，用 `httpx.MockTransport` 断言请求 URL / 头 / 请求体，并覆盖 200 正常解析、401 / 429 / 432 / 500、超时、非 JSON、缺 `results` 均抛 `WebSearchError`，且异常信息与日志不含 Key
- [x] 2.2 实现纯函数 `build_reference`；验证：`tests/test_web_search.py` 覆盖空列表返回空串、单条截断、总长度上限、尖括号被去除、命中敏感词的条目被丢弃、编号格式

## 3. Prompt 与出题链

- [x] 3.1 `app/prompts/quiz_prompt.py`：v1、v2 system 增加参考资料规则，human 模板增加 `{reference_block}`，`quiz_prompt_variables` / `build_quiz_messages` 增加 `reference` 参数；验证：`tests/test_prompt_contract.py` 新增用例——有资料时出现 `<reference>` 块且在 `<material>` 之后、无资料时不出现、资料中的 `{}` 原样保留不报错；原有用例全部通过
- [x] 3.2 `app/llm/quiz_chain.py`：`QuizGenerator` Protocol 与 `LangChainQuizGenerator.generate` 增加 `reference: str = ""` 并传入变量；验证：`tests/test_quiz_chain.py` 新增用例断言带资料时发给 DeepSeek 的消息包含资料内容

## 4. 出题服务与注入

- [x] 4.1 `QuizService` 增加可选 `searcher`，在输入校验通过后、重试循环前检索一次并构建参考资料，任何异常降级为空资料（决策 5）；验证：`tests/test_quiz_service.py` 新增用例——无 searcher 时行为不变、检索结果传入 generator、检索抛错 / 超时仍成功出题、输入太短或命中敏感词时不调用 searcher、重试 3 次只检索 1 次且每次 reference 相同；更新原有对 generator 调用参数的断言
- [x] 4.2 `app/main.py` lifespan 创建 / 关闭 `app.state.web_searcher`；`app/api/deps.py` 拆出缓存的 `get_quiz_generator` 与每请求的 `get_quiz_service`；验证：`tests/test_quiz_api.py` 全部通过，并新增用例断言未配 Key 时 `app.state.web_searcher is None`、响应字段与原来一致
- [x] 4.3 `docs/方案设计文档.md` 的“流程一：生成题目”与配置说明补充联网检索步骤、降级策略、额度与隐私说明；验证：文档中的配置名与 `config.py` 一致；`cd backend && pytest` 全部通过

## 5. 真实环境验证

- [x] 5.1 用真实 Key 跑 `python -m scripts.smoke_quiz`（必要时给脚本加一个打印“检索条数 / 耗时”的开关），选一个较新的主题（如近期发布的产品版本）对比开 / 关检索的题目；验证：开启时日志显示检索成功且条数 > 0，出题成功；把 Key 临时改错再跑一次，日志显示 401 降级且出题仍成功
- [x] 5.2 在微信开发者工具中走一遍首页出题 → 闯关；验证：出题成功、界面无变化、耗时可接受（记录一次实际耗时）

## Workflow follow-up

- 实现与验证完成后运行 `/opsx:archive` 归档本次改动。
- 上线前在 Tavily 控制台重新生成开发 Key（当前 Key 已出现在对话记录中）。
