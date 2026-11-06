# 后端（FastAPI + LangChain + DeepSeek + MySQL）

技术方案见 [docs/方案设计文档.md](../docs/方案设计文档.md)，用户系统见 [docs/用户系统方案设计文档.md](../docs/用户系统方案设计文档.md)。需要 Python 3.11+（开发时用 3.13）。

## 数据库（Docker 里的 MySQL 8.4）

本机 3306 被 MySQL 5.7 占用，所以容器映射到 **3307**。开发库 `yhyd`，测试库 `yhyd_test`（pytest 会清空它）。

```bash
# 首次创建（Docker Hub 不通时用国内镜像，拉下来后打成 mysql:8.4）
docker pull docker.m.daocloud.io/library/mysql:8.4 && docker tag docker.m.daocloud.io/library/mysql:8.4 mysql:8.4
docker run -d --name yhyd-mysql --restart unless-stopped -p 3307:3306 \
  -e MYSQL_ROOT_PASSWORD=yhyd_root_2026 -e MYSQL_DATABASE=yhyd \
  -e MYSQL_USER=yhyd -e MYSQL_PASSWORD=yhyd_dev_2026 -e TZ=UTC \
  -v yhyd-mysql-data:/var/lib/mysql mysql:8.4 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_ai_ci
docker exec yhyd-mysql mysql -uroot -pyhyd_root_2026 \
  -e "CREATE DATABASE IF NOT EXISTS yhyd_test; GRANT ALL PRIVILEGES ON yhyd_test.* TO 'yhyd'@'%';"

docker start yhyd-mysql   # 之后每次
```

表结构在 `app/resources/schema.sql`，应用启动时自动执行（`CREATE TABLE IF NOT EXISTS`，幂等），也可以手动 `python -m scripts.init_db`。时间字段一律存 UTC。

库连不上时应用照常启动：出题、报告按匿名模式工作（不落库），`/user/*` 返回 5000。

## 启动

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填写 DEEPSEEK_API_KEY、MYSQL_*、WECHAT_APP_SECRET、JWT_SECRET
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 接口文档：http://localhost:8000/docs
- **只能单 worker 运行**（不要加 `--workers N`，也不要多实例部署）：知识库的向量库是嵌入式 Chroma（数据在 `data/chroma`，只支持单进程写），资料处理任务也在进程内。`--reload` 或重启会中断正在处理的资料，启动时它们会被标为失败并提示重新上传。
- 真机调试时，小程序要访问电脑的局域网 IP（如 `http://192.168.1.10:8000`），所以用 `--host 0.0.0.0` 启动。

## 测试

```bash
pytest                       # 全部单测：LLM 用假模型 / httpx MockTransport，微信登录用假客户端；
                             # 用户系统用例连 yhyd_test 真库（连不上时自动跳过，可用 TEST_MYSQL_* 覆盖）
python -m scripts.smoke_quiz # 真模型冒烟：连续出题 10 次 + 生成 1 份报告，需要 .env 里的 Key
```

## 接口

所有接口统一返回 `{code, message, data}`，`code=0` 表示成功。

| 接口 | 说明 |
| --- | --- |
| `GET /api/v1/health` | 健康检查 |
| `POST /api/v1/quiz/generate` | 生成题库。`user_input`（≤2000 字）、`question_count`（3 / 5 / 10，默认 5）、`difficulty`（mixed / easy / medium / hard）。带 token 时题库存入 `quiz_sessions`。出题前由检索规划 Agent 决定是否联网、是否查当前用户的知识库（见「出题前的检索规划」）；依据知识库资料出的题带 `sources`，此时 `source_type=knowledge_base` |
| `POST /api/v1/report/generate` | 生成复盘报告。传入题目与答题记录，后端重新判题并统计。带 token 且题库是本人出的：用库里的题目判题，先写答题记录并结算经验金币，再生成 AI 复盘并存档（见下） |
| `POST /api/v1/user/login` | 微信登录：`{code}`（wx.login 拿到）→ `{token, user}`。首次登录自动注册 |
| `GET /api/v1/user/profile` | 档案：昵称、头像、经验、金币、已学话数、答对题数、总正确率、本周分钟 |
| `PUT /api/v1/user/profile` | 改昵称（1–20 字，过敏感词）/ 头像地址（https，本期前端不上传） |
| `GET /api/v1/user/quizzes?page=1&page_size=10` | 闯关历史（已完结的话），最近的在前，`page_size` ≤ 50 |
| `GET /api/v1/user/quizzes/{quiz_id}` | 某一话的完整题目、答题记录、奖励、复盘报告（AI 失败时为 null）、第几话 |

