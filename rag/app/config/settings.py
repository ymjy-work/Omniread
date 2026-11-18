from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bailian_api_key: str = ""
    bailian_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chat_model: str = "qwen3.7-plus"
    embedding_model: str = "qwen3.7-text-embedding"
    embedding_dim: int = 1024
    rerank_model: str = "qwen3-rerank"
    rag_db: str = "./var/rag.db"
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
