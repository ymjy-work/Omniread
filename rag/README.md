# rag

Python 3.13 + FastAPI + LangChain 的检索增强服务。模型 Key 只在 rag 进程内使用，
gateway 不接触平台 Key，也不持有免费渠道 Key。

```bash
uv sync --group dev
cp .env.example .env   # 填入 BAILIAN_API_KEY
cp channels.example.json channels.json   # 可选：配置免费渠道
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

接口：

- `POST /v1/index`：接收整本章节内容，整体替换该书 chunk。
- `POST /v1/ask`：接收问题、进度、历史与模型选择，返回答案、引用与 token 用量。
- `GET /v1/health`：健康检查。

`/v1/ask` 支持三种模式：

- `auto`：按 `channels.json` 的 `priority` 尝试免费渠道；全部失败时回退平台百炼 Key。
- `platform`：固定使用百炼，`model` 必填，Key 取 `BAILIAN_API_KEY`。
- `byok`：`provider`、`model`、`api_key` 必填；Key 只在本请求内使用，不落库、不写日志。

提供商固定为百炼、OpenAI、DeepSeek、硅基流动四个 OpenAI 兼容端点。免费渠道文件
`channels.json` 已在 `.gitignore` 中忽略，模板见 `channels.example.json`。

检索与业务规则（区间过滤、引用白名单、拒答）在 `app/rag/` 内实现，不使用 LangChain 的
VectorStore / Retriever / Agent 抽象。提示词由 Qwen4Max 子代理撰写，代码由 Codex + DeepSeek 实现。