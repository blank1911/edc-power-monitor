"""ntfy.sh push notifications."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests

URGENT, HIGH, DEFAULT, LOW, MIN = 5, 4, 3, 2, 1
TOPIC_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


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
    if topic.startswith(("http://", "https://")):
        # Accept a full topic URL pasted into the secret.
        server, _, topic = topic.rstrip("/").rpartition("/")
    if not TOPIC_RE.fullmatch(topic):
        print("[notify] NTFY_TOPIC is not a valid ntfy topic: use 1 to 64 letters, digits, - or _ (no spaces)")
        return False
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
