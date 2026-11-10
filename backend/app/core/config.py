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
    # POST /quick-eval requests allowed per IP per 5 minutes.
    eval_rate_limit: int = Field(5, validation_alias="EVAL_RATE_LIMIT")
    dev_fake_provider: bool = Field(False, validation_alias="DEV_FAKE_PROVIDER")
    judge_model: str = Field("gpt-4o-mini", validation_alias="JUDGE_MODEL")
    judge_temperature: float = Field(0.0, validation_alias="JUDGE_TEMPERATURE")
    dev_fake_judge: bool = Field(False, validation_alias="DEV_FAKE_JUDGE")
    # Free-tier hosted models for demos and smoke tests ONLY — free tiers may use
    # prompts for training, so never send customer data through them.
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_base_url: str = Field("https://api.groq.com/openai/v1", validation_alias="GROQ_BASE_URL")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_base_url: str = Field("https://generativelanguage.googleapis.com/v1beta/openai", validation_alias="GEMINI_BASE_URL")
    public_url: str = Field("https://redline-safety.fly.dev", validation_alias="PUBLIC_URL")
    # Seconds to wait between testcases (paces shared-provider rate limits, e.g. Groq TPM).
    eval_pacing_seconds: float = Field(12.0, validation_alias="EVAL_PACING_SECONDS")
    # Deployment mode. "production" (default) = locked down: eval auth required.
    # "demo" = the public hosted demo (open evals, demo banner in the UI).
    # "development" = local hacking/tests.
    redline_env: str = Field("production", validation_alias="REDLINE_ENV", pattern="^(production|demo|development)$")
    # When true, POST /quick-eval requires the admin key or a valid invite token.
    # Unset = derived from REDLINE_ENV (required everywhere except demo).
    require_eval_auth_override: bool | None = Field(default=None, validation_alias="REQUIRE_EVAL_AUTH")
    # Comma-separated hostnames and/or CIDRs that agent_endpoint_url may target even
    # though they are private (self-hosted installs testing internal agents), e.g.
    # "agent.internal,10.20.0.0/16". Cloud metadata addresses are always blocked.
    agent_endpoint_allowlist: str = Field("", validation_alias="AGENT_ENDPOINT_ALLOWLIST")
    # Max testcases a single quick-eval may request.
    max_testcases_per_run: int = Field(200, validation_alias="MAX_TESTCASES_PER_RUN")
    # Optional path to a TOML file overriding the default tier criteria.
    tier_config_path: str | None = Field(default=None, validation_alias="TIER_CONFIG_PATH")
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

    @property
    def require_eval_auth(self) -> bool:
        if self.require_eval_auth_override is not None:
            return self.require_eval_auth_override
        return self.redline_env != "demo"

    @property
    def is_demo(self) -> bool:
        return self.redline_env == "demo"


settings = Settings()
