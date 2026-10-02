"""Shared result type, text helpers and a polite HTTP fetch used by every check."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

# Statuses a check can report.
AVAILABLE = "AVAILABLE"
SOLD_OUT = "SOLD_OUT"
OK = "OK"
STRUCTURE_BROKEN = "STRUCTURE_BROKEN"
BLOCKED = "BLOCKED"
UNREADABLE = "UNREADABLE"
ERROR = "ERROR"

FAILURE_STATUSES = {STRUCTURE_BROKEN, BLOCKED, UNREADABLE, ERROR}

# Markers of bot challenges. We only detect these to log and skip, never to get around them.
CHALLENGE_MARKERS = (
    "cf-chl",
    "challenge-platform",
    "just a moment...",
    "attention required! | cloudflare",
    "px-captcha",
    "perimeterx",
    "datadome",
    "g-recaptcha",
    "h-captcha",
    "are you a robot",
    "verify you are human",
)


@dataclass
class CheckResult:
    target: str
    status: str
    detail: str = ""
    items: list = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.status in FAILURE_STATUSES


class FetchBlocked(Exception):
    pass


def normalize(text: str) -> str:
    """Lowercase, unify dashes and quotes, and collapse whitespace."""
    text = text.replace(" ", " ")
    text = re.sub(r"[‐-―−]", "-", text)
    text = text.replace("’", "'")
    return re.sub(r"\s+", " ", text).strip().lower()


def looks_like_challenge(html: str) -> bool:
    low = html[:200_000].lower()
    return any(marker in low for marker in CHALLENGE_MARKERS)


def fetch(url: str, user_agent: str, timeout: float, accept: str = "text/html,*/*") -> requests.Response:
    """One GET, no retries. Raises FetchBlocked on 403/429. Other HTTP errors raise normally."""
    resp = requests.get(
        url,
        headers={"User-Agent": user_agent, "Accept": accept},
        timeout=timeout,
    )
    if resp.status_code in (403, 429):
        raise FetchBlocked(f"HTTP {resp.status_code}")
    resp.raise_for_status()
    return resp


def run_safely(target: str, func, *args, **kwargs) -> CheckResult:
    """Run a check and turn any exception into a failed CheckResult."""
    try:
        return func(*args, **kwargs)
    except FetchBlocked as exc:
        return CheckResult(target, BLOCKED, f"blocked: {exc}")
    except requests.RequestException as exc:
        return CheckResult(target, ERROR, f"request failed: {type(exc).__name__}: {exc}"[:300])
    except Exception as exc:  # a bug in a parser must not stop the other targets
        return CheckResult(target, ERROR, f"unexpected error: {type(exc).__name__}: {exc}"[:300])
