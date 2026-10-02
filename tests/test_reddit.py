import pytest

from checks import reddit
from helpers import FIXTURES

KW = {"any_of": ["power", "hookup", "30 amp", "50 amp"], "and_any_of": ["rv", "dawn", "camp"]}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Dawn RV power add-on restocked", True),
        ("anyone got a 30 amp HOOKUP at camp?", True),
        ("50   amp at the RVs", True),
        ("Best power bank for the festival", False),
        ("Pink flamingo near the server tent, power outage", False),
        ("Camping at dawn", False),
    ],
)
def test_keyword_matching(text, expected):
    assert reddit.matches(text, KW["any_of"], KW["and_any_of"]) is expected


def test_feed_parse_flags_matches():
    r = reddit.parse("reddit_new", (FIXTURES / "reddit_new.xml").read_bytes(), KW)
    by_id = {p["id"]: p["match"] for p in r.items}
    assert by_id == {
        "t3_ccc333": True,
        "t3_ddd444": False,
        "t3_eee555": True,
        "t3_fff666": False,
        "t3_aaa111": False,
        "t3_bbb222": True,
    }


def test_real_feed_snapshot_parses():
    r = reddit.parse("reddit_new", (FIXTURES / "reddit_real_new.xml").read_bytes(), KW)
    assert r.status == "OK"
    assert len(r.items) == 25
    assert all(p["id"].startswith("t3_") and p["url"].startswith("https://www.reddit.com/") for p in r.items)
