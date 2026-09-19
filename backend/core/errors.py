class CadenceError(Exception):
    status = 400
    code = "error"

    def __init__(self, message: str, code: str | None = None, status: int | None = None, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status
        self.extra = extra or {}


class NotFound(CadenceError):
    status = 404
    code = "not_found"


class Forbidden(CadenceError):
    status = 403
    code = "forbidden"


class Unauthorized(CadenceError):
    status = 401
    code = "unauthorized"


class StateConflict(CadenceError):
    status = 409
    code = "state_conflict"


class GateBlocked(CadenceError):
    """The policy gate refused an action. code carries the reason code."""

    status = 409

    def __init__(self, reason: str, message: str = "", decision: str = "block", detail: dict | None = None):
        super().__init__(message or reason, code=reason)
        self.decision = decision
        self.detail = detail or {}


class AgentFailure(CadenceError):
    status = 502
    code = "agent_failure"


class ChannelError(CadenceError):
    status = 502
    code = "channel_error"


class ConflictDeferred(CadenceError):
    status = 409
    code = "claimed_by_other_campaign"
