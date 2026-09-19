from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from backend.channels.adapters import twilio_signature
from backend.core.config import get_settings
from backend.core.db import Db
from backend.core.errors import Forbidden
from backend.core.security import db_dep, secret_ok
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
