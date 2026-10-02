from datetime import datetime, timedelta, timezone

import pytest

import monitor
import state as state_mod
from checks import reddit
from checks.common import AVAILABLE, BLOCKED, ERROR, SOLD_OUT, STRUCTURE_BROKEN, CheckResult
from helpers import FIXTURES, ROOT

CFG = monitor.load_config(ROOT / "config.yaml")
# 18:00 UTC is noon in Denver (MDT), after the 9am heartbeat hour.
NOON_DENVER = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)
EARLY_DENVER = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)  # 06:00 Denver


def fresh():
    st = state_mod.default_state()
    st["last_heartbeat_date"] = "2026-10-02"  # keep heartbeats out of most tests
    return st


def deliver(pending):
    for p in pending:
        p.on_sent()
    return [p.alert for p in pending]


def edc(status, detail="power row"):
    return CheckResult("edc_page", status, detail)


def test_available_alerts_urgent_with_links():
    st = fresh()
    alerts = deliver(monitor.decide([edc(SOLD_OUT)], st, CFG, NOON_DENVER))
    assert alerts == []
    alerts = deliver(monitor.decide([edc(AVAILABLE)], st, CFG, NOON_DENVER))
    assert len(alerts) == 1
    a = alerts[0]
    assert (a.title, a.priority, a.tags) == ("DAWN RV POWER IS ON SALE", 5, ["rotating_light"])
    assert a.click == CFG["targets"]["edc_page"]["url"]
    assert CFG["targets"]["frontgate"]["url"] in a.body


def test_realert_throttled_to_30_minutes():
    st = fresh()
    t0 = NOON_DENVER
    assert len(deliver(monitor.decide([edc(AVAILABLE)], st, CFG, t0))) == 1
    for minutes in (5, 10, 29):
        assert deliver(monitor.decide([edc(AVAILABLE)], st, CFG, t0 + timedelta(minutes=minutes))) == []
    assert len(deliver(monitor.decide([edc(AVAILABLE)], st, CFG, t0 + timedelta(minutes=30)))) == 1


def test_failed_send_retries_next_run():
    st = fresh()
    pending = monitor.decide([edc(AVAILABLE)], st, CFG, NOON_DENVER)
    assert len(pending) == 1  # not delivered: on_sent never called
    assert len(monitor.decide([edc(AVAILABLE)], st, CFG, NOON_DENVER + timedelta(minutes=5))) == 1


def test_back_to_sold_out_note():
    st = fresh()
    deliver(monitor.decide([edc(AVAILABLE)], st, CFG, NOON_DENVER))
    alerts = deliver(monitor.decide([edc(SOLD_OUT)], st, CFG, NOON_DENVER + timedelta(minutes=5)))
    assert [(a.title, a.priority) for a in alerts] == [("Dawn RV power back to sold out", 3)]
    # And an immediate flip back to available alerts again right away.
    alerts = deliver(monitor.decide([edc(AVAILABLE)], st, CFG, NOON_DENVER + timedelta(minutes=10)))
    assert [a.priority for a in alerts] == [5]


def test_structure_broken_alerts_once_per_incident():
    st = fresh()
    now = NOON_DENVER
    first = deliver(monitor.decide([edc(STRUCTURE_BROKEN, "gone")], st, CFG, now))
    assert [(a.title, a.priority) for a in first] == [("EDC monitor: page layout changed", 3)]
    second = deliver(monitor.decide([edc(STRUCTURE_BROKEN, "gone")], st, CFG, now))
    assert second == []
    # Recovery closes the incident, so a new break alerts again.
    deliver(monitor.decide([edc(SOLD_OUT)], st, CFG, now))
    again = deliver(monitor.decide([edc(STRUCTURE_BROKEN, "gone")], st, CFG, now))
    assert len(again) == 1


def test_failure_counting_alerts_after_three_runs_once():
    st = fresh()
    fail = CheckResult("frontgate", ERROR, "timeout")
    counts = [len(deliver(monitor.decide([fail], st, CFG, NOON_DENVER))) for _ in range(5)]
    assert counts == [0, 0, 1, 0, 0]
    assert st["targets"]["frontgate"]["consecutive_failures"] == 5
    deliver(monitor.decide([CheckResult("frontgate", SOLD_OUT, "ok")], st, CFG, NOON_DENVER))
    assert st["targets"]["frontgate"]["consecutive_failures"] == 0
    counts = [len(deliver(monitor.decide([fail], st, CFG, NOON_DENVER))) for _ in range(3)]
    assert counts == [0, 0, 1]