### 知识库

都要求登录。数据库不可用或没配 `SILICONFLOW_API_KEY` 时，知识库接口一律返回 5000（HTTP 503），其余接口不受影响。

| 接口 | 说明 |
| --- | --- |
| `GET /api/v1/knowledge-bases` | 我的知识库，最近更新的在前：`{items, total, document_total, document_limit}`，每项含资料总数与可出题资料数 |
| `POST /api/v1/knowledge-bases` | 建库：`{name}`（1–20 字，过敏感词），每人最多 10 个 |
| `GET /api/v1/knowledge-bases/{kb_id}` | 详情：`{knowledge_base, documents}`，资料按上传时间新到旧，含状态 `processing / ready / failed`、失败原因、页数（仅 PDF）、字数 |
| `PUT /api/v1/knowledge-bases/{kb_id}` | 改名：`{name}`，规则同建库 |
| `DELETE /api/v1/knowledge-bases/{kb_id}` | 删库及其全部资料的文本与向量；已出的题、答题记录、报告、错题保留 |
| `POST /api/v1/knowledge-bases/{kb_id}/documents` | 上传资料（multipart，字段 `file`）：PDF（文字版）/ .docx / .txt / .md，单个 ≤ 20 MB，每人所有库合计 ≤ 50 份。校验通过立即返回 `processing`，后台解析 → 切块 → 向量化 |
| `DELETE /api/v1/knowledge-bases/{kb_id}/documents/{document_id}` | 删资料及其文本与向量；处理中的也能删 |
| `POST /api/v1/knowledge-bases/{kb_id}/quiz` | 用知识库出题：`document_ids`（可选，空 = 全部）、`focus`（可选，≤200 字）、`question_count`、`difficulty` → 与文本出题同结构的题库，`source_type=knowledge_base`，每题带 `sources` 出处。填了重点时 Agent 在所选资料里检索片段；Agent 联网查到的只作背景，不作出题依据、不进出处 |

- 文本以 MySQL（`kb_documents`、`kb_chunks`）为准，Chroma 只存向量与过滤用的 metadata；检索时按 MySQL 里的资料列表过滤，向量删除失败留下的孤儿向量不会被用到。
- 上传的原始文件只在处理期间临时存放（`data/uploads`），处理结束即删除，启动时清空。
- **隐私**：上传资料提取出的全文、以及带重点出题时填写的重点（和检索规划 Agent 写的知识库查询词），会发送给硅基流动（`BAAI/bge-m3`）做向量化。不配 Key 就完全不发送。联网查询词的说明见「出题前的检索规划」。
- 上传大小由后端自己计数判断（不信任 `Content-Length`），但请求体会先被完整接收；生产环境请在反向代理上也限制请求体大小（如 nginx `client_max_body_size 21m`）。

鉴权：`Authorization: Bearer <JWT>`（HS256，默认 30 天）。`/user/*`（登录除外）必须登录；出题、报告是**可选鉴权**，没有或无效 token 时按匿名处理、照常返回，只是不落库。

经验金币：每答对一题 +10 经验、+5 金币（与前端、原型一致）。同一用户同一话只结算一次（`answer_records` 上 `user_id + quiz_id` 唯一），重复提交、AI 复盘失败后重试都不会重复加。

