"""Community signal: r/electricdaisycarnival RSS feeds."""
from __future__ import annotations

import html as html_lib
import re

import feedparser

from .common import BLOCKED, OK, UNREADABLE, CheckResult, fetch, looks_like_challenge

TAG_RE = re.compile(r"<[^>]+>")


def _keyword_pattern(words):
    # Match at a word start so "rv" hits "RV" and "RVs" but not "server"; "camp" hits "camping".
    parts = [r"\s+".join(re.escape(p) for p in w.split()) for w in words]
    return re.compile(r"\b(?:" + "|".join(parts) + ")", re.IGNORECASE)


def matches(text: str, any_of, and_any_of) -> bool:
    return bool(_keyword_pattern(any_of).search(text)) and bool(_keyword_pattern(and_any_of).search(text))


def _entry_text(entry) -> str:
    body = entry.get("summary", "")
    for content in entry.get("content", []) or []:
        body += " " + content.get("value", "")
    body = html_lib.unescape(TAG_RE.sub(" ", body))
    return f"{entry.get('title', '')} {body}"


def parse(target: str, feed_bytes: bytes, keywords: dict) -> CheckResult:
    feed = feedparser.parse(feed_bytes)
    if not feed.entries:
        if feed.bozo:
            return CheckResult(target, UNREADABLE, f"feed did not parse: {feed.get('bozo_exception')}")
        return CheckResult(target, OK, "feed has no posts")
    posts = []
    for e in feed.entries:
        pid = e.get("id") or e.get("link")
        if not pid:
            continue
        posts.append(
            {
                "id": pid,
                "title": e.get("title", "(no title)"),
                "url": e.get("link", ""),
                "match": matches(_entry_text(e), keywords["any_of"], keywords["and_any_of"]),
            }
        )
    return CheckResult(target, OK, f"{len(posts)} posts read", items=posts)


def check(target: str, cfg: dict, user_agent: str, timeout: float, keywords: dict, data: bytes | None = None) -> CheckResult:
    if data is None:
        resp = fetch(cfg["url"], user_agent, timeout, accept="application/atom+xml,application/rss+xml,*/*")
        if looks_like_challenge(resp.text):
            return CheckResult(target, BLOCKED, "block page returned instead of the feed, skipping")
        data = resp.content
    return parse(target, data, keywords)
