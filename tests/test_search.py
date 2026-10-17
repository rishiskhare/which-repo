import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("find_github_repos_search", ROOT / "scripts" / "search.py")
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)

TODAY = date(2026, 10, 16)


def repo(**overrides):
    item = {
        "full_name": "octo/example",
        "html_url": "https://github.com/octo/example",
        "stargazers_count": 10,
        "pushed_at": "2026-01-01T00:00:00Z",
        "description": "An example project",
        "archived": False,
        "fork": False,
        "private": False,
        "language": "Python",
        "license": {"spdx_id": "MIT"},
    }
    item.update(overrides)
    return item


def body(items, total=None, incomplete=False):
    return {
        "total_count": len(items) if total is None else total,
        "incomplete_results": incomplete,
        "items": items,
    }


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        status, headers_out, payload = self.responses.pop(0)
        if not isinstance(payload, (bytes, str)):
            payload = json.dumps(payload).encode()
        return status, headers_out, payload


class SearchTests(unittest.TestCase):
    def run_query(self, argv, transport, sleeper=None):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                search.main(
                    argv,
                    transport=transport,
                    sleeper=sleeper or (lambda _seconds: None),
                    today=TODAY,
                )
        return caught.exception.code, stdout.getvalue(), transport

    def query_text(self, url):
        return parse_qs(urlparse(url).query)["q"][0]

    def test_caps_query_at_four_longest_words(self):
        transport = Transport([(200, {}, body([repo()]))])
        code, raw, transport = self.run_query(
            ["--query", "alpha beta gamma delta epsilon"],
            transport,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(transport.calls), 1)
        url, headers = transport.calls[0]
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["Accept"], "application/vnd.github+json")
        text = self.query_text(url)
        self.assertTrue(text.startswith("alpha gamma delta epsilon "))
        self.assertNotIn("beta", text.split())
        self.assertIn("is:public", text)
        self.assertIn("archived:false", text)
        self.assertIn("fork:false", text)
        self.assertIn("pushed:>=2025-04-16", text)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        self.assertEqual(params["sort"], ["stars"])
        self.assertEqual(params["order"], ["desc"])
        self.assertEqual(params["per_page"], ["10"])

    def test_zero_count_retries_three_longest_words(self):
        kept = repo(full_name="octo/shorter", stargazers_count=9)
        transport = Transport(
            [
                (200, {}, body([], total=0)),
                (200, {}, body([kept], total=1)),
            ]
        )
        code, raw, transport = self.run_query(
            ["--query", "alpha beta gamma delta epsilon"],
            transport,
        )
        self.assertEqual(code, 0)
        payload = json.loads(raw)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(len(payload["requests"]), 2)
        self.assertTrue(self.query_text(payload["requests"][0]["url"]).startswith("alpha gamma delta epsilon "))
        self.assertTrue(self.query_text(payload["requests"][1]["url"]).startswith("alpha gamma epsilon "))
        self.assertEqual(payload["query"], "alpha gamma epsilon")
        self.assertEqual(payload["url"], payload["requests"][1]["url"])
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["repos"][0]["full_name"], "octo/shorter")

    def test_drops_archived_repos(self):
        transport = Transport(
            [
                (
                    200,
                    {},
                    body(
                        [
                            repo(full_name="octo/archived", archived=True),
                            repo(full_name="octo/fork", fork=True),
                            repo(full_name="octo/private", private=True),
                            repo(full_name="octo/blank", description="  "),
                            repo(full_name="octo/live", stargazers_count=4),
                        ]
                    ),
                )
            ]
        )
        code, raw, _transport = self.run_query(["--query", "sqlite search"], transport)
        self.assertEqual(code, 0)
        payload = json.loads(raw)
        names = [item["full_name"] for item in payload["repos"]]
        self.assertEqual(names, ["octo/live"])

    def test_429_exits_2_with_empty_list(self):
        delays = []
        transport = Transport(
            [
                (429, {"Retry-After": "0"}, {"message": "slow down"}),
                (429, {"Retry-After": "0"}, {"message": "slow down"}),
            ]
        )
        code, raw, transport = self.run_query(["--query", "sqlite search"], transport, delays.append)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(raw), {"error": "rate_limited", "repos": [], "count": 0})
        self.assertEqual(raw.strip(), '{"error":"rate_limited","repos":[],"count":0}')
        self.assertEqual(delays, [0])
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(search.wait_seconds({}), 5)
        self.assertEqual(search.wait_seconds({"Retry-After": "120"}), 60)
        self.assertEqual(search.wait_seconds({"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}), 5)

    def test_keeps_repo_with_three_stars(self):
        transport = Transport(
            [
                (
                    200,
                    {},
                    body(
                        [
                            repo(full_name="octo/popular", stargazers_count=100),
                            repo(
                                full_name="octo/small",
                                stargazers_count=3,
                                description="SQLite full text search bindings",
                                language="C",
                            ),
                        ]
                    ),
                )
            ]
        )
        code, raw, _transport = self.run_query(["--query", "sqlite search"], transport)
        self.assertEqual(code, 0)
        payload = json.loads(raw)
        small = payload["repos"][1]
        self.assertEqual(small["stargazers_count"], 3)
        self.assertEqual(small["full_name"], "octo/small")
        self.assertEqual(small["license"], "MIT")
        self.assertEqual(small["language"], "C")
        self.assertEqual(small["html_url"], "https://github.com/octo/example")

    def test_keeps_the_full_page(self):
        items = [repo(full_name=f"octo/repo-{index}", stargazers_count=index) for index in range(11)]
        transport = Transport([(200, {}, body(items))])
        code, raw, _transport = self.run_query(["--query", "sqlite search"], transport)
        self.assertEqual(code, 0)
        payload = json.loads(raw)
        self.assertEqual(payload["count"], 10)
        self.assertEqual(payload["repos"][-1]["full_name"], "octo/repo-9")

    def test_drops_comparison_words(self):
        transport = Transport([(200, {}, body([repo()]))])
        code, _raw, transport = self.run_query(
            ["--query", "free screen studio alternative"],
            transport,
        )
        self.assertEqual(code, 0)
        words = self.query_text(transport.calls[0][0]).split()
        self.assertEqual(words[:2], ["screen", "studio"])
        self.assertNotIn("alternative", words)
        self.assertNotIn("free", words)

    def test_missing_query_exits_1(self):
        def explode(url, headers):
            raise AssertionError("the API was called")

        code, raw, _transport = self.run_query([], explode)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(raw), {"error": "empty_query", "repos": [], "count": 0})


if __name__ == "__main__":
    unittest.main()
