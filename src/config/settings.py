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

    # Application
    log_level: str = "INFO"


settings = Settings()
