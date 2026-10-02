"""Secondary check: the Front Gate event page for Dawn RV.

Ticket inventory may show here before the WordPress page updates. We only read what a plain
GET returns. If the page is rendered by JavaScript or sits behind a bot wall we report that
and skip; we never try to get around it.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString

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
PRICE_RE = re.compile(r"\$\s?\d")
MAX_ROW_CHARS = 400


def _ticket_rows(soup: BeautifulSoup):
    """Yield (row_text) for every small element that has a price, one row per ticket type."""
    rows = []
    for node in soup.find_all(string=PRICE_RE):
        if not isinstance(node, NavigableString) or node.parent.name in ("script", "style"):
            continue
        row = node.parent
        # Grow until the row has a name next to the price, but stay small enough to be one row.
        while row.parent is not None and len(normalize(row.get_text(" "))) < 25:
            row = row.parent
        while (
            row.parent is not None
            and row.parent.name not in ("body", "html", "[document]")
            and len(PRICE_RE.findall(row.parent.get_text(" "))) == 1
            and len(normalize(row.parent.get_text(" "))) <= MAX_ROW_CHARS
        ):
            row = row.parent
        text = normalize(row.get_text(" "))
        if text not in rows:
            rows.append(text)
    return rows


def parse(html: str, keyword: str) -> CheckResult:
    soup = BeautifulSoup(html, "html.parser")
    rows = _ticket_rows(soup)
    if not rows:
        return CheckResult(
            TARGET,
            UNREADABLE,
            "no ticket prices in the HTML (likely JavaScript-rendered); set frontgate.enabled: false",
        )
    kw = keyword.lower()
    power_rows = [r for r in rows if kw in r]
    if not power_rows:
        return CheckResult(TARGET, SOLD_OUT, f"{len(rows)} ticket rows, none mention '{keyword}'")
    open_rows = [r for r in power_rows if not any(w in r for w in UNAVAILABLE_WORDS)]
    if open_rows:
        return CheckResult(TARGET, AVAILABLE, f"power ticket listed: {open_rows[0][:160]}", items=open_rows)
    return CheckResult(TARGET, SOLD_OUT, f"power ticket marked unavailable: {power_rows[0][:160]}")


def check(cfg: dict, user_agent: str, timeout: float, html: str | None = None) -> CheckResult:
    if html is None:
        html = fetch(cfg["url"], user_agent, timeout).text
    result = parse(html, cfg.get("ticket_keyword", "power"))
    # Many normal pages load challenge scripts, so only treat it as blocked when content is also missing.
    if result.status == UNREADABLE and looks_like_challenge(html):
        return CheckResult(TARGET, BLOCKED, "bot challenge page returned, skipping")
    return result