def test_blocked_alerts_once_then_repeated_failure_once():
    st = fresh()
    blocked = CheckResult("reddit_new", BLOCKED, "blocked: HTTP 403")
    titles = [[a.title for a in deliver(monitor.decide([blocked], st, CFG, NOON_DENVER))] for _ in range(4)]
    assert titles == [["EDC monitor: reddit_new blocked"], [], ["EDC monitor: reddit_new failing"], []]


def reddit_result(name):
    return reddit.parse("reddit_new", (FIXTURES / name).read_bytes(), CFG["reddit_keywords"])


def test_reddit_seed_then_alert_only_new_matches():
    st = fresh()
    assert deliver(monitor.decide([reddit_result("reddit_seed.xml")], st, CFG, NOON_DENVER)) == []
    assert set(st["reddit"]["seen_ids"]) == {"t3_aaa111", "t3_bbb222"}
    alerts = deliver(monitor.decide([reddit_result("reddit_new.xml")], st, CFG, NOON_DENVER))
    assert [(a.title, a.priority, a.body) for a in alerts] == [
        ("Reddit: possible power lead", 4, "Dawn RV power add-on just restocked??"),
        ("Reddit: possible power lead", 4, "Camping question"),
    ]
    assert alerts[0].click.endswith("/comments/ccc333/x/")
    # Same feed again: everything is a duplicate now.
    assert deliver(monitor.decide([reddit_result("reddit_new.xml")], st, CFG, NOON_DENVER)) == []


def test_same_post_in_both_feeds_alerts_once():
    st = fresh()
    st["reddit"]["seeded_feeds"] = [CFG["targets"]["reddit_new"]["url"], CFG["targets"]["reddit_search"]["url"]]
    a = reddit_result("reddit_new.xml")
    b = reddit_result("reddit_new.xml")
    b.target = "reddit_search"
    alerts = deliver(monitor.decide([a, b], st, CFG, NOON_DENVER))
    assert len(alerts) == 3  # ccc333, eee555, bbb222 (bbb222 unseen here since nothing was seeded)


def test_seen_ids_capped():
    st = fresh()
    state_mod.add_seen(st, [f"t3_{i}" for i in range(700)])
    assert len(st["reddit"]["seen_ids"]) == 500
    assert st["reddit"]["seen_ids"][-1] == "t3_699"


def test_heartbeat_once_per_day_after_hour():
    st = state_mod.default_state()
    results = [edc(SOLD_OUT), CheckResult("frontgate", SOLD_OUT, "x")]
    assert deliver(monitor.decide(results, st, CFG, EARLY_DENVER)) == []
    alerts = deliver(monitor.decide(results, st, CFG, NOON_DENVER))
    assert [(a.title, a.priority) for a in alerts] == [("Monitor alive", 1)]
    assert "edc_page: SOLD_OUT" in alerts[0].body
    assert deliver(monitor.decide(results, st, CFG, NOON_DENVER + timedelta(hours=2))) == []


def test_dry_run_with_available_fixture_prints_urgent_and_writes_nothing(tmp_path, capsys, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    text = (ROOT / "config.yaml").read_text(encoding="utf-8")
    for name in ("frontgate:", "reddit_new:", "reddit_search:"):
        text = text.replace(f"  {name}\n    enabled: true", f"  {name}\n    enabled: false")
    cfg_path.write_text(text, encoding="utf-8")
    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("notify.requests.post", lambda *a, **k: pytest.fail("dry run must not send"))
    rc = monitor.main([
        "--dry-run", "--config", str(cfg_path), "--state", str(state_path),
        "--edc-html", str(FIXTURES / "edc_dawn_power_available.html"),
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[dry-run] would send p5: DAWN RV POWER IS ON SALE" in out
    assert state_path.read_text(encoding="utf-8") == "{}"


def test_state_save_only_when_changed(tmp_path):
    p = tmp_path / "state.json"
    st = state_mod.default_state()
    assert state_mod.save(p, st) is True
    assert state_mod.save(p, state_mod.load(p)) is False
