from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from backend.channels.adapters import twilio_signature
from backend.core.config import get_settings
from backend.core.db import Db
from backend.core.errors import Forbidden
from backend.core.security import db_dep, secret_ok
from backend.integrations.calendly import verify_signature
from backend.orchestrator import replies

router = APIRouter()


@router.post("/webhooks/twilio/sms")
async def twilio_sms(request: Request, db: Db = Depends(db_dep)) -> Response:
    """Inbound SMS. The X-Twilio-Signature header proves the request came from Twilio."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    s = get_settings()
    url = s.base_url.rstrip("/") + urlparse(str(request.url)).path
    if not secret_ok(request.headers.get("x-twilio-signature"), twilio_signature(s.twilio_auth_token, url, form)):
        raise Forbidden("Bad Twilio signature", code="bad_signature")
    digits = "".join(ch for ch in form.get("From", "") if ch.isdigit())
    row = db.q1(
        """select e.id from enrollments e join prospects p on p.id = e.prospect_id
           where regexp_replace(p.phone, '[^0-9]', '', 'g') = %s
           order by (select max(m.created_at) from messages m where m.enrollment_id = e.id and m.channel = 'sms' and m.direction = 'out') desc nulls last,
                    (select max(m.created_at) from messages m where m.enrollment_id = e.id) desc nulls last, e.created_at desc limit 1""", (digits,))
    if row:
        from backend.orchestrator.repo import enrollment

        replies.ingest_reply(db, enrollment(db, row["id"]), "sms", form.get("Body", ""), external_id=form.get("MessageSid"))
    return Response("<Response/>", media_type="application/xml")


@router.post("/webhooks/calendly")
async def calendly_webhook(request: Request, db: Db = Depends(db_dep)) -> dict:
    """Invitee booked or canceled a real slot. The Calendly-Webhook-Signature header proves the request came from Calendly."""
    body = await request.body()
    s = get_settings()
    if not verify_signature(body, request.headers.get("calendly-webhook-signature"), s.calendly_webhook_signing_key):
        raise Forbidden("Bad Calendly signature", code="bad_signature")
    data = await request.json()
    if data.get("event") != "invitee.created":
        return {"ok": True, "ignored": data.get("event")}
    p = data.get("payload", {})
    email = p.get("email", "")
    start_time = p.get("scheduled_event", {}).get("start_time")
    if not email or not start_time:
        return {"ok": True, "ignored": "missing email or start_time"}
    row = db.q1(
        """select e.id from enrollments e join prospects p on p.id = e.prospect_id where lower(p.email) = lower(%s)
           and e.state not in ('rejected', 'opted_out', 'stopped')
           order by (select count(*) from messages m where m.enrollment_id = e.id and m.direction = 'out') desc, e.created_at desc limit 1""",
        (email,),
    )
    if not row:
        return {"ok": True, "ignored": "no matching enrollment"}
    from datetime import datetime

    from agents.util import f_dt
    from backend.orchestrator.repo import enrollment

    e = enrollment(db, row["id"])
    t_ms = int(datetime.fromisoformat(start_time.replace("Z", "+00:00")).timestamp() * 1000)
    if e["state"] != "meeting":
        replies.book_meeting(db, e, {"t": t_ms, "label": f_dt(t_ms)}, "Calendly")
    return {"ok": True}
