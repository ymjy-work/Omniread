"""FastAPI 应用工厂。

catalog 端点默认按环境变量装配读库实现；三条 rag 路径默认按环境变量装配真实依赖（见
`build_retrieval_service` / `build_query_runner`）：`retrieval-only` 走检索链，`query` /
`query-stream` 走完整问答链。缺凭据时不阻止启动，端点以 503 显式暴露未接线状态。
依赖全部经端口注入，测试替换实现不需要改路由。

provider 由 `OMNIREAD_ANSWER_PROVIDER` / `OMNIREAD_RETRIEVAL_PROVIDER` 选择，默认走真实
适配器；取 `fake` 时装配确定性假 provider（联调/测试专用，启动日志会明确打出）。这条
开关不是降级路径：真实适配器缺凭据时构造失败，端点 503，不会因为缺 key 静默换成 fake。

入口命令（工厂模式，导入时不读环境）：`uv run uvicorn omniread.api.app:create_app --factory`
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import sessionmaker

from omniread.api.deps import attach_request_id
from omniread.api.errors import (
    handle_rag_error,
    handle_request_validation_error,
    handle_unexpected_error,
)
from omniread.api.routers import catalog as catalog_routes
from omniread.api.routers import health as health_routes
from omniread.api.routers import rag as rag_routes
from omniread.application.ports import (
    CatalogRepository,
    ImageStorage,
    QueryRunner,
    RetrievalService,
)
from omniread.application.query_service import AnsweringRunner, UnimplementedQueryRunner
from omniread.config import Settings
from omniread.domain.errors import RagError
from omniread.infrastructure.db.catalog import EmptyCatalogRepository, PgCatalogRepository
from omniread.infrastructure.db.context import PgContextSource
from omniread.infrastructure.db.session import create_engine_from_env
from omniread.infrastructure.objectstore.local import LocalFileSystemImageStorage
from omniread.infrastructure.objectstore.minio_storage import build_minio_storage
from omniread.infrastructure.providers.ali import AliEmbeddingAdapter, AliRerankAdapter
from omniread.infrastructure.providers.base import ChatModel, EmbeddingModel, RerankModel
from omniread.infrastructure.providers.fake import (
    FakeChatModel,
    FakeEmbeddingModel,
    FakeRerankModel,
    FaultyChatModel,
)
from omniread.infrastructure.providers.glm import GlmChatAdapter
from omniread.logging_config import configure_logging
from omniread.pipelines.retrieval.dense import PgVectorDenseIndex
from omniread.pipelines.retrieval.pipeline import RetrievalPipeline
from omniread.pipelines.retrieval.store import PgChunkStore

logger = logging.getLogger(__name__)

API_PREFIX = "/internal/v1"

# create_app 的 retrieval / query_runner 默认值：按环境变量装配真实依赖。
# 显式传 None 表示「本次应用不接该依赖」，端点回 503——测试与控制台用它保持路径确定。
RETRIEVAL_AUTO: Literal["auto"] = "auto"
QUERY_RUNNER_AUTO: Literal["auto"] = "auto"


def build_image_storage(settings: Settings) -> ImageStorage:
    if settings.image_storage_backend == "minio":
        return build_minio_storage(settings)
    return LocalFileSystemImageStorage(settings.image_local_root)


def build_catalog_repository() -> CatalogRepository:
    """按环境变量装配目录读库；缺库凭据时返回空实现（catalog 端点仍可解析）。

    与检索链同样构造期不连库：Engine 懒连接，缺 `POSTGRES_PASSWORD` 时构造即失败。
    """
    try:
        session_factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
        return PgCatalogRepository(session_factory)
    except Exception as exc:
        logger.warning("目录读库未接线，catalog 端点返回空结构：%s", exc)
        return EmptyCatalogRepository()


def build_embedding_model(settings: Settings) -> EmbeddingModel:
    if settings.retrieval_provider == "fake":
        return FakeEmbeddingModel()
    return AliEmbeddingAdapter()


def build_rerank_model(settings: Settings) -> RerankModel:
    if settings.retrieval_provider == "fake":
        return FakeRerankModel()
    return AliRerankAdapter()


def build_chat_model(settings: Settings) -> ChatModel:
    """按配置装配回答模型。

    `answer_provider=fake` 是联调/测试专用路径：装配确定性假 provider，并把这件事以
    WARNING 打进启动日志，避免有人误以为线上在跑真模型。默认值 `glm` 缺 `GLM_API_KEY`
    时构造即失败，由调用方转成「未接线」——不静默换成假 provider。
    """
    if settings.answer_provider == "fake":
        logger.warning(
            "联调/测试模式：回答链使用确定性假 provider（OMNIREAD_ANSWER_PROVIDER=fake），"
            "不会调用 GLM；此开关不要用于线上"
        )
        if settings.fake_answer_fault == "provider_error":
            return FaultyChatModel("provider_error")
        if settings.fake_answer_fault == "timeout":
            return FaultyChatModel("timeout")
        return FakeChatModel(delay_ms=settings.fake_answer_delay_ms)
    return GlmChatAdapter()


def build_retrieval_service(settings: Settings) -> RetrievalService | None:
    """按环境变量装配检索链；缺库凭据或 provider 凭据时返回 None。

    构造期不发网络请求也不连库：SQLAlchemy 的 Engine 懒连接，百炼适配器只在构造时读
    `DASHSCOPE_API_KEY`。凭据缺失不阻止服务启动——端点以 503 显式暴露未接线状态，
    比让进程起不来更便于运维定位。失败原因只写日志，不打印凭据。
    """
    try:
        session_factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
        if settings.retrieval_provider == "fake":
            logger.warning(
                "联调/测试模式：检索链使用确定性假 embedding/rerank"
                "（OMNIREAD_RETRIEVAL_PROVIDER=fake），不会调用百炼；"
                "dense 以假查询向量对真库向量，排名无语义，仅用于链路联调"
            )
        return RetrievalPipeline(
            store=PgChunkStore(session_factory),
            dense=PgVectorDenseIndex(session_factory),
            embedder=build_embedding_model(settings),
            reranker=build_rerank_model(settings),
        )
    except Exception as exc:
        logger.warning("检索链未接线：%s", exc)
        return None


def build_query_runner(
    retrieval: RetrievalService | None, settings: Settings
) -> QueryRunner | None:
    """在检索链之上装配问答链；缺库凭据、检索链未接线或缺 provider 凭据时返回 None。

    与检索链同样在构造期不连库、不发网络请求：回答适配器只在构造时读凭据，
    `PgContextSource` 持有的 Engine 懒连接。返回 None 时端点以 503 暴露未接线状态。
    """
    if retrieval is None:
        return None
    try:
        session_factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
        return AnsweringRunner(
            retrieval=retrieval,
            context=PgContextSource(session_factory),
            chat=build_chat_model(settings),
            answer_provider=settings.answer_provider,
        )
    except Exception as exc:
        logger.warning("回答链未接线：%s", exc)
        return None


def create_app(
    settings: Settings | None = None,
    *,
    catalog: CatalogRepository | None = None,
    image_storage: ImageStorage | None = None,
    query_runner: QueryRunner | Literal["auto"] | None = QUERY_RUNNER_AUTO,
    retrieval: RetrievalService | Literal["auto"] | None = RETRIEVAL_AUTO,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Omniread RAG 内部 API",
        version="1.0.0",
        # 只暴露契约里的 8 条路径；交互式文档与 openapi.json 不在契约内，一律关闭。
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.catalog = catalog if catalog is not None else build_catalog_repository()
    app.state.image_storage = image_storage or build_image_storage(settings)
    retrieval_service = (
        build_retrieval_service(settings) if retrieval == RETRIEVAL_AUTO else retrieval
    )
    app.state.retrieval = retrieval_service
    if query_runner == QUERY_RUNNER_AUTO:
        app.state.query_runner = (
            build_query_runner(retrieval_service, settings) or UnimplementedQueryRunner()
        )
    else:
        app.state.query_runner = query_runner or UnimplementedQueryRunner()

    app.middleware("http")(attach_request_id)

    app.add_exception_handler(RagError, handle_rag_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)

    # 路由模块以 `_routes` 别名导入：`catalog` / `rag` 同名参数与依赖已在作用域内。
    app.include_router(health_routes.router, prefix=API_PREFIX)
    app.include_router(catalog_routes.router, prefix=API_PREFIX)
    app.include_router(rag_routes.router, prefix=API_PREFIX)

    logger.info(
        "服务已装配 service=%s log_level=%s prefix=%s",
        settings.service_name,
        settings.log_level,
        API_PREFIX,
    )
    return app


__all__ = ["API_PREFIX", "build_image_storage", "create_app"]
