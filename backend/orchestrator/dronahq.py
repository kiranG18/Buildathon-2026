"""DronaHQ agent provider. Filled in with the webhook client when DronaHQ is connected; until then every agent runs on the direct provider."""

from backend.core.config import get_settings


def enabled(agent: str) -> bool:
    s = get_settings()
    provider = {"Researcher": s.agent_provider_researcher, "Responder": s.agent_provider_responder, "Caller": s.agent_provider_caller}.get(agent, "direct")
    url = {"Researcher": s.dronahq_researcher_webhook_url, "Responder": s.dronahq_responder_webhook_url}.get(agent, s.dronahq_voice_agent_id)
    return provider == "dronahq" and bool(url)


def sweep_awaiting_outcome(db) -> None:
    """Placeholder until the DronaHQ Voice adapter is connected: no call is ever left awaiting an outcome in sandbox mode."""
    return None
