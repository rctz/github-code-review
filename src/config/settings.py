from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Providers
    litellm_api_key: str = ""
    litellm_api_base: str = ""
    openrouter_api_key: str = ""
    azure_api_key: str = ""

    # GitHub
    github_token: str = ""

    # GitHub App
    github_app_id: str = ""
    github_app_private_key: str = ""  # PEM content or path to .pem file

    # Webhook
    github_webhook_secret: str = ""
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000

    # Application
    log_level: str = "INFO"
    max_concurrent_llm_calls: int = 5
    llm_rate_limit: int = 20
    llm_rate_period_seconds: int = 60


settings = Settings()
