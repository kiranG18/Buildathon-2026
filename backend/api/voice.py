from fastapi import APIRouter, Depends

from agents.models import CallOutcome
from backend.core.db import Db
from backend.core.security import db_dep, webhook_guard
from backend.orchestrator import voice

router = APIRouter()


class OutcomeBody(CallOutcome):
    enrollment_id: str


@router.get("/voice/briefing/{enrollment_id}", dependencies=[Depends(webhook_guard)])
def briefing(enrollment_id: str, db: Db = Depends(db_dep)) -> dict:
    """DronaHQ pre-call webhook: everything the voice agent may say, fetched as the call starts."""
    return voice.briefing(db, enrollment_id)


@router.post("/voice/outcome", dependencies=[Depends(webhook_guard)])
def outcome(body: OutcomeBody, db: Db = Depends(db_dep)) -> dict:
    """DronaHQ post-call webhook: transcript, recording and disposition."""
    return voice.ingest_outcome(db, body.enrollment_id, body.model_dump())
