from checks import frontgate
from checks.common import AVAILABLE, BLOCKED, SOLD_OUT, UNREADABLE
from helpers import FIXTURES

CFG = {"url": "https://example.invalid", "ticket_keyword": "power"}


def run(name):
    return frontgate.check(CFG, "ua", 1, html=(FIXTURES / name).read_text(encoding="utf-8"))


def test_power_sold_out():
    assert run("frontgate_power_sold_out.html").status == SOLD_OUT


def test_power_available():
    r = run("frontgate_power_available.html")
    assert r.status == AVAILABLE
    assert "rv + power add-on" in r.detail


def test_power_in_another_tickets_description_is_ignored():
    # Real page: only the RV + Power ticket is named "power"; feature lines elsewhere must not count.
    html = (FIXTURES / "frontgate_power_sold_out.html").read_text(encoding="utf-8")
    html = html.replace("RV + Power Add-On (Drive Your Own", "RV + Hookup Add-On (Drive Your Own")
    r = frontgate.parse(html, "power")
    assert r.status == SOLD_OUT
    assert "none named" in r.detail


def test_js_shell_is_unreadable():
    assert run("frontgate_js_shell.html").status == UNREADABLE


def test_challenge_page_is_blocked():
    # Fetched pages are checked for challenges before parsing.
    from checks.common import looks_like_challenge
    assert looks_like_challenge((FIXTURES / "frontgate_challenge.html").read_text(encoding="utf-8"))
