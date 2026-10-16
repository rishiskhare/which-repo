# Search reference

The script prints one JSON object and writes nothing. Run it from the directory that contains `SKILL.md`.

## Endpoint

`GET https://api.github.com/search/repositories`

Headers:

- `Accept: application/vnd.github+json`
- `User-Agent: which-repo`
- `X-GitHub-Api-Version: 2026-03-10`

The request carries no other headers. One page only: `sort=stars`, `order=desc`, `per_page=10`.

## Qualifiers

The query is the chosen words, then:

`is:public archived:false fork:false pushed:>=YYYY-MM-DD`

The date is 18 calendar months before today in UTC. The day is clamped to the last day of the target month. GitHub treats the words as AND. The words are matched in the name, the description, and the README.

## Query cap

A content word is a token of letters, digits, `+`, `#`, `.`, `_`, and `-`, lowercased, at least two characters long. Function words are dropped: `a`, `an`, `the`, `for`, `to`, `of`, `and`, `or`, `in`, `on`, `with`, `from`, `by`.

The script sends the four longest content words, breaking length ties by original order, then emitting the chosen words in original order. If that call returns `total_count` 0 and the phrase had more than four content words, it sends one shorter query of the three longest words and records both URLs. A zero from the long query alone is not an empty search.

## Which rows are kept

At most 10 items, in the order returned. The script asks for one page of 10, so every row on that page can be kept. Each kept row has `full_name`, `html_url`, `stargazers_count`, `pushed_at`, and a non-empty `description`. Archived, fork, and private rows are dropped. `license` is the SPDX id when one was returned. `language` is included when one was returned. A low star count stays.

## Budget and refusal

GitHub counts requests, not repositories. Unauthenticated search allows 10 requests per minute for the originating IP. One use sends one request, or two when the long query has `total_count` 0. A second script run can double that.

On HTTP 403 or 429, the same request is retried once. The wait is an integer `Retry-After` capped at 60 seconds, or 5 seconds when that header is missing or is a date. If the retry still fails, the process exits 2 with:

```json
{"error":"rate_limited","repos":[],"count":0}
```

Other HTTP and network failures exit 1 with `{"error":"request_failed","repos":[],"count":0}`. A missing query exits 1 with `{"error":"empty_query","repos":[],"count":0}`. A finished search exits 0, including when `count` is 0.

`incomplete_results: true` means the search stopped early. It is part of the record. It is not a reason to send another request.

## Success JSON

Top-level fields are `query`, `url`, `total_count`, `incomplete_results`, `count`, `repos`, and `requests`. Each entry in `requests` has `query`, `url`, `total_count`, and `incomplete_results`. The top-level query fields match the call whose rows were kept.

Each repo has `full_name`, `html_url`, `stargazers_count`, `pushed_at`, and `description`. `license` and `language` are present only when GitHub returned them.
