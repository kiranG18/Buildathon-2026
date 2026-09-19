"""The Channel interface. Sandbox sends write to the database only. Live adapters register themselves here."""

from dataclasses import dataclass
from typing import Protocol

from backend.core.db import Db


@dataclass
class Capabilities:
    max_chars: int | None
    needs_consent: bool
    supports_threading: bool


@dataclass
class OutboundMessage:
    message_id: str
    channel: str
    to: str
    subject: str | None
    body: str
    in_reply_to: str | None = None


@dataclass
class SendResult:
    external_id: str | None = None
    rfc_message_id: str | None = None


class Channel(Protocol):
    name: str

    def capabilities(self) -> Capabilities: ...

    def send(self, msg: OutboundMessage) -> SendResult: ...

    def poll_inbound(self, since) -> list[dict]: ...


REGISTRY: dict[str, Channel] = {}


def register(channel: Channel) -> None:
    REGISTRY[channel.name] = channel


def send_message(db: Db, msg: dict, p: dict) -> None:
    """Hand a stored outbound message to its adapter. Sandbox mode and channels without a live adapter send nothing."""
    if msg["mode"] != "live":
        return
    adapter = REGISTRY.get(msg["channel"])
    if adapter is None:
        return
    to = {"email": p["email"], "sms": p["phone"], "linkedin": p["linkedin_url"], "voice": p["phone"]}[msg["channel"]]
    result = adapter.send(OutboundMessage(msg["id"], msg["channel"], to, msg["subject"], msg["body"]))
    db.x("update messages set external_id = %s, rfc_message_id = %s where id = %s", (result.external_id, result.rfc_message_id, msg["id"]))
