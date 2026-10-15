from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration and settings loaded from environment or .env."""

    APP_NAME: str = "Self-Healing Agentic Text-to-SQL & BI Analytics Engine"
    APP_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # Database settings
    DB_PATH: str = "ecommerce.db"
    SEED_ON_STARTUP: bool = True

    # Google Gemini API
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"

    # Agent Limits & Guardrails
    MAX_SELF_HEAL_ATTEMPTS: int = 3
    DEFAULT_QUERY_LIMIT: int = 100
    MAX_QUERY_LIMIT: int = 500

    # AST Security Guardrails
    FORBIDDEN_TABLES: List[str] = [
        "admin_secrets",
        "api_keys",
        "audit_logs_internal",
        "system_config",
    ]
    FORBIDDEN_COLUMNS: List[str] = [
        "password_hash",
        "credit_card",
        "cvv",
        "secret_key",
        "ssn",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
