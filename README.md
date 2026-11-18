# Omniread

不剧透的轻小说 RAG 阅读助手：读到哪，聊到哪。

## 三层

| 目录 | 技术 | 端口 |
| --- | --- | --- |
| `web/` | Vue 3 + TypeScript + Pinia + Vue Router | 5173 |
| `gateway/` | Spring Boot 4.1.2 + MyBatis + SQLite | 8080 |
| `rag/` | Python 3.13 + FastAPI + LangChain | 8000 |

架构、数据归属与层间契约见 `.agent/docs/Omniread架构.md`；语料与 Golden 评测集在
`《不时轻声地以俄语遮羞的邻座艾莉同学》/`。

## 本地启动

```bash
# rag
cd rag && cp .env.example .env   # 填 BAILIAN_API_KEY
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# gateway
cd gateway && ./mvnw spring-boot:run

# web
cd web && npm install && npm run dev
```

gateway 只调用本机 rag；模型 key 只在 `rag/.env` 中。
