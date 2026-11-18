# rag

Python 3.13 + FastAPI + LangChain 的检索增强服务。只有本服务持有百炼 API Key，
gateway 不接触模型。

```bash
uv sync --group dev
cp .env.example .env   # 填入 BAILIAN_API_KEY
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

接口：

- `POST /v1/index`：接收整本章节内容，整体替换该书 chunk。
- `POST /v1/ask`：接收问题、进度与历史，返回答案与引用。
- `GET /v1/health`：健康检查。

模型：`qwen3.7-plus` / `qwen3.7-text-embedding`（1024 维）/ `qwen3-rerank`。
检索与业务规则（区间过滤、引用白名单、拒答）在 `app/rag/` 内实现，不使用 LangChain 的
VectorStore / Retriever / Agent 抽象。提示词由 Qwen4Max 子代理撰写，代码由 Codex + DeepSeek 实现。
