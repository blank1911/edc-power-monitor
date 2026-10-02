"""ntfy.sh push notifications."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests

URGENT, HIGH, DEFAULT, LOW, MIN = 5, 4, 3, 2, 1


@dataclass
class Alert:
    title: str
    body: str
    priority: int = DEFAULT
    tags: list = field(default_factory=list)
    click: str = ""


def _ascii(text: str) -> str:
    # HTTP header values must be latin-1; keep titles plain ASCII.
    return text.encode("ascii", "replace").decode("ascii")


def send(alert: Alert, user_agent: str, timeout: float, dry_run: bool = False) -> bool:
    """Send one alert. Returns True on success. Never raises."""
    if dry_run:
        print(f"[dry-run] would send p{alert.priority}: {alert.title} | {alert.body}"
              + (f" | click={alert.click}" if alert.click else ""))
        return True
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print(f"[notify] NTFY_TOPIC is not set, cannot send: {alert.title}")
        return False
    server = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    headers = {
        "User-Agent": user_agent,
        "Title": _ascii(alert.title),
        "Priority": str(alert.priority),
    }
    if alert.tags:
        headers["Tags"] = ",".join(alert.tags)
    if alert.click:
        headers["Click"] = alert.click
    try:
        resp = requests.post(f"{server}/{topic}", data=alert.body.encode("utf-8"), headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[notify] failed to send '{alert.title}': {type(exc).__name__}: {exc}")
        return False
    print(f"[notify] sent p{alert.priority}: {alert.title}")
    return True
