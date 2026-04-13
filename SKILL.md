---
name: bestbuy-search-crawler
description: Scrape Best Buy search results for laptops or any query, working around anti-bot and region-state issues. Covers Playwright session setup, the locStoreId cookie trick, DOM selectors, and pricing extraction.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [web scraping, e-commerce, Playwright, Best Buy, laptops, open-box]
    related_skills: [duckduckgo-search]
---

# Best Buy Search Crawler

Best Buy search pages block raw HTTP clients and require a real browser to hydrate correctly. Region/state is driven primarily by the locStoreId cookie, not by ZIP codes alone.

## Architecture summary

Best Buy uses:
- server-side rendering for a partial product stub
- client-side hydration to fill in prices, availability, and open-box offers
- locStoreId cookie to choose which inventory pool and open-box conditions to display

Standard requests, curl, and curl-cffi will:
- get a partial SSR stub with See price in cart or Unavailable
- not show real open-box availability or correct pricing

## Working approach

1. Launch Playwright with real Chromium (headless is fine)
2. Seed locStoreId cookie on .bestbuy.com
3. Warm the session by visiting the Best Buy homepage
4. Then navigate to the search URL
5. Wait for hydration, scroll to trigger lazy loading
6. Extract from #main-results .product-list-item.grid-view
7. Read: title, review count, product link, open-box prices

## Critical session setup

DO NOT use this flow:
- setting cookie then directly navigating to search page

USE this flow:
- set cookie, visit homepage, THEN navigate to search page

Without the homepage visit, Best Buy does not always flip into the correct region/inventory state.

## locStoreId behavior

locStoreId is the single strongest cookie for changing Best Buy's result set:
- without it or with default state: 26 results for some filtered queries
- with locStoreId=1021: 29 results for our open-box high-RAM laptop query

It changes:
- total result count
- ordering
- which open-box condition and price is shown as as low as
- pickup availability language

Other location cookies like locDestZip, customerZipCode, sc-location-v2 had no measurable effect when locStoreId was absent or set differently.

## Dependencies

- Python playwright
- Chromium installed via playwright install chromium

Both are tracked in requirements.txt at the repo root.

## Playwright setup

Launch headless Chromium with a full viewport. Seed the location cookie before any navigation.

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1440, 'height': 2200},
        locale='en-US',
    )
    # Seed location cookie BEFORE navigating
    location_store = '1021'
    context.add_cookies([
        {'name': 'locStoreId', 'value': location_store, 'domain': '.bestbuy.com', 'path': '/'},
    ])
    page = context.new_page()

    # Warm session on homepage first
    page.goto('https://www.bestbuy.com/', wait_until='domcontentloaded', timeout=120000)
    page.wait_for_timeout(8000)

    # Then go to the actual search page
    search_url = 'https://www.bestbuy.com/site/searchpage.jsp?st=5070+Ti+laptop'
    page.goto(search_url, wait_until='domcontentloaded', timeout=120000)
    page.wait_for_timeout(12000)

    # Scroll to trigger lazy-loaded cards
    for y in [0, 1000, 2000, 3000, 4000, 5000]:
        page.evaluate(f'window.scrollTo(0, {y})')
        page.wait_for_timeout(1000)
```

## Extracting product cards

Use #main-results .product-list-item.grid-view. This targets only the main search results list, not featured or sponsored carousels above it.

```python
cards = page.locator('#main-results .product-list-item.grid-view')
total_cards = cards.count()
for i in range(total_cards):
    card = cards.nth(i)
    text = card.inner_text().strip()
    if 'See price in cart' in text or text == 'Sponsored':
        continue

    links = card.locator('a.product-list-item-link').evaluate_all(
        "els => els.map(e => ({href: e.href, text: (e.innerText || '').trim()}))"
    )
    # href points to a specific open-box condition, e.g. /openbox?condition=excellent
```

## Pricing extraction

Best Buy shows two price blocks on open-box cards:
1. Open-box as low as $X,XXX.XX — the cheapest open-box condition
2. More Buying Options from $X,XXX.XX — alternative open-box entry point

Each product link href often points to a specific open-box condition such as excellent, good, or fair.

If the card has no Open-box as low as block, it shows See price in cart instead. That means no open-box offer is available.

## Pagination

First page has no cp param or cp=1. Subsequent pages use cp=2, cp=3, and so on.

Body text contains 1-18 of XX items. The XX value is the visible result count shown on that page's UI.

## Common pitfalls

1. using raw HTTP instead of Playwright — produces partial or incomplete data
2. navigating directly to search page with cookies — results in wrong region state
3. using broad selectors like .product-list-item.grid-view outside #main-results — includes featured or sponsored blocks
4. assuming the first card price belongs to the main open-box product link — causes wrong pairing
5. assuming the page is fully loaded after domcontentloaded without scrolling — cards do not hydrate
6. relying on customerZipCode, locDestZip, or sc-location-v2 instead of locStoreId — has no effect on result count
7. hardcoding the customerZipCode format with pipe-N suffix — Best Buy sets this internally

## File structure at /data/bestbuy

- bestbuy/browser_search.py — Playwright-backed extraction and HTML parsing
- scripts/hourly_available_report.py — CLI entrypoint for cron jobs
- requirements.txt — curl-cffi, playwright
- tests/test_browser_search.py — basic parser regression tests
- reports/initial_probe.md — first-pass connectivity findings
- scripts/probe_search_page.py — original HTTP-level probe script, kept for history

## Current working query example

The exact query used for the 5070 Ti laptop open-box search is stored in the repo README. Key params include:

- st — search term
- condition_facet — open-box only
- id — Computers and Tablets category
- parent_laptopscreensizesv_facet — screen size filters
- systemmemoryram_facet — high RAM filter

Change st and the filter facets to search for different laptop types or product categories.