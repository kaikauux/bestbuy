# bestbuy

Supporting scripts for light crawling of Best Buy search pages.

## What works now

Plain `requests` / `curl` from this runtime stalled after TLS completed. A browser-impersonating client via `curl-cffi` works for raw HTML fetches, but the Best Buy page only server-renders a partial subset of results.

The working hourly path is now browser-backed with Playwright:

- open a real Chromium session
- set the store context to `Union City`
- load the search page after hydration
- scroll to hydrate visible result cards
- collect currently available open-box items across pages

## Root cause, in short

- DNS worked
- TCP to `www.bestbuy.com:443` worked
- TLS handshake completed
- raw HTTP clients received no response bytes before timeout
- `curl-cffi` with Chrome impersonation succeeded, but only exposed a partial SSR subset
- the full, accurate availability view requires the hydrated browser DOM

That means the real fix is not just anti-bot fingerprinting. It is anti-bot plus client-side rendering.

## Files

- `bestbuy/search.py` — raw HTML fetch and parse helpers from the earlier probe path
- `bestbuy/browser_search.py` — browser-backed store selection and hydrated result extraction
- `scripts/fetch_search_results.py` — JSON CLI entrypoint for the raw HTML path
- `scripts/hourly_available_report.py` — human-readable browser-backed hourly report CLI
- `scripts/probe_search_page.py` — low-level reachability probe from the first pass
- `reports/initial_probe.json` — raw low-level probe output
- `reports/initial_probe.md` — first-pass summary
- `tests/test_search_parser.py` — parser regression test
- `tests/fixtures/searchpage.html` — saved real search-page fixture

## Install

```bash
python3 -m pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH=/data/pw-browsers python3 -m playwright install chromium
```

## Usage

Fetch one page and print parsed JSON:

```bash
python3 scripts/fetch_search_results.py \
  --url 'https://www.bestbuy.com/site/searchpage.jsp?id=pcat17071&qp=parent_laptopscreensizesv_facet%3DScreen+Size%7E14%22+-+15.9%22%5Eparent_laptopscreensizesv_facet%3DScreen+Size%7E12%22+-+13.9%22%5Econdition_facet%3DOpen-Box%7EOpen-Box%5Esystemmemoryram_facet%3DRAM%7E32+gigabytes%5Esystemmemoryram_facet%3DRAM%7E64+gigabytes%5Esystemmemoryram_facet%3DRAM%7E128+gigabytes%5Esystemmemoryram_facet%3DRAM%7E36+gigabytes&st=5070+Ti+laptop' \
  --pretty
```

Fetch every page for a query and return a deduplicated JSON report:

```bash
python3 scripts/fetch_search_results.py \
  --url 'https://www.bestbuy.com/site/searchpage.jsp?st=5070+Ti+laptop' \
  --all-pages \
  --pretty
```

Print the hourly human-readable browser-backed availability report:

```bash
PLAYWRIGHT_BROWSERS_PATH=/data/pw-browsers python3 scripts/hourly_available_report.py \
  --url 'https://www.bestbuy.com/site/searchpage.jsp?id=pcat17071&qp=parent_laptopscreensizesv_facet%3DScreen+Size%7E14%22+-+15.9%22%5Eparent_laptopscreensizesv_facet%3DScreen+Size%7E12%22+-+13.9%22%5Econdition_facet%3DOpen-Box%7EOpen-Box%5Esystemmemoryram_facet%3DRAM%7E32+gigabytes%5Esystemmemoryram_facet%3DRAM%7E64+gigabytes%5Esystemmemoryram_facet%3DRAM%7E128+gigabytes%5Esystemmemoryram_facet%3DRAM%7E36+gigabytes&st=5070+Ti+laptop' \
  --store 'Union City'
```

Fetch live and save the raw HTML too:

```bash
python3 scripts/fetch_search_results.py --url 'https://www.bestbuy.com/site/searchpage.jsp?st=5070+Ti+laptop' --save-html reports/latest.html --pretty
```

Parse a saved HTML file:

```bash
python3 scripts/fetch_search_results.py --html tests/fixtures/searchpage.html --pretty
```

## Output shape

Each parsed result currently includes:

- `sku_id`
- `title`
- `short_name`
- `brand`
- `model_number`
- `condition`
- `customer_price`
- `regular_price`
- `displayable_customer_price`
- `price_with_cart`
- `product_url`
- `sku_url`
- `image_url`
- `average_rating`
- `review_count`
- `button_state`
- `open_box_options`

## Test

```bash
python3 -m unittest discover -s tests -v
```
