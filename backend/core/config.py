from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    demo_mode: bool = True
    base_url: str = "http://localhost:8000"
    database_url: str = "postgresql://cadence:cadence@localhost:5433/cadence"
    jwt_secret: str = DEV_SECRET
    webhook_shared_secret: str = DEV_SECRET
    mcp_token: str = DEV_SECRET
    cors_origins: str = "http://localhost:8000"
    cors_origin_regex: str = r"https://([a-z0-9-]+\.)*dronahq\.com"

    llm_mode: str = "fake"
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    llm_model_strong: str = ""
    llm_model_fast: str = ""
    llm_fallback_provider: str = ""
    llm_fallback_key: str = ""
    llm_fallback_model: str = ""
    embeddings_api_key: str = ""
    fail_llm: str = ""
    fail_embeddings: bool = False
    fail_channel: str = ""
    fake_latency_ms: int = 400

    dronahq_researcher_webhook_url: str = ""
    dronahq_responder_webhook_url: str = ""
    dronahq_api_key: str = ""
    dronahq_voice_agent_id: str = ""
    dronahq_voice_call_url: str = ""
    agent_provider_researcher: str = "direct"
    agent_provider_responder: str = "direct"
    agent_provider_caller: str = "direct"

    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    gmail_sender: str = ""
    seed_inbox_base: str = "helix.sandbox@gmail.com"
    smtp_host: str = ""
    smtp_user: str = ""
    smtp_app_password: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    channel_mode_email: str = "sandbox"
    channel_mode_sms: str = "sandbox"
    channel_mode_linkedin: str = "sandbox"
    channel_mode_voice: str = "sandbox"
    allowed_recipients: str = "gmail.com,helix.demo"

    worker_campaign_id: str = ""
    embedded_worker: bool = False

    @model_validator(mode="after")
    def production_needs_secrets(self):
        if self.app_env == "production":
            missing = [
                k
                for k in ("jwt_secret", "webhook_shared_secret", "mcp_token")
                if getattr(self, k) == DEV_SECRET or len(getattr(self, k)) < 32
            ]
            if missing:
                raise ValueError(f"Set {', '.join(m.upper() for m in missing)} (32+ random characters) in production")
        return self

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_list(self) -> list[str]:
        return [o.strip().lower() for o in self.allowed_recipients.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