微信登录：调 `jscode2session`，需要 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`。`APP_ENV=dev` 且没配 Secret 时启用模拟登录（所有设备都登录成同一个开发用户），生产环境不会启用。

错误码：

| code | 含义 |
| --- | --- |
| 4000 | 请求参数不合法（HTTP 422） |
| 4001 | 题库生成失败（已自动重试 2 次） |
| 4002 | 输入太短（不足 4 个字） |
| 4003 | 内容不合规 |
| 4004 | 复盘报告生成失败 |
| 4010 | 未登录或登录已失效（HTTP 401），前端会静默重登一次再重发 |
| 4011 | 微信登录失败 |
| 4012 | 昵称不合规 |
| 4020 | 文件类型不支持（只支持 PDF / .docx / .txt / .md，按扩展名和内容共同判断） |
| 4021 | 文件大小不合法（空文件或超过 20 MB） |
| 4022 | 超出数量上限（知识库 10 个 / 资料 50 份） |
| 4023 | 没有可出题的资料（所选资料都还没处理完或处理失败） |
| 4040 | 记录不存在（或不是自己的） |
| 5000 | 服务内部错误（HTTP 500）；用户系统 / 知识库不可用时为 HTTP 503 |

题型配比：3 题 = 单选 1 / 多选 1 / 判断 1；5 题 = 3 / 1 / 1；10 题 = 6 / 2 / 2。判断题选项固定为 `A=对`、`B=错`。

报告里的 `accuracy`、`knowledge_mastery`、`mastered_points`（≥80%）、`weak_points`（<60%）由后端统计得出；`three_line_summary`、`advice`、`share_quote` 由 AI 生成。

## 知识库配置

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `SILICONFLOW_API_KEY` | 空 | 硅基流动 Key（https://cloud.siliconflow.cn），为空则知识库功能关闭。只放 `.env` |
| `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | OpenAI 兼容接口 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 1024 维（`EMBEDDING_DIMENSIONS`）；硅基流动目前免费 |
| `EMBEDDING_BATCH_SIZE` | `32` | 单次请求条数，硅基流动 `/embeddings` 的 `input` 数组上限为 32 |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | |
| `CHROMA_PATH` | `data/chroma` | 相对后端工作目录；`backend/data/` 不纳入版本管理。换模型会换一个集合 |
| `KB_UPLOAD_DIR` | `data/uploads` | 上传临时文件 |
| `KB_MAX_BASES` / `KB_MAX_DOCUMENTS` | `10` / `50` | 每人知识库数 / 所有库合计资料数 |
| `KB_MAX_FILE_BYTES` | `20971520` | 20 MB |
| `KB_MAX_CHARS` | `300000` | 单份资料提取出的字数上限 |
| `KB_CHUNK_CHARS` / `KB_CHUNK_OVERLAP` | `500` / `80` | 切块长度与重叠（字符）；PDF 的块不跨页 |
| `KB_RETRIEVE_TOP_K` / `KB_MATERIAL_MAX_CHARS` | `12` / `6000` | 带重点出题时检索的片段数 / 交给模型的材料总长 |
| `KB_PROCESS_CONCURRENCY` | `2` | 同时处理的资料数 |

## 出题前的检索规划（Agent）

出题有两个外部数据源：联网检索（Tavily，配了 `TAVILY_API_KEY` 才有）和用户自己的知识库。出题前先跑一步检索规划：DeepSeek 用工具调用（`tool_choice=auto`）决定查知识库、联网、两个都查还是都不查，查询词也由它写，可以查多次。规划只负责“查什么”，出题、校验、重试、出处校验沿用原链路；重试复用同一份检索结果，不重新规划。

| 入口 | 知识库检索 | 联网检索 | 结果怎么用 |
| --- | --- | --- | --- |
| 首页 `POST /quiz/generate` | 已登录、知识库可用且有 `ready` 资料时可用，范围是该用户全部知识库 | 配了搜索 Key 时可用 | 联网结果 → `<reference>`（事实依据，规则不变）；知识库片段 → `<materials>`，模型按需引用，用到的题带出处，其余题 `sources` 为空 |
| 知识库 `POST /knowledge-bases/{kb_id}/quiz` | 填了重点时可用，范围是本次所选的 `ready` 资料；Agent 可改写、拆分查询词，片段去重合并 | 配了搜索 Key 且 `AGENT_WEB_IN_KB_QUIZ=true` 时可用 | 联网结果 → `<background>`，只用于理解资料，不作出题依据、不编号、不进出处；每题仍必须有资料出处 |

