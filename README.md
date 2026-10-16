# which-repo

Finds live GitHub repositories for a use case.

[![skills.sh](https://skills.sh/b/rishiskhare/which-repo)](https://skills.sh/rishiskhare/which-repo)

## Install

```bash
npx skills add rishiskhare/which-repo
```

## What it does

The skill searches public repositories that are not forks and not archived, and that were pushed within the last 18 months. It returns at most 10 matches, with stars, the last push, and a URL.

The search runs with the Python standard library and prints the matches as JSON.

## License

[MIT](LICENSE)
