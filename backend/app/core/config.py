from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


_WEAK_ADMIN_KEYS = {"change-me", "changeme", "change", "admin", "password", "secret", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "Redline"
    admin_api_key: str = Field(..., validation_alias="ADMIN_API_KEY")
    postgres_url: str = Field(..., validation_alias="POSTGRES_URL")
    redis_url: str = Field(..., validation_alias="REDIS_URL")
    llm_provider: str = Field("openai", validation_alias="LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    aws_region: str | None = Field(default=None, validation_alias="AWS_REGION")
    aws_profile: str | None = Field(default=None, validation_alias="AWS_PROFILE")
    ollama_base_url: str = Field("http://host.docker.internal:11434", validation_alias="OLLAMA_BASE_URL")
    default_model: str = Field("gpt-4o-mini", validation_alias="DEFAULT_MODEL")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    rate_limit_per_minute: int = Field(60, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_burst: int = Field(20, validation_alias="RATE_LIMIT_BURST")
    dev_fake_provider: bool = Field(False, validation_alias="DEV_FAKE_PROVIDER")
    judge_model: str = Field("gpt-4o-mini", validation_alias="JUDGE_MODEL")
    judge_temperature: float = Field(0.0, validation_alias="JUDGE_TEMPERATURE")
    dev_fake_judge: bool = Field(False, validation_alias="DEV_FAKE_JUDGE")
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    public_url: str = Field("https://redline-safety.fly.dev", validation_alias="PUBLIC_URL")
    # Seconds to wait between testcases (paces shared-provider rate limits, e.g. Groq TPM).
    eval_pacing_seconds: float = Field(12.0, validation_alias="EVAL_PACING_SECONDS")
    # When true, POST /quick-eval requires the admin key or a valid invite token.
    require_eval_auth: bool = Field(False, validation_alias="REQUIRE_EVAL_AUTH")
    # Max seconds a single eval run may take before the worker kills it.
    job_timeout_seconds: int = Field(3600, validation_alias="JOB_TIMEOUT_SECONDS")
    # Max queued jobs before /quick-eval returns 503.
    max_queued_jobs: int = Field(20, validation_alias="MAX_QUEUED_JOBS")
    # Fernet key for encrypting agent_endpoint_key at rest (base64url, 32 bytes).
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # If unset, keys are stored plaintext (backwards-compatible — set this for production).
    field_encryption_key: str | None = Field(default=None, validation_alias="FIELD_ENCRYPTION_KEY")

    @model_validator(mode="after")
    def _reject_weak_admin_key(self) -> "Settings":
        # Fail closed: refuse to boot unless a real admin key is set. Tests/dev that
        # use the fake provider still need a non-default key (set in conftest.py).
        if self.admin_api_key.strip().lower() in _WEAK_ADMIN_KEYS:
            raise ValueError(
                "ADMIN_API_KEY is unset or a well-known default. Set a strong, unique "
                "value (e.g. `openssl rand -hex 32`) before starting Redline."
            )
        if len(self.admin_api_key) < 16:
            raise ValueError("ADMIN_API_KEY must be at least 16 characters.")
        return self


settings = Settings()
