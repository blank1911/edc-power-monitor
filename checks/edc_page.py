"""Primary check: the official EDC RV camping page (server-rendered WordPress).

The Dawn section is everything between the heading that contains the section title and the
next heading of the same level. Inside it we find the "Full Price with Power Add-On" row by
text, never by CSS class, so a theme tweak does not break us.
"""
from __future__ import annotations

from bs4 import BeautifulSoup, NavigableString, Tag

from .common import (
    AVAILABLE,
    BLOCKED,
    SOLD_OUT,
    STRUCTURE_BROKEN,
    CheckResult,
    fetch,
    looks_like_challenge,
    normalize,
)

TARGET = "edc_page"
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
# Labels of the other rows. A container holding any of these is bigger than one row.
OTHER_ROW_LABELS = ("deposit", "extra vehicle")


def _find_section(soup: BeautifulSoup, section_heading: str):
    """Return (heading_tag, start_index, end_index) over soup.descendants, or None."""
    wanted = normalize(section_heading)
    nodes = list(soup.descendants)
    start = heading = None
    for i, node in enumerate(nodes):
        if isinstance(node, Tag) and node.name in HEADING_TAGS and wanted in normalize(node.get_text(" ")):
            heading, start = node, i
            break
    if heading is None:
        return None, nodes, 0, 0
    end = len(nodes)
    for j in range(start + 1, len(nodes)):
        node = nodes[j]
        if isinstance(node, Tag) and node.name == heading.name and node is not heading:
            end = j
            break
    return heading, nodes, start, end


def _last_descendant(tag: Tag):
    last = tag
    for last in tag.descendants:
        pass
    return last


def _find_row(nodes, index_of, start: int, end: int, row_label: str):
    """Find the element that holds the power row, bounded to the section."""
    label = normalize(row_label)
    candidates = []
    for i in range(start + 1, end):
        node = nodes[i]
        if isinstance(node, NavigableString) and label in normalize(str(node)):
            candidates.append(node)
    if not candidates:
        # Label may be split across inline tags, e.g. "Full Price <strong>with Power Add-On</strong>".
        for i in range(start + 1, end):
            node = nodes[i]
            if not (isinstance(node, Tag) and label in normalize(node.get_text(" "))):
                continue
            # Innermost match only: no child tag also carries the whole label.
            if not any(label in normalize(c.get_text(" ")) for c in node.find_all(True)):
                candidates.append(node)
    if not candidates:
        return None

    node = candidates[0]
    row = node.parent if isinstance(node, NavigableString) else node
    best = row
    while True:
        parent = best.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        p_start = index_of.get(id(parent))
        p_end = index_of.get(id(_last_descendant(parent)))
        if p_start is None or p_start <= start or p_end is None or p_end >= end:
            break  # would leave the Dawn section
        text = normalize(parent.get_text(" "))
        if text.count("full price") > 1 or any(lbl in text for lbl in OTHER_ROW_LABELS):
            break  # would swallow a neighbouring row
        best = parent
    return best


def parse(html: str, section_heading: str, row_label: str, buy_link_domain: str) -> CheckResult:
    soup = BeautifulSoup(html, "html.parser")
    heading, nodes, start, end = _find_section(soup, section_heading)
    if heading is None:
        return CheckResult(TARGET, STRUCTURE_BROKEN, f'section heading "{section_heading}" not found')

    index_of = {id(n): i for i, n in enumerate(nodes)}
    row = _find_row(nodes, index_of, start, end, row_label)
    if row is None:
        return CheckResult(TARGET, STRUCTURE_BROKEN, f'"{row_label}" row not found in the Dawn section')

    text = normalize(row.get_text(" "))
    if "$" not in text:
        return CheckResult(TARGET, STRUCTURE_BROKEN, f'"{row_label}" row has no price, layout may have changed')

    links = [a.get("href", "") for a in row.find_all("a")]
    buy_links = [h for h in links if buy_link_domain in h]
    sold_out = "sold out" in text
    summary = text[:200]

    if buy_links or not sold_out:
        link = buy_links[0] if buy_links else ""
        return CheckResult(TARGET, AVAILABLE, f"power row: {summary}", items=[link] if link else [])
    return CheckResult(TARGET, SOLD_OUT, f"power row: {summary}")


def check(cfg: dict, user_agent: str, timeout: float, html: str | None = None) -> CheckResult:
    if html is None:
        html = fetch(cfg["url"], user_agent, timeout).text
    result = parse(html, cfg["section_heading"], cfg["row_label"], cfg["buy_link_domain"])
    # Many normal pages load challenge scripts, so only treat it as blocked when content is also missing.
    if result.status == STRUCTURE_BROKEN and looks_like_challenge(html):
        return CheckResult(TARGET, BLOCKED, "bot challenge page returned, skipping")
    return result
