"""One wrapper for every model call: timeout, retries with backoff, JSON parse, Pydantic validation, one repair pass,
a fallback provider, cost and latency logging. Modes: fake (offline), live, record (live and saved), replay (saved outputs).

Callers never touch the SDK. Tests inject a transport with set_transport() to script garbage, timeouts and 429s.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

from agents.util import strip_fences
from backend.core.config import get_settings
from backend.core.errors import AgentFailure
from backend.core.logging import log

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"
# List prices in dollars per million tokens (input, output). Configuration, not measurement: cost per run uses real token counts.
PRICES = {HAIKU: (1.0, 5.0), SONNET: (3.0, 15.0)}
TIMEOUT_S = 30
RETRIES = 2
REPLAY_FILE = Path(__file__).resolve().parents[1] / "seed" / "fixtures" / "agent_replays.json"


class LLMUnavailable(Exception):
    """A transport-level failure: timeout, 429, 5xx or no key."""


@dataclass
class RawReply:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class LLMResult:
    parsed: BaseModel
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    latency: float = 0.0
    provider: str = "anthropic"
    repaired: bool = False
    replay: bool = False
    notes: list[str] = field(default_factory=list)


Transport = Callable[[str, str, str, float, int], RawReply]
_transport: Transport | None = None


def set_transport(fn: Transport | None) -> None:
    global _transport
    _transport = fn


def cost_of(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICES.get(model, (3.0, 15.0))
    return round((tin * pin + tout * pout) / 1_000_000, 6)


def _anthropic(model: str, system: str, user: str, temperature: float, max_tokens: int) -> RawReply:
    key = get_settings().anthropic_api_key
    if not key:
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT_S, max_retries=0)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return RawReply(text, msg.usage.input_tokens, msg.usage.output_tokens)
    except LLMUnavailable:
        raise
    except Exception as e:  # SDK raises typed errors; every one of them is a transport failure for our purposes
        raise LLMUnavailable(f"{type(e).__name__}: {e}") from e


def _fallback(system: str, user: str, temperature: float, max_tokens: int) -> RawReply:
    s = get_settings()
    if s.llm_fallback_provider != "openai" or not s.llm_fallback_key:
        raise LLMUnavailable("no fallback provider configured")
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {s.llm_fallback_key}"},
            json={"model": "gpt-4o-mini", "temperature": temperature, "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        j = r.json()
        return RawReply(j["choices"][0]["message"]["content"], j["usage"]["prompt_tokens"], j["usage"]["completion_tokens"])
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise LLMUnavailable(f"fallback failed: {e}") from e


def _call(model: str, system: str, user: str, temperature: float, max_tokens: int) -> tuple[RawReply, str]:
    """Primary provider with retries and backoff, then the fallback provider."""
    fail = get_settings().fail_llm
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            if fail == "timeout":
                raise LLMUnavailable("injected timeout")
            if fail == "garbage":
                return RawReply("this is not json at all", 10, 5), "anthropic"
            if fail == "empty":
                return RawReply("", 10, 0), "anthropic"
            if _transport is not None:
                return _transport(model, system, user, temperature, max_tokens), "anthropic"
            return _anthropic(model, system, user, temperature, max_tokens), "anthropic"
        except LLMUnavailable as e:
            last = e
            log().warning("llm attempt failed", extra={"event": "llm_retry", "status": str(attempt)})
            if attempt < RETRIES:
                time.sleep(0 if _transport is not None or fail else 0.5 * (2**attempt))
    try:
        return _fallback(system, user, temperature, max_tokens), "fallback"
    except LLMUnavailable as e:
        raise AgentFailure(f"llm_unavailable: {last}; {e}", code="llm_unavailable") from e


def _replay_load() -> dict:
    return json.loads(REPLAY_FILE.read_text(encoding="utf-8")) if REPLAY_FILE.exists() else {}


def replay_key(agent: str, version: int, inputs: dict) -> str:
    return hashlib.sha1(json.dumps([agent, version, inputs], sort_keys=True, default=str).encode()).hexdigest()


def run(
    *,
    agent: str,
    model: str,
    system: str,
    user: str,
    schema: type[BaseModel],
    temperature: float = 0.0,
    max_tokens: int = 1500,
    prompt_version: int = 1,
    key_inputs: dict | None = None,
) -> LLMResult:
    """Call the model, validate against `schema`, repair once, or raise AgentFailure."""
    mode = get_settings().llm_mode
    rkey = replay_key(agent, prompt_version, key_inputs or {"user": user})
    if mode == "replay":
        rec = _replay_load().get(rkey)
        if rec is None:
            raise AgentFailure("no recorded output for this input", code="replay_miss")
        return LLMResult(schema.model_validate(rec["output"]), model, rec.get("tin", 0), rec.get("tout", 0), rec.get("cost", 0.0), 0.0, "replay", replay=True)
    t0 = time.monotonic()
    raw, provider = _call(model, system, user, temperature, max_tokens)
    tin, tout = raw.tokens_in, raw.tokens_out
    parsed, err = _parse(raw.text, schema)
    repaired = False
    if parsed is None:
        repair_user = f"{user}\n\nYour previous reply was invalid: {err}\nReturn only a JSON object that matches the schema. Previous reply:\n{raw.text[:2000]}"
        raw2, provider = _call(model, system, repair_user, 0.0, max_tokens)
        tin, tout = tin + raw2.tokens_in, tout + raw2.tokens_out
        parsed, err = _parse(raw2.text, schema)
        repaired = True
        if parsed is None:
            raise AgentFailure(f"invalid model output after repair: {err}", code="invalid_output")
    result = LLMResult(parsed, model, tin, tout, cost_of(model, tin, tout), round(time.monotonic() - t0, 2), provider, repaired)
    if mode == "record":
        REPLAY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = _replay_load()
        data[rkey] = {"agent": agent, "output": parsed.model_dump(), "tin": tin, "tout": tout, "cost": result.cost}
        REPLAY_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return result


def _parse(text: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str]:
    if not text or not text.strip():
        return None, "empty reply"
    try:
        return schema.model_validate(json.loads(strip_fences(text))), ""
    except (json.JSONDecodeError, ValidationError) as e:
        return None, str(e)[:400]
