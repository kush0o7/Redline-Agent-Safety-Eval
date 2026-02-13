from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    project_name: str = "Redline"
    admin_api_key: str = Field(..., validation_alias="ADMIN_API_KEY")
    postgres_url: str = Field(..., validation_alias="POSTGRES_URL")
    redis_url: str = Field(..., validation_alias="REDIS_URL")
    llm_provider: str = Field("openai", validation_alias="LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    aws_region: str | None = Field(default=None, validation_alias="AWS_REGION")
    aws_profile: str | None = Field(default=None, validation_alias="AWS_PROFILE")
    default_model: str = Field("gpt-4o-mini", validation_alias="DEFAULT_MODEL")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    rate_limit_per_minute: int = Field(60, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_burst: int = Field(20, validation_alias="RATE_LIMIT_BURST")
    dev_fake_provider: bool = Field(False, validation_alias="DEV_FAKE_PROVIDER")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
