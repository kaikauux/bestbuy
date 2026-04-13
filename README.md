# bestbuy

Supporting scripts for light crawling and diagnostics against Best Buy search pages.

## What this starts with

The first pass is a probe against a specific Best Buy search URL to answer a basic question: from this runtime, what can we actually read?

Current result from this environment:

- DNS resolution works for `www.bestbuy.com`
- TCP connection to port 443 succeeds
- HTTP `HEAD` and `GET` requests time out before any response body is received
- That means we do not yet have reliable page HTML or product JSON from this runtime

## Files

- `scripts/probe_search_page.py` — small diagnostic probe for a Best Buy URL
- `reports/initial_probe.json` — captured output from the first probe run
- `reports/initial_probe.md` — short human-readable summary

## Usage

```bash
python3 scripts/probe_search_page.py 'https://www.bestbuy.com/site/searchpage.jsp?...'
```

The script prints JSON with:

- DNS resolution result
- TCP connect result
- `HEAD` request result
- `GET` request result

## Next steps

Once we find a request shape that returns actual content, we can add:

1. lightweight result-page fetchers
2. parsers for embedded JSON or product cards
3. polite pagination and rate limiting
4. snapshot diffing for price / inventory changes
```
