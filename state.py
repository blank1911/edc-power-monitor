"""state.json: what the monitor remembers between runs.

Only facts that change on real events are stored (no "last run" timestamp), so the workflow
commits state.json only when something actually happened.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

MAX_SEEN_IDS = 500


def default_state() -> dict:
    return {
        "targets": {},
        "reddit": {"seen_ids": [], "seeded_feeds": []},
        "last_heartbeat_date": None,
        "last_keepalive": None,
    }


def default_target() -> dict:
    return {
        "status": None,
        "last_result": None,
        "detail": "",
        "consecutive_failures": 0,
        "failure_alert_sent": False,
        "open_incident": None,
        "last_available_alert": None,
    }


def load(path: str | Path) -> dict:
    state = default_state()
    p = Path(path)
    if p.exists() and p.read_text(encoding="utf-8").strip():
        loaded = json.loads(p.read_text(encoding="utf-8"))
        state.update({k: v for k, v in loaded.items() if k in state})
        state["reddit"] = {**default_state()["reddit"], **loaded.get("reddit", {})}
    for name, t in list(state["targets"].items()):
        state["targets"][name] = {**default_target(), **t}
    return state


def target(state: dict, name: str) -> dict:
    return state["targets"].setdefault(name, default_target())


def add_seen(state: dict, ids) -> None:
    seen = state["reddit"]["seen_ids"]
    known = set(seen)
    for i in ids:
        if i not in known:
            seen.append(i)
            known.add(i)
    del seen[:-MAX_SEEN_IDS]


def dumps(state: dict) -> str:
    return json.dumps(state, indent=2, sort_keys=True) + "\n"


def save(path: str | Path, state: dict) -> bool:
    """Write state if its content changed. Returns True when the file was written."""
    p = Path(path)
    new = dumps(state)
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    if new == old:
        return False
    p.write_text(new, encoding="utf-8", newline="\n")
    return True


def snapshot(state: dict) -> dict:
    return copy.deepcopy(state)
