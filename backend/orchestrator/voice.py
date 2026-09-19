"""Voice calls. The DronaHQ Voice agent places live calls (see dronahq.py). Sandbox mode plays the scripted outcome through the same recording path."""

from backend.core.db import Db


def place_call(db: Db, e: dict, *, sandbox: bool) -> str:
    from backend.orchestrator.replies import record_call

    return record_call(db, e, sandbox=sandbox)
