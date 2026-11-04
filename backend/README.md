# 后端（FastAPI + LangChain + DeepSeek）

技术方案见 [docs/方案设计文档.md](../docs/方案设计文档.md)。需要 Python 3.11+（开发时用 3.13）。

## 启动

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填写 DEEPSEEK_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 接口文档：http://localhost:8000/docs
- 真机调试时，小程序要访问电脑的局域网 IP（如 `http://192.168.1.10:8000`），所以用 `--host 0.0.0.0` 启动。

## 测试

```bash
pytest                       # 全部离线单测（LLM 用假模型 / httpx MockTransport）
python -m scripts.smoke_quiz # 真模型冒烟：连续出题 10 次 + 生成 1 份报告，需要 .env 里的 Key
```

## 接口

所有接口统一返回 `{code, message, data}`，`code=0` 表示成功。

| 接口 | 说明 |
| --- | --- |
| `GET /api/v1/health` | 健康检查 |
| `POST /api/v1/quiz/generate` | 生成题库。`user_input`（≤2000 字）、`question_count`（3 / 5 / 10，默认 5）、`difficulty`（mixed / easy / medium / hard） |
| `POST /api/v1/report/generate` | 生成复盘报告。传入题目与答题记录，后端重新判题并统计 |

错误码：

| code | 含义 |
| --- | --- |
| 4000 | 请求参数不合法（HTTP 422） |
| 4001 | 题库生成失败（已自动重试 2 次） |
| 4002 | 输入太短（不足 4 个字） |
| 4003 | 内容不合规 |
| 4004 | 复盘报告生成失败 |
| 5000 | 服务内部错误（HTTP 500） |

题型配比：3 题 = 单选 1 / 多选 1 / 判断 1；5 题 = 3 / 1 / 1；10 题 = 6 / 2 / 2。判断题选项固定为 `A=对`、`B=错`。

报告里的 `accuracy`、`knowledge_mastery`、`mastered_points`（≥80%）、`weak_points`（<60%）由后端统计得出；`three_line_summary`、`advice`、`share_quote` 由 AI 生成。

## DeepSeek 接入要点（已实测）

- 模型 `deepseek-flash` 默认开启思考模式，而思考模式不支持命名 `tool_choice`，结构化输出会报 400。因此默认 `DEEPSEEK_THINKING=disabled`。
- `with_structured_output(..., method="function_calling")`：`ChatOpenAI` 默认的 `json_schema` 方式 DeepSeek 不支持。
- `ChatOpenAI` 会把 `max_tokens` 改名为 `max_completion_tokens`，所以 `max_tokens` 通过 `extra_body` 透传。
- 显式设置 `use_responses_api=False`，走 Chat Completions。

## 目录

```text
app/
  api/            路由与依赖注入（deps.py）
  core/           配置、日志、错误码与异常处理
  llm/            模型工厂、出题链、报告链、结构化输出 Schema
  prompts/        版本化 Prompt（quiz_prompt_v1 / v2、report_prompt_v1）
  services/       出题、校验、评分、报告服务
  utils/          文本清洗、敏感词过滤、ID
  resources/      敏感词词库（种子词库，上线前请替换为专业词库并接入微信 msgSecCheck）
scripts/          真模型冒烟脚本
tests/            pytest
```
