# Python RAG 服务。
#
# 只装运行依赖（no-dev）：测试与静态检查在 CI / 开发机跑，不进生产镜像。
# 库与对象存储都在 AWS（RDS + S3），容器本身无状态，不需要挂卷。

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# 依赖层单独复制：只改源码时这一层命中缓存。
COPY services/rag/pyproject.toml services/rag/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/rag ./
RUN uv sync --frozen --no-dev

# AWS RDS 的公共根证书包：`sslmode=verify-full` 要靠它认 RDS 的证书链。
# 这是公开的 CA 证书，不是凭据；打进镜像而不是挂宿主文件，部署时少一步。
COPY infra/certs/global-bundle.pem /app/certs/global-bundle.pem

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

EXPOSE 8000
CMD ["uvicorn", "omniread.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
