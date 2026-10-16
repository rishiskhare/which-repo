---
name: which-repo
description: Finds live GitHub repositories for a use case. Use when the user asks which repo, which library, or which open-source project to use. Skip it when the user wants code written, a bug fixed, or an implementation done and has not asked which project to use.
license: MIT
compatibility: Requires Python 3 and HTTPS access to api.github.com. Uses only the Python standard library.
metadata:
  author: rishiskhare
  version: "1.0"
  repository: "https://github.com/rishiskhare/which-repo"
---

# which-repo

Find live GitHub repositories for a use case. Run the script. Judge fit from the names and descriptions it returns.

## When to use

Use this when the user asks which repo, which library, or which open-source project to use. That includes a question asked in the middle of writing code.

Stay quiet when the user wants code written, a bug fixed, or an implementation done and has not asked which project to use.

If the use case is missing, ask once what they want the software to do. Then search. The search needs no account and no credential. Do not mention either.

## Search

Run this from the directory that contains `SKILL.md`:

```bash
python3 scripts/search.py --query "distinctive words"
```

Pass words a repository would use to describe the job. The script keeps at most four, and it drops comparison words such as alternative, free, version, like, and replacement. GitHub requires every remaining word to appear, so a brand name plus "alternative" hides the projects that only describe what they do.

When the user wants a free or open-source version of a named product, search the job, not the brand. Screen Studio is a polished screen recorder for demos, so the query is `record screen demo`, not `screen studio alternative`.

A web search may suggest the open project's name. The repository list, stars, last push, and URLs in the reply come from the script's JSON.

Do not fill gaps from memory. Do not rank trends. Do not say a kind of project is missing. Do not clone a repository.

Read the JSON:

- Exit 0 with `count` 0: no repository survived. Say so and show the recorded query.
- Exit 2 with `error` `rate_limited`: the search was refused. Say so and stop. Do not replace the list with web results.
- Exit 1: the search did not complete. Say so and stop.
- `incomplete_results` true: the search stopped early. Use the repositories that were returned. Do not send another request only because that flag is set.

`requests` records every completed call. The top-level `query`, `url`, `total_count`, and `incomplete_results` belong to the call whose repositories were kept.

## Reply

Show at most 10 repositories. For each one, give the full name, stars, last push, license, one-line description, URL, and why it fits or does not.

Say that the list order is popularity among the matches that came back. Judge fit from the name and the description. Stars and the last push are evidence of adoption and maintenance. A repository with few stars stays in the reply when it is the real match.

A repository that merely uses the requested technology goes under nearest misses when the user asked for that technology.

If the first page is the wrong kind of project, or a web search named a project that is missing from that page, run the script once more. The second query can be that project name, or words from the user's request or the first JSON. Stop after that second run. Show the recorded query for each run. Do not add a repository the script did not return.

## Reference

Endpoint, qualifiers, the query cap, and the JSON fields are in [references/reference.md](references/reference.md).
