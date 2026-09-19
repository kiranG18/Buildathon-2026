"""Print which features the current environment enables and stop with a clear message when a required variable is missing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import get_settings  # noqa: E402


def main() -> int:
    try:
        s = get_settings()
    except ValueError as e:
        print("Configuration error:", e)
        return 1
    rows = [
        ("Database", bool(s.database_url)),
        ("Live LLM (Sonnet 5, Haiku 4.5)", s.llm_mode in ("live", "record") and bool(s.anthropic_api_key)),
        ("Hosted embeddings", bool(s.embeddings_api_key)),
        ("DronaHQ Researcher", bool(s.dronahq_researcher_webhook_url) and s.agent_provider_researcher == "dronahq"),
        ("DronaHQ Responder", bool(s.dronahq_responder_webhook_url) and s.agent_provider_responder == "dronahq"),
        ("DronaHQ Voice", bool(s.dronahq_voice_agent_id and s.dronahq_voice_call_url)),
        ("Gmail (live email)", all([s.gmail_client_id, s.gmail_client_secret, s.gmail_refresh_token, s.gmail_sender])),
        ("SMTP fallback", all([s.smtp_host, s.smtp_user, s.smtp_app_password])),
        ("Twilio SMS", all([s.twilio_account_sid, s.twilio_auth_token, s.twilio_from_number])),
    ]
    print(f"APP_ENV={s.app_env} LLM_MODE={s.llm_mode} DEMO_MODE={s.demo_mode}")
    for name, on in rows:
        print(f"  {'on ' if on else 'off'}  {name}")
    print("Features marked off run in sandbox or on the direct provider.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
