"""Live channel adapters: Gmail API (SMTP fallback) for email and Twilio for SMS. LinkedIn is rep-assisted: agents write and queue the note, a person sends it from their own account.

Every adapter refuses recipients outside ALLOWED_RECIPIENTS, in production too. Adapters register themselves only when their credentials exist,
so a channel without credentials sends nothing and its messages wear the SANDBOX badge.
"""

import base64
import hashlib
import hmac
import smtplib
import time
import uuid
from email.message import EmailMessage

import httpx

from backend.channels.base import REGISTRY, Capabilities, OutboundMessage, SendResult, register
from backend.core import clock
from backend.core.config import get_settings
from backend.core.db import Db
from backend.core.errors import ChannelError

_transport: httpx.BaseTransport | None = None


def set_transport(t: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = t


def _client(timeout: float = 10.0) -> httpx.Client:
    return httpx.Client(transport=_transport, timeout=timeout)


def is_allowed(address: str) -> bool:
    """True when ALLOWED_RECIPIENTS lists the address. Entries are full addresses, domains or phone numbers."""
    a = address.strip().lower()
    domain = a.rsplit("@", 1)[-1] if "@" in a else ""
    base = a.split("+", 1)[0] + "@" + domain if "+" in a.split("@", 1)[0] and domain else a
    digits = "".join(ch for ch in a if ch.isdigit())
    return any(
        entry in (a, base) or (domain and (domain == entry or domain.endswith("." + entry))) or (digits and "".join(ch for ch in entry if ch.isdigit()) == digits)
        for entry in get_settings().allowed_list
    )


def enforce_allowed(address: str) -> None:
    if not is_allowed(address):
        raise ChannelError("Recipient is not on ALLOWED_RECIPIENTS", code="recipient_not_allowed")


def _maybe_fail(channel: str) -> None:
    if get_settings().fail_channel == channel:
        raise ChannelError(f"{channel} send failed (FAIL_CHANNEL is set)", code="channel_down")


class GmailAdapter:
    name = "email"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, sender: str):
        self.client_id, self.client_secret, self.refresh_token, self.sender = client_id, client_secret, refresh_token, sender
        self._token: tuple[str, float] | None = None

    def capabilities(self) -> Capabilities:
        return Capabilities(None, False, True)

    def _access_token(self) -> str:
        if self._token and self._token[1] > time.time() + 30:
            return self._token[0]
        with _client() as c:
            r = c.post("https://oauth2.googleapis.com/token", data={"client_id": self.client_id, "client_secret": self.client_secret, "refresh_token": self.refresh_token, "grant_type": "refresh_token"})
        if r.status_code != 200:
            raise ChannelError(f"Gmail token refresh failed: {r.status_code}", code="gmail_auth")
        j = r.json()
        self._token = (j["access_token"], time.time() + int(j.get("expires_in", 3000)))
        return self._token[0]

    def send(self, msg: OutboundMessage) -> SendResult:
        _maybe_fail("email")
        enforce_allowed(msg.to)
        m = EmailMessage()
        rfc_id = f"<{uuid.uuid4().hex}@cadence.helix.demo>"
        m["To"], m["From"], m["Subject"], m["Message-ID"] = msg.to, self.sender, msg.subject or "(no subject)", rfc_id
        if msg.in_reply_to:
            m["In-Reply-To"] = m["References"] = msg.in_reply_to
        m.set_content(msg.body)
        raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
        with _client() as c:
            r = c.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", headers={"Authorization": f"Bearer {self._access_token()}"}, json={"raw": raw})
        if r.status_code >= 400:
            raise ChannelError(f"Gmail send failed: {r.status_code}", code="gmail_send")
        gmail_id = r.json().get("id")
        return SendResult(external_id=gmail_id, rfc_message_id=self._assigned_message_id(gmail_id) or rfc_id)

    def _assigned_message_id(self, gmail_id: str | None) -> str | None:
        """Gmail replaces the Message-ID we set, and replies quote its own, so read the one it assigned."""
        if not gmail_id:
            return None
        with _client() as c:
            r = c.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{gmail_id}", headers={"Authorization": f"Bearer {self._access_token()}"},
                      params={"format": "metadata", "metadataHeaders": "Message-ID"})
        if r.status_code >= 400:
            return None
        return next((h["value"] for h in r.json().get("payload", {}).get("headers", []) if h["name"].lower() == "message-id"), None)

    def poll_inbound(self, since) -> list[dict]:
        after = int(since.timestamp()) if since else int(time.time()) - 3600
        with _client(15) as c:
            h = {"Authorization": f"Bearer {self._access_token()}"}
            listing = c.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", headers=h, params={"q": f"in:inbox after:{after}", "maxResults": 20})
            if listing.status_code >= 400:
                raise ChannelError(f"Gmail poll failed: {listing.status_code}", code="gmail_poll")
            out = []
            for ref in listing.json().get("messages", []):
                full = c.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{ref['id']}", headers=h, params={"format": "full"})
                if full.status_code >= 400:
                    continue
                j = full.json()
                hdr = {x["name"].lower(): x["value"] for x in j["payload"].get("headers", [])}
                out.append({"external_id": j["id"], "rfc_id": hdr.get("message-id"), "in_reply_to": hdr.get("in-reply-to"), "references": hdr.get("references", ""),
                            "sender": hdr.get("from", ""), "subject": hdr.get("subject", ""), "body": _plain_body(j["payload"]) or j.get("snippet", "")})
            return out

    def test(self) -> None:
        self._access_token()


