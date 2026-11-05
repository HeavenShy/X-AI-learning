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
| `POST /api/v1/quiz/generate` | 生成题库。`user_input`（≤2000 字）、`question_count`（3 / 5 / 10，默认 5）、`difficulty`（mixed / easy / medium / hard）。带 token 时题库存入 `quiz_sessions` |
| `POST /api/v1/report/generate` | 生成复盘报告。传入题目与答题记录，后端重新判题并统计。带 token 且题库是本人出的：用库里的题目判题，先写答题记录并结算经验金币，再生成 AI 复盘并存档（见下） |
| `POST /api/v1/user/login` | 微信登录：`{code}`（wx.login 拿到）→ `{token, user}`。首次登录自动注册 |
| `GET /api/v1/user/profile` | 档案：昵称、头像、经验、金币、已学话数、答对题数、总正确率、本周分钟 |
| `PUT /api/v1/user/profile` | 改昵称（1–20 字，过敏感词）/ 头像地址（https，本期前端不上传） |
| `GET /api/v1/user/quizzes?page=1&page_size=10` | 闯关历史（已完结的话），最近的在前，`page_size` ≤ 50 |
| `GET /api/v1/user/quizzes/{quiz_id}` | 某一话的完整题目、答题记录、奖励、复盘报告（AI 失败时为 null）、第几话 |

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
| 4040 | 记录不存在（或不是自己的） |
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
  core/           配置、日志、错误码与异常处理、JWT 鉴权（auth.py）、MySQL 连接池（db.py）
  repositories/   SQL（不用 ORM）：users、quiz_sessions / answer_records / reports
  llm/            模型工厂、出题链、报告链、结构化输出 Schema
  prompts/        版本化 Prompt（quiz_prompt_v1 / v2、report_prompt_v1）
  services/       出题、校验、评分、报告服务；用户（登录 / 档案）、闯关记录（落库 / 历史）、微信 code2Session
  utils/          文本清洗、敏感词过滤、ID
  resources/      敏感词词库（种子词库，上线前请替换为专业词库并接入微信 msgSecCheck）、schema.sql
scripts/          真模型冒烟脚本、init_db（手动建表）
tests/            pytest
```