- 没有任何可用数据源（例如未登录且没配搜索 Key）时跳过规划，直接出题。输入没通过长度 / 敏感词校验时不规划。
- 上限（一次请求）：模型调用 3 轮、工具执行 4 次、其中联网 2 次，整个规划 20 秒。超出次数的调用不执行；达到任一次数上限即结束规划，用已有结果出题。第 3 轮返回的工具调用不执行。
- 不合法的工具调用（未知工具、参数不是合法 JSON、缺 `query`）忽略，不计次数；工具执行失败（Embedding / Tavily 报错）回“检索失败”给 Agent，计入次数，不算规划失败。
- **降级**：规划时模型报错或超时 → 按固定规则出题，用户无感知：首页以学习内容联网检索一次（配了 Key 时）、不查知识库；知识库出题有重点时以重点向量检索一次（失败再均匀抽取）、没重点均匀抽取，不联网。Agent 没查知识库或没查到片段时，知识库出题同样以重点检索一次。
- **总开关**：`.env` 设 `AGENT_RETRIEVAL_ENABLED=false` 即全部回到固定规则，无需改代码、无数据变更。
- 日志：每次出题一条 `retrieval plan entry=home tools=[kb,web] calls=kb:1,web:1 results=kb:6,web:5 rounds=2 1.8s fallback=-`；失败时 WARNING，`fallback=timeout|model_error`；没跑规划时记 `skipped fallback=disabled|no_tools`。不记学习内容、重点、查询词、正文和 Key。
- 延迟与成本：每次出题多 1–3 次短的 DeepSeek 调用（低温度、`max_tokens=800`）。常识主题 Agent 通常不联网，Tavily 用量会比“每次出题固定检索 1 次”少；但单次请求最多可联网 2 次（2 credits，basic）。带重点的知识库出题可能多 1–2 次 Embedding 调用。
- **隐私**：联网查询词由 Agent 写，截到 100 字、过敏感词，Prompt 要求不写资料原文、人名、公司内部信息，只写通用主题词——但这是 Prompt 约束，**不能完全保证**。首页出题时 Agent 能看到该用户自己的资料片段，可能把片段内容带进联网查询词发给 Tavily。资料需要严格保密的部署：知识库出题设 `AGENT_WEB_IN_KB_QUIZ=false`，或整体关闭 `AGENT_RETRIEVAL_ENABLED`。

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `AGENT_RETRIEVAL_ENABLED` | `true` | 检索规划总开关；关掉即两个入口都走固定规则 |
| `AGENT_WEB_IN_KB_QUIZ` | `true` | 知识库出题时是否允许 Agent 联网查背景 |
| `AGENT_MAX_ROUNDS` | `3` | 规划的模型调用轮数 |
| `AGENT_MAX_TOOL_CALLS` | `4` | 一次请求的工具执行总次数 |
| `AGENT_MAX_WEB_SEARCHES` | `2` | 其中联网次数，控制 Tavily 用量 |
| `AGENT_KB_TOP_K` | `6` | 每次知识库检索取的片段数 |
| `AGENT_TIMEOUT_SECONDS` | `20.0` | 整个规划的总超时 |
| `AGENT_TEMPERATURE` / `AGENT_MAX_TOKENS` | `0.1` / `800` | 规划模型参数 |
| `AGENT_WEB_QUERY_MAX_CHARS` / `AGENT_KB_QUERY_MAX_CHARS` | `100` / `200` | Agent 写的查询词长度上限 |

## DeepSeek 接入要点（已实测）

- 模型 `deepseek-flash` 默认开启思考模式，而思考模式不支持命名 `tool_choice`，结构化输出会报 400。因此默认 `DEEPSEEK_THINKING=disabled`。
- `with_structured_output(..., method="function_calling")`：`ChatOpenAI` 默认的 `json_schema` 方式 DeepSeek 不支持。
- `ChatOpenAI` 会把 `max_tokens` 改名为 `max_completion_tokens`，所以 `max_tokens` 通过 `extra_body` 透传。
- 显式设置 `use_responses_api=False`，走 Chat Completions。
- 检索规划用 `bind_tools(..., tool_choice="auto")` 的普通工具调用，在关闭思考模式下可用。

## 目录

```text
app/
  agent/          出题前的检索规划 Agent：工具参数模型（tools）、规划循环与上限（retrieval_planner）
  api/            路由与依赖注入（deps.py）
  core/           配置、日志、错误码与异常处理、JWT 鉴权（auth.py）、MySQL 连接池（db.py）
  repositories/   SQL（不用 ORM）：users、quiz_sessions / answer_records / reports、知识库（kb_repository）
  rag/            知识库基础组件：文档解析与切块（parsing）、硅基流动 Embedding（embedding）、Chroma 封装（vector_store）
  llm/            模型工厂、出题链、报告链、结构化输出 Schema
  prompts/        版本化 Prompt（quiz_prompt_v1 / v2、kb_quiz_prompt_v1 / v2、report_prompt_v1、retrieval_agent_v1）
  services/       出题、校验、评分、报告服务；用户（登录 / 档案）、闯关记录（落库 / 历史）、微信 code2Session；
                  知识库管理（kb_service）、资料后台处理（kb_ingest）、知识库出题（kb_quiz_service）、
                  取材与出处（kb_materials）、Agent 的知识库检索执行器（kb_retrieval）
  utils/          文本清洗、敏感词过滤、ID
  resources/      敏感词词库（种子词库，上线前请替换为专业词库并接入微信 msgSecCheck）、schema.sql
scripts/          真模型冒烟脚本、init_db（手动建表）
tests/            pytest
```
