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
    model_name: str = "glm-5"
    max_tokens: int = 4096      # 全局默认最大输出 token 数（推理模型需设大一些）
    max_retries: int = 3
    timeout: int = 60
    # 是否显式传 thinking extra_body。glm-5 等推理模型默认就开启 thinking，
    # 此开关仅用于对非默认行为的模型显式开启。默认 false（不传 extra_body）。
    enable_thinking: bool = False


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


class KTSettings(BaseSettings):
    """KT (知识追踪) 集成设置。

    mode:
      - "off" (默认): cognitive_diagnosis 走纯 LLM 模拟,不调用 KT
      - "integrated": cognitive_diagnosis 调用本地 kt-runtime-skill 拿真实掌握度,
                       LLM 仅做认知归因
      - "standalone": KT 走 PR #1 原方案 — services/chat-agent 独立服务 + 前端 iframe
                       (此模式下 cognitive_diagnosis 行为同 off)
    """
    mode: Literal["off", "integrated", "standalone"] = "off"
    # kt-runtime-skill 路径,相对于仓库根目录或绝对路径
    skill_path: str = "services/kt-runtime-skill"
    # KT 模型运行设备(cuda:0 / cpu)
    device: str = "cuda:0"
    # 默认预测目标 kp_id 列表,逗号分隔(留空则使用 kt config 默认全部)
    default_targets: str = ""
    # KT 失败时是否降级到纯 LLM
    fallback_to_llm: bool = True


class GraphRecommenderSettings(BaseSettings):
    """Configuration for the standalone heterogeneous graph recommender."""

    enabled: bool = True
    embedding_model_id: str = "BAAI/bge-small-zh-v1.5"
    checkpoint_dir: str = "algorithm/graph_recommender/ckpt"

    model_config = SettingsConfigDict(
        env_prefix="SMART_TUTOR_GRAPH_RECOMMENDER__",
        env_file=".env",
        extra="ignore",
    )


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
    kt: KTSettings = Field(default_factory=KTSettings)
    graph_recommender: GraphRecommenderSettings = Field(default_factory=GraphRecommenderSettings)


# Singleton – reads .env and env vars directly
settings = Settings()