def _plain_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode(errors="replace").split("\nOn ")[0].strip()
    for part in payload.get("parts", []) or []:
        found = _plain_body(part)
        if found:
            return found
    return ""


class SmtpAdapter:
    """Fallback when Gmail OAuth fails: an app password over SMTP. Inbound is not polled on this path."""

    name = "email"

    def __init__(self, host: str, user: str, password: str):
        self.host, self.user, self.password = host, user, password

    def capabilities(self) -> Capabilities:
        return Capabilities(None, False, True)

    def send(self, msg: OutboundMessage) -> SendResult:
        _maybe_fail("email")
        enforce_allowed(msg.to)
        m = EmailMessage()
        rfc_id = f"<{uuid.uuid4().hex}@cadence.helix.demo>"
        m["To"], m["From"], m["Subject"], m["Message-ID"] = msg.to, self.user, msg.subject or "(no subject)", rfc_id
        m.set_content(msg.body)
        try:
            with smtplib.SMTP_SSL(self.host, 465, timeout=10) as s:
                s.login(self.user, self.password)
                s.send_message(m)
        except (smtplib.SMTPException, OSError) as e:
            raise ChannelError(f"SMTP send failed: {type(e).__name__}", code="smtp_send") from e
        return SendResult(rfc_message_id=rfc_id)

    def poll_inbound(self, since) -> list[dict]:
        return []

    def test(self) -> None:
        with smtplib.SMTP_SSL(self.host, 465, timeout=10) as s:
            s.login(self.user, self.password)


class TwilioAdapter:
    name = "sms"

    def __init__(self, sid: str, token: str, from_number: str):
        self.sid, self.token, self.from_number = sid, token, from_number

    def capabilities(self) -> Capabilities:
        return Capabilities(160, True, False)

    def send(self, msg: OutboundMessage) -> SendResult:
        _maybe_fail("sms")
        enforce_allowed(msg.to)
        with _client() as c:
            r = c.post(f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json", auth=(self.sid, self.token), data={"To": msg.to, "From": self.from_number, "Body": msg.body})
        if r.status_code >= 400:
            try:
                twilio_code = r.json().get("code")
            except ValueError:
                twilio_code = None
            raise ChannelError(f"Twilio rejected the message: {r.status_code}" + (f", error {twilio_code}" if twilio_code else ""), code="twilio_send")
        return SendResult(external_id=r.json().get("sid"))

    def poll_inbound(self, since) -> list[dict]:
        return []

    def test(self) -> None:
        with _client() as c:
            r = c.get(f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}.json", auth=(self.sid, self.token))
        if r.status_code >= 400:
            raise ChannelError(f"Twilio auth failed: {r.status_code}", code="twilio_auth")


class LinkedInAssisted:
    """LinkedIn has no API for messaging prospects and automating an account breaks its terms. The rep sends the note by hand
    and confirms it on the approval card, so this adapter sends nothing and only makes the channel available in live mode."""

    name = "linkedin"

    def capabilities(self) -> Capabilities:
        return Capabilities(300, False, False)

    def send(self, msg: OutboundMessage) -> SendResult:
        return SendResult()

    def poll_inbound(self, since) -> list[dict]:
        return []


def twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()).decode()


def register_configured() -> list[str]:
    """Register the adapters whose credentials exist. Called at start-up by the API and the worker."""
    s = get_settings()
    REGISTRY.clear()
    if s.gmail_client_id and s.gmail_client_secret and s.gmail_refresh_token and s.gmail_sender:
        register(GmailAdapter(s.gmail_client_id, s.gmail_client_secret, s.gmail_refresh_token, s.gmail_sender))
    elif s.smtp_host and s.smtp_user and s.smtp_app_password:
        register(SmtpAdapter(s.smtp_host, s.smtp_user, s.smtp_app_password))
    if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
        register(TwilioAdapter(s.twilio_account_sid, s.twilio_auth_token, s.twilio_from_number))
    register(LinkedInAssisted())
    return sorted(REGISTRY)


def sync_integrations(db: Db) -> None:
    """Make the integration rows say what is actually configured. A service without credentials is sandbox only and never shows as live."""
    s = get_settings()
    can_live = {
        "gmail": "email" in REGISTRY,
        "twilio": "sms" in REGISTRY,
        "voice": bool(s.dronahq_voice_agent_id and s.dronahq_voice_call_url),
        "agents": bool(s.dronahq_researcher_webhook_url or s.dronahq_responder_webhook_url),
        "embed": bool(s.embeddings_api_key),
        "llm": bool({"anthropic": s.anthropic_api_key, "gemini": s.gemini_api_key, "groq": s.groq_api_key}.get(s.llm_provider)),
        "linkedin": True,
    }
    follows_config = {"agents": can_live["agents"], "embed": can_live["embed"], "llm": can_live["llm"] and s.llm_mode == "live"}
    for key, ok in can_live.items():
        if not ok:
            db.x("update integrations set can_live = false, mode = 'sandbox', status = 'ok', err = null, last_check = %s where key = %s", (clock.now(), key))
        elif key in follows_config:
            db.x("update integrations set can_live = true, mode = %s where key = %s", ("live" if follows_config[key] else "sandbox", key))
        else:
            db.x("update integrations set can_live = true where key = %s", (key,))
