"""Secondary check: the Front Gate event page for Camp EDC Dawn.

Ticket inventory may show here before the WordPress page updates. The page is server
rendered: each ticket type is an element carrying data-price / data-name attributes, and a
sold out ticket shows "SOLD OUT" where the quantity picker would be. We only read what a
plain GET returns and never try to get around bot protection.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from .common import (
    AVAILABLE,
    BLOCKED,
    SOLD_OUT,
    UNREADABLE,
    CheckResult,
    fetch,
    looks_like_challenge,
    normalize,
)

TARGET = "frontgate"
UNAVAILABLE_WORDS = ("sold out", "soldout", "unavailable", "not available", "no longer available")


def _ticket_rows(soup: BeautifulSoup):
    """Return [(name, row_text)] for each ticket type on the page."""
    rows = []
    for tag in soup.find_all(attrs={"data-price": True}):
        if tag.name in ("input", "select", "option", "button"):
            continue
        # Skip wrappers that contain other ticket rows; keep the innermost one per ticket.
        if tag.find(lambda t: t is not tag and t.has_attr("data-price") and t.name not in ("input", "select", "option", "button")):
            continue
        name = tag.get("data-name") or ""
        if not name:
            title = tag.find(class_=lambda c: c and "title" in c)
            name = title.get_text(" ") if title else ""
        rows.append((normalize(name), normalize(tag.get_text(" "))))
    return rows


def parse(html: str, keyword: str) -> CheckResult:
    soup = BeautifulSoup(html, "html.parser")
    rows = _ticket_rows(soup)
    if not rows:
        return CheckResult(
            TARGET,
            UNREADABLE,
            "no ticket rows in the HTML (layout changed or JavaScript-rendered); set frontgate.enabled: false",
        )
    kw = keyword.lower()
    # Match the ticket name only, so a feature line like "power hookup" in another ticket's description cannot count.
    power_rows = [(n, t) for n, t in rows if kw in n]
    if not power_rows:
        return CheckResult(TARGET, SOLD_OUT, f"{len(rows)} ticket types listed, none named '{keyword}'")
    open_rows = [(n, t) for n, t in power_rows if not any(w in t for w in UNAVAILABLE_WORDS)]
    if open_rows:
        return CheckResult(TARGET, AVAILABLE, f"power ticket on sale: {open_rows[0][0][:160]}", items=[n for n, _ in open_rows])
    return CheckResult(TARGET, SOLD_OUT, f"power ticket sold out: {power_rows[0][0][:160]}")


def check(cfg: dict, user_agent: str, timeout: float, html: str | None = None) -> CheckResult:
    if html is None:
        html = fetch(cfg["url"], user_agent, timeout).text
    result = parse(html, cfg.get("ticket_keyword", "power"))
    # Many normal pages load challenge scripts, so only treat it as blocked when content is also missing.
    if result.status == UNREADABLE and looks_like_challenge(html):
        return CheckResult(TARGET, BLOCKED, "bot challenge page returned, skipping")
    return result
