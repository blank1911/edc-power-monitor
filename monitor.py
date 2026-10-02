"""EDC Las Vegas 2027 Dawn RV power monitor.

Alert only. It reads public pages, decides what changed, and pushes to ntfy. It never buys,
logs in, queues, or tries to get past any bot protection.

  python monitor.py                 normal run
  python monitor.py --dry-run       print what would alert, send nothing, write no state
  python monitor.py --test-alert    send one test notification at each priority level
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import notify
import state as state_mod
from checks import edc_page, frontgate, reddit
from checks.common import AVAILABLE, BLOCKED, SOLD_OUT, STRUCTURE_BROKEN, UNREADABLE, CheckResult, run_safely
from notify import Alert

HERE = Path(__file__).resolve().parent
INCIDENT_STATUSES = {STRUCTURE_BROKEN, BLOCKED, UNREADABLE}
REDDIT_TARGETS = ("reddit_new", "reddit_search")


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- running the checks

def run_checks(cfg: dict, overrides: dict | None = None) -> list[CheckResult]:
    overrides = overrides or {}
    ua, timeout = cfg["user_agent"], cfg["timeout_seconds"]
    targets = cfg["targets"]
    results = []
    if targets["edc_page"].get("enabled", True):
        results.append(run_safely("edc_page", edc_page.check, targets["edc_page"], ua, timeout, overrides.get("edc_page")))
    if targets["frontgate"].get("enabled", True):
        results.append(run_safely("frontgate", frontgate.check, targets["frontgate"], ua, timeout, overrides.get("frontgate")))
    for name in REDDIT_TARGETS:
        if targets[name].get("enabled", True):
            results.append(
                run_safely(name, reddit.check, name, targets[name], ua, timeout, cfg["reddit_keywords"], overrides.get(name))
            )
    return results


# ---------------------------------------------------------------- deciding what to alert

class Pending:
    """An alert plus the state change to apply only once it is actually delivered."""

    def __init__(self, alert: Alert, on_sent=None):
        self.alert = alert
        self.on_sent = on_sent or (lambda: None)


def _power_alerts(name: str, result: CheckResult, t: dict, cfg: dict, now: datetime) -> list[Pending]:
    out = []
    edc_url = cfg["targets"]["edc_page"]["url"]
    fg_url = cfg["targets"]["frontgate"]["url"]
    prev = t["status"]
    if result.status == AVAILABLE:
        last = _parse_iso(t["last_available_alert"])
        due = prev != AVAILABLE or last is None or now - last >= timedelta(minutes=cfg["realert_minutes"])
        if due:
            source = "EDC page" if name == "edc_page" else "Front Gate"
            body = (
                f"Bring Your Own RV (Dawn 4 Nights) Full Price with Power Add-On looks available ({source}).\n"
                f"Front Gate Dawn: {fg_url}\n"
                f"{result.detail}"
            )

            def mark(t=t):
                t["last_available_alert"] = _iso(now)

            out.append(Pending(Alert("DAWN RV POWER IS ON SALE", body, notify.URGENT, ["rotating_light"], edc_url), mark))
        t["status"] = AVAILABLE
    elif result.status == SOLD_OUT:
        if prev == AVAILABLE:
            out.append(Pending(Alert(
                "Dawn RV power back to sold out",
                f"{name}: the power option is showing sold out again. {result.detail}",
                notify.DEFAULT, ["no_entry"], edc_url)))
        t["status"] = SOLD_OUT
        t["last_available_alert"] = None
    return out


def _reddit_alerts(name: str, result: CheckResult, st: dict, cfg: dict, alerted_now: set) -> list[Pending]:
    out = []
    url = cfg["targets"][name]["url"]
    posts = result.items
    if url not in st["reddit"]["seeded_feeds"]:
        state_mod.add_seen(st, [p["id"] for p in posts])
        st["reddit"]["seeded_feeds"].append(url)
        print(f"[{name}] first run: seeded {len(posts)} posts without alerting")
        return out
    seen = set(st["reddit"]["seen_ids"])
    fresh = [p for p in posts if p["id"] not in seen and p["id"] not in alerted_now]
    state_mod.add_seen(st, [p["id"] for p in fresh if not p["match"]])
    for p in [p for p in fresh if p["match"]]:
        alerted_now.add(p["id"])

        def mark(pid=p["id"]):
            state_mod.add_seen(st, [pid])

        out.append(Pending(Alert("Reddit: possible power lead", p["title"], notify.HIGH, ["speech_balloon"], p["url"]), mark))
    return out


def decide(results: list[CheckResult], st: dict, cfg: dict, now: datetime) -> list[Pending]:
    pending: list[Pending] = []
    alerted_reddit: set = set()
    threshold = cfg["failure_alert_threshold"]
    for r in results:
        t = state_mod.target(st, r.target)
        t["detail"] = r.detail[:200]
        if r.failed:
            t["consecutive_failures"] += 1
            t["last_result"] = r.status
            if r.status in INCIDENT_STATUSES and t["open_incident"] != r.status:
                def mark_incident(t=t, s=r.status):
                    t["open_incident"] = s
                title = "EDC monitor: page layout changed" if r.status == STRUCTURE_BROKEN else f"EDC monitor: {r.target} {r.status.lower()}"
                pending.append(Pending(Alert(title, f"{r.target}: {r.detail}", notify.DEFAULT, ["warning"]), mark_incident))
            if t["consecutive_failures"] >= threshold and not t["failure_alert_sent"]:
                def mark_fail(t=t):
                    t["failure_alert_sent"] = True
                pending.append(Pending(Alert(
                    f"EDC monitor: {r.target} failing",
                    f"{r.target} failed {t['consecutive_failures']} runs in a row. Latest: {r.detail}",
                    notify.DEFAULT, ["warning"]), mark_fail))
            continue

        t["consecutive_failures"] = 0
        t["failure_alert_sent"] = False
        t["open_incident"] = None
        t["last_result"] = r.status
        if r.target in ("edc_page", "frontgate"):
            pending += _power_alerts(r.target, r, t, cfg, now)
        else:
            t["status"] = r.status
            pending += _reddit_alerts(r.target, r, st, cfg, alerted_reddit)

    # Do not flood the phone if Reddit lights up.
    cap = cfg["max_reddit_alerts_per_run"]
    reddit_pending = [p for p in pending if p.alert.title.startswith("Reddit:")]
    if len(reddit_pending) > cap:
        extra = reddit_pending[cap:]
        pending = [p for p in pending if p not in extra]
        for p in extra:
            p.on_sent()  # mark seen; covered by the summary below
        pending.append(Pending(Alert(
            "Reddit: more possible power leads",
            f"{len(extra)} more matching posts. Check r/electricdaisycarnival.",
            notify.HIGH, ["speech_balloon"], "https://www.reddit.com/r/electricdaisycarnival/new/")))

    hb = heartbeat(results, st, cfg, now)
    if hb:
        pending.append(hb)
    return pending


def heartbeat(results: list[CheckResult], st: dict, cfg: dict, now: datetime) -> Pending | None:
    local = now.astimezone(ZoneInfo(cfg["timezone"]))
    today = local.date().isoformat()
    if local.hour < cfg["heartbeat_hour"] or st["last_heartbeat_date"] == today:
        return None
    by_name = {r.target: r for r in results}
    lines = []
    for name, tcfg in cfg["targets"].items():
        if not tcfg.get("enabled", True):
            lines.append(f"{name}: disabled")
        elif name in by_name:
            r = by_name[name]
            extra = f" ({r.detail[:60]})" if r.failed or name.startswith("reddit") else ""
            lines.append(f"{name}: {r.status}{extra}")

    def mark():
        st["last_heartbeat_date"] = today

    return Pending(Alert("Monitor alive", "\n".join(lines), notify.MIN, ["white_check_mark"]), mark)


# ---------------------------------------------------------------- output

def write_summary(results: list[CheckResult], sent: list[str]) -> None:
    lines = ["| Target | Status | Detail |", "|---|---|---|"]
    for r in results:
        lines.append(f"| {r.target} | {r.status} | {r.detail[:150].replace('|', '/')} |")
    lines.append("")
    lines.append("Alerts: " + ("; ".join(sent) if sent else "none"))
    text = "\n".join(lines)
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## EDC Dawn RV power monitor\n\n" + text + "\n")


def send_test_alerts(cfg: dict) -> int:
    ua, timeout = cfg["user_agent"], cfg["timeout_seconds"]
    edc_url = cfg["targets"]["edc_page"]["url"]
    ok = True
    for prio in (notify.MIN, notify.LOW, notify.DEFAULT, notify.HIGH, notify.URGENT):
        alert = Alert(f"TEST p{prio}: EDC monitor", f"Test notification at priority {prio}. Nothing is on sale.",
                      prio, ["test_tube"], edc_url)
        ok = notify.send(alert, ua, timeout) and ok
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EDC Dawn RV power add-on monitor (alert only)")
    ap.add_argument("--dry-run", action="store_true", help="print alerts, send nothing, do not write state")
    ap.add_argument("--test-alert", action="store_true", help="send one test notification at each priority")
    ap.add_argument("--config", default=str(HERE / "config.yaml"))
    ap.add_argument("--state", default=str(HERE / "state.json"))
    ap.add_argument("--edc-html", help="use this local HTML file instead of fetching the EDC page")
    ap.add_argument("--frontgate-html", help="use this local HTML file instead of fetching Front Gate")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.test_alert:
        return send_test_alerts(cfg)

    overrides = {}
    if args.edc_html:
        overrides["edc_page"] = Path(args.edc_html).read_text(encoding="utf-8")
    if args.frontgate_html:
        overrides["frontgate"] = Path(args.frontgate_html).read_text(encoding="utf-8")

    st = state_mod.load(args.state)
    now = datetime.now(timezone.utc)
    results = run_checks(cfg, overrides)
    for r in results:
        print(f"[{r.target}] {r.status}: {r.detail}")

    sent = []
    for p in decide(results, st, cfg, now):
        if notify.send(p.alert, cfg["user_agent"], cfg["timeout_seconds"], dry_run=args.dry_run):
            p.on_sent()
            sent.append(f"p{p.alert.priority} {p.alert.title}")
    write_summary(results, sent)

    if args.dry_run:
        print("[dry-run] state not written")
    elif state_mod.save(args.state, st):
        print("[state] state.json updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
