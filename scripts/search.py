#!/usr/bin/env python3
"""Search public GitHub repositories and print a JSON record."""

import argparse
import calendar
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from urllib.parse import urlencode

API = "https://api.github.com/search/repositories"
PAGE = 10
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "which-repo",
    "X-GitHub-Api-Version": "2026-03-10",
}
ALLOWED = frozenset("abcdefghijklmnopqrstuvwxyz0123456789+#._-")
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "for",
        "to",
        "of",
        "and",
        "or",
        "in",
        "on",
        "with",
        "from",
        "by",
        "free",
        "like",
        "similar",
        "version",
        "versions",
        "alternative",
        "alternatives",
        "replacement",
        "replacements",
        "equivalent",
    }
)
EMPTY_QUERY = {"error": "empty_query", "repos": [], "count": 0}
RATE_LIMITED = {"error": "rate_limited", "repos": [], "count": 0}
REQUEST_FAILED = {"error": "request_failed", "repos": [], "count": 0}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        emit(EMPTY_QUERY, 1)


def emit(payload, code):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    raise SystemExit(code)


def content_words(phrase):
    words = []
    for index, raw in enumerate(phrase.split()):
        text = raw.lower()
        while text and text[0] not in ALLOWED:
            text = text[1:]
        while text and text[-1] not in ALLOWED:
            text = text[:-1]
        if len(text) < 2 or any(char not in ALLOWED for char in text):
            continue
        if text in STOPWORDS:
            continue
        words.append((text, index))
    return words


def choose_words(words, limit):
    ranked = sorted(words, key=lambda item: (-len(item[0]), item[1]))
    chosen = ranked[:limit]
    chosen.sort(key=lambda item: item[1])
    return " ".join(word for word, _index in chosen)


def months_ago(day, months=18):
    month = day.month - months
    year = day.year
    while month <= 0:
        month += 12
        year -= 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def search_url(words, pushed_since):
    query = f"{words} is:public archived:false fork:false pushed:>={pushed_since}"
    params = urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": str(PAGE)}
    )
    return f"{API}?{params}"


def wait_seconds(headers):
    raw = None
    for key, value in (headers or {}).items():
        if str(key).lower() == "retry-after":
            raw = value
            break
    if raw is None:
        return 5
    text = str(raw).strip()
    if text.isdigit():
        return min(int(text), 60)
    return 5


def load_body(body):
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    return json.loads(body)


def header_map(headers):
    if not headers:
        return {}
    return dict(headers.items())


def default_transport(url, headers):
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, header_map(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, header_map(error.headers), error.read()


def call_api(url, transport, sleeper):
    for attempt in range(2):
        try:
            status, resp_headers, body = transport(url, dict(HEADERS))
        except Exception:
            return ("failed", None)
        if status in (403, 429):
            if attempt == 0:
                sleeper(wait_seconds(resp_headers))
                continue
            return ("rate_limited", None)
        if status != 200:
            return ("failed", None)
        try:
            return ("ok", load_body(body))
        except Exception:
            return ("failed", None)
    return ("rate_limited", None)


def parse_result(data):
    if not isinstance(data, dict):
        return None
    total = data.get("total_count")
    incomplete = data.get("incomplete_results")
    items = data.get("items")
    if isinstance(total, bool) or not isinstance(total, int):
        return None
    if not isinstance(incomplete, bool) or not isinstance(items, list):
        return None
    return total, incomplete, items


def presentable(value):
    return isinstance(value, str) and bool(value.strip())


def select_repos(items):
    kept = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("archived") is True or item.get("fork") is True or item.get("private") is True:
            continue
        stars = item.get("stargazers_count")
        if isinstance(stars, bool) or not isinstance(stars, int):
            continue
        if not all(
            presentable(item.get(field))
            for field in ("full_name", "html_url", "pushed_at", "description")
        ):
            continue
        repo = {
            "full_name": item["full_name"],
            "html_url": item["html_url"],
            "stargazers_count": stars,
            "pushed_at": item["pushed_at"],
            "description": item["description"],
        }
        license_info = item.get("license")
        if isinstance(license_info, dict):
            spdx = license_info.get("spdx_id")
            if presentable(spdx):
                repo["license"] = spdx
        language = item.get("language")
        if presentable(language):
            repo["language"] = language
        kept.append(repo)
        if len(kept) == PAGE:
            break
    return kept


def run(phrase, transport, sleeper, today):
    words = content_words(phrase)
    if not words:
        return EMPTY_QUERY, 1
    primary = choose_words(words, 4)
    pushed_since = months_ago(today).isoformat()
    requests = []

    def once(query_words):
        url = search_url(query_words, pushed_since)
        kind, data = call_api(url, transport, sleeper)
        if kind != "ok":
            return kind, None
        parsed = parse_result(data)
        if parsed is None:
            return "failed", None
        total, incomplete, items = parsed
        record = {
            "query": query_words,
            "url": url,
            "total_count": total,
            "incomplete_results": incomplete,
        }
        requests.append(record)
        return "ok", items

    kind, items = once(primary)
    if kind == "rate_limited":
        return RATE_LIMITED, 2
    if kind == "failed":
        return REQUEST_FAILED, 1
    if requests[0]["total_count"] == 0 and len(words) > 4:
        shorter = choose_words(words, 3)
        kind, items = once(shorter)
        if kind == "rate_limited":
            return RATE_LIMITED, 2
        if kind == "failed":
            return REQUEST_FAILED, 1
    record = requests[-1]
    repos = select_repos(items)
    payload = {
        "query": record["query"],
        "url": record["url"],
        "total_count": record["total_count"],
        "incomplete_results": record["incomplete_results"],
        "count": len(repos),
        "repos": repos,
        "requests": requests,
    }
    return payload, 0


def main(argv=None, transport=None, sleeper=None, today=None):
    parser = Parser(prog="search.py")
    parser.add_argument("--query", default=None)
    args = parser.parse_args(argv)
    if args.query is None or not str(args.query).strip():
        emit(EMPTY_QUERY, 1)
    payload, code = run(
        args.query,
        transport or default_transport,
        sleeper or time.sleep,
        today or datetime.now(timezone.utc).date(),
    )
    emit(payload, code)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        emit(REQUEST_FAILED, 1)
