"""Application configuration using pydantic-settings.

All settings can be overridden via environment variables with the prefix SMART_TUTOR_.
For nested settings, use double underscore: SMART_TUTOR_DATABASE__URL

Priority (highest → lowest):
  1. Environment variables (SMART_TUTOR_LLM__API_KEY=...)
  2. .env file values
  3. Python field defaults below
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Sub-settings
# ---------------------------------------------------------------------------

class DatabaseSettings(BaseSettings):
    # 支持两种 URL：
    #   SQLite 本地开发: sqlite+aiosqlite:///./smart_tutor.db
    #   MySQL 生产:      mysql+aiomysql://tutor:tutor123@localhost:3306/smart_tutor
    url: str = "sqlite+aiosqlite:///./smart_tutor.db"
    echo: bool = False


class LLMSettings(BaseSettings):
    provider: Literal["openai", "vllm", "glm"] = "glm"
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    api_key: str = "sk-xxxxxxxxxxxxxxxx"
    model_name: str = "glm-4-flash"
    max_tokens: int = 4096      # 全局默认最大输出 token 数（推理模型需设大一些）
    max_retries: int = 3
    timeout: int = 60


class AppSettings(BaseSettings):
    debug: bool = True
    secret_key: str = "change-me-in-production-32chars!!"
    jwt_expiration: int = 86400  # seconds
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class LangGraphSettings(BaseSettings):
    checkpoint_type: Literal["postgres", "memory"] = "memory"
    checkpoint_postgres_url: str = "postgresql+psycopg://tutor:tutor123@localhost:5432/smart_tutor_checkpoint"


class TraceSettings(BaseSettings):
    enabled: bool = True
    log_path: str = ""  # 空=自动使用 backend/logs/trace.log
    max_bytes: int = 10 * 1024 * 1024  # 10 MB
    backup_count: int = 5


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """Root settings that aggregates all sub-groups."""

    model_config = SettingsConfigDict(
        env_prefix="SMART_TUTOR_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    app: AppSettings = Field(default_factory=AppSettings)
    langgraph: LangGraphSettings = Field(default_factory=LangGraphSettings)
    trace: TraceSettings = Field(default_factory=TraceSettings)


# Singleton – reads .env and env vars directly
settings = Settings()
