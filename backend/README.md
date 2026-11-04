# 后端（FastAPI）

技术栈见根目录《方案设计文档.md》第 5.2 / 6 节。需要 Python 3.11+。

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填写 DEEPSEEK_API_KEY
uvicorn app.main:app --reload --port 8000
```

- 接口文档：http://localhost:8000/docs
- 健康检查：`GET /api/v1/health`
- 测试：`pytest`

`quiz/generate`、`report/generate` 已定义请求/响应模型，业务逻辑暂时返回 `5001 尚未实现`，待接入 `app/llm/` 下的 LangChain 链。
