import re
from datetime import UTC, datetime, timedelta

DAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DAY_MS = 86_400_000


def dt(ms: float) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def f_t(ms: float) -> str:
    d = dt(ms)
    return f"{d.hour:02d}:{d.minute:02d}"


def f_d(ms: float) -> str:
    d = dt(ms)
    return f"{DAYS[(d.weekday() + 1) % 7]} {d.day} {MON[d.month - 1]}"


def f_dt(ms: float) -> str:
    return f"{f_d(ms)}, {f_t(ms)}"


def slug(s: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))


def js_hash(s: str) -> int:
    """The prototype's string hash: h = h * 31 + code, wrapped to a signed 32-bit int, then abs."""
    h = 7
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return abs(h)


def slots_for(now_ms: float) -> list[dict]:
    """Two real open Calendly slots when CALENDLY_MODE=live; otherwise two deterministic fake slots
    starting two days out, weekdays only, on different days. A Calendly outage falls back to fake."""
    from backend.core.config import get_settings
    from backend.integrations import calendly

    if get_settings().calendly_mode == "live":
        try:
            return calendly.available_times(now_ms)
        except calendly.CalendlyUnavailable:
            pass
    start = dt(now_ms) + timedelta(days=2)
    out: list[dict] = []
    for i in range(12):
        if len(out) >= 2:
            break
        day = datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(days=i)
        x = day.replace(hour=15 if out else 11)
        wd = (x.weekday() + 1) % 7
        t = int(x.timestamp() * 1000)
        if 0 < wd < 6 and (not out or t // DAY_MS != out[0]["t"] // DAY_MS):
            out.append({"t": t, "label": f_dt(t)})
    return out


def first(name: str) -> str:
    return name.split(" ")[0]


def words(s: str) -> int:
    return len(s.split())


def strip_fences(text: str) -> str:
    """Pull a JSON object out of a model reply that wraps it in markdown fences or prose."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", t, re.S)
    if m:
        return m.group(1)
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b > a:
        return t[a : b + 1]
    return t
