from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

HOME_URL = 'https://www.bestbuy.com/'
RESULT_CARD_SELECTOR = '#main-results .product-list-item.grid-view'
DEFAULT_GEOLOCATION = {'latitude': 37.5934, 'longitude': -122.0438}
DEFAULT_STORE_COOKIE = '1021'


@dataclass
class BrowserResult:
    title: str
    href: str
    open_box_price: str | None
    regular_price: str | None
    savings: str | None
    condition: str | None
    rating: float | None
    review_count: int | None
    available: bool
    availability_note: str | None
    raw_text: str


@dataclass
class BrowserReport:
    query_url: str
    fetched_at: str
    store_name: str
    result_count_label: int | None
    page_count: int
    available_count: int
    pickup_summary: str | None
    shipping_summary: str | None
    shipping_zip: str | None
    results: list[dict[str, Any]]


def set_page_number(url: str, page_number: int) -> str:
    parts = urlsplit(url)
    params = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'cp']
    if page_number > 1:
        params.append(('cp', str(page_number)))
    query = urlencode(params, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def parse_card_text(text: str, href: str) -> BrowserResult | None:
    clean = text.strip()
    if not clean:
        return None

    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    if not lines:
        return None

    title = lines[0]
    if title in {'Sponsored', 'See price in cart'}:
        return None

    rating_match = re.search(r'Rating\s+([0-9.]+) out of 5 stars with ([0-9,]+) reviews', clean)
    price_match = re.search(r'Open-box as low as\s*\$([0-9,]+(?:\.\d{2})?)', clean, re.IGNORECASE)

    availability_note = None
    availability_patterns = [
        r'(Several available in your area\.)',
        r'(Ready in \d+ hour[s]?\.?|Ready today\.?|Ready tomorrow\.?|Ships by .*?)',
    ]
    for pattern in availability_patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            availability_note = match.group(1)
            break

    has_open_box_action = 'Shop Open-Box' in clean or price_match is not None
    unavailable = 'Unavailable' in clean and not has_open_box_action

    # Extract condition from the URL href (e.g. condition=excellent, condition=good, condition=fair)
    condition = None
    cond_match = re.search(r'condition=(excellent|good|fair)', href, re.IGNORECASE)
    if cond_match:
        condition = cond_match.group(1).capitalize()

    return BrowserResult(
        title=title,
        href=href,
        open_box_price=price_match.group(1) if price_match else None,
        regular_price=None,
        savings=None,
        condition=condition,
        rating=float(rating_match.group(1)) if rating_match else None,
        review_count=int(rating_match.group(2).replace(',', '')) if rating_match else None,
        available=has_open_box_action and not unavailable,
        availability_note=availability_note,
        raw_text=clean,
    )


def _find_all_key(obj, key, depth=0, max_depth=12) -> list:
    """Find all values for a given key anywhere in a nested structure."""
    if depth > max_depth:
        return []
    results = []
    if isinstance(obj, dict):
        if key in obj:
            results.append(obj[key])
        for v in obj.values():
            results.extend(_find_all_key(v, key, depth + 1, max_depth))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_find_all_key(item, key, depth + 1, max_depth))
    return results


def _extract_open_box_entries(product: dict, fallback_sku_id: str | None = None) -> list[dict[str, Any]]:
    """Extract open-box option entries from a product dict."""
    ob_options = product.get('openBoxOptions', [])
    if not isinstance(ob_options, list):
        return []

    sku_id = product.get('skuId') or fallback_sku_id
    entries = []
    for ob in ob_options:
        ob_product = ob.get('product', {})
        ob_price = ob_product.get('price', {})
        ob_sku = ob_product.get('skuId') or sku_id
        ob_url_obj = ob_product.get('url', {})
        ob_url = ob_url_obj.get('pdp', '') if isinstance(ob_url_obj, dict) else ''

        entry = {
            'condition': ob.get('type'),  # Excellent, Good, Fair
            'customer_price': ob_price.get('customerPrice'),
            'open_box_savings': ob_price.get('openBoxSavings'),
            'sku_id': ob_sku,
            'url': ob_url,
        }
        entries.append(entry)
    return entries


def parse_apollo_ssr(html: str) -> dict[str, dict[str, Any]]:
    """Extract open-box pricing metadata from Apollo SSR payloads in page HTML.

    Returns a dict keyed by skuId, each value containing:
      - regular_price: the new/product regular price (float)
      - open_box_options: list of dicts with keys condition, customer_price, open_box_savings, sku_id, url

    Handles two payload structures:
    1. Page 1: detailedProductSearch.documents[].product (with .price and .openBoxOptions)
    2. Page 2+: events[].result.data.productBySkuId.buyingOptions[].product (with .openBoxOptions)
       Also rehydrate entries with productBySkuId.
    """
    apollo_pattern = r'\(window\[Symbol\.for\("ApolloSSRDataTransport"\)\]\s*\?\?=\s*\[\]\)\.push\((.+?)\);?\s*</script>'
    matches = re.findall(apollo_pattern, html, re.DOTALL)

    sku_map: dict[str, dict[str, Any]] = {}

    for payload_text in matches:
        # Normalize JS undefined to JSON null
        normalized = payload_text
        normalized = re.sub(r':undefined', ':null', normalized)
        normalized = re.sub(r'\[undefined', '[null', normalized)
        normalized = re.sub(r',undefined', ',null', normalized)

        try:
            data = json.loads(normalized)
        except json.JSONDecodeError:
            continue

        # --- Path 1: detailedProductSearch (page 1 style) ---
        for search_data in _find_all_key(data, 'detailedProductSearch'):
            if not isinstance(search_data, dict):
                continue
            documents = search_data.get('documents')
            if not isinstance(documents, list):
                continue

            for doc in documents:
                product = doc.get('product')
                if not product or not isinstance(product, dict):
                    continue

                sku_id = product.get('skuId')
                if not sku_id:
                    continue

                # Get regular price from the product-level price object
                regular_price = None
                price_obj = product.get('price', {})
                if isinstance(price_obj, dict):
                    regular_price = price_obj.get('displayableRegularPrice') or price_obj.get('customerPrice')

                open_box_entries = _extract_open_box_entries(product, sku_id)

                sku_map[sku_id] = {
                    'regular_price': regular_price,
                    'open_box_options': open_box_entries,
                }

        # --- Path 2: productBySkuId (page 2+ style, in both rehydrate and events) ---
        for pbs_obj in _find_all_key(data, 'productBySkuId'):
            if not isinstance(pbs_obj, dict):
                continue

            # Extract SKU ID and regular price from the top-level productBySkuId
            sku_id = pbs_obj.get('skuId')
            if not sku_id:
                continue

            # Try to get regular price from the top-level object
            regular_price = None
            price_obj = pbs_obj.get('price', {})
            if isinstance(price_obj, dict):
                regular_price = price_obj.get('displayableRegularPrice') or price_obj.get('customerPrice')

            # buyingOptions contains products with openBoxOptions
            buying_options = pbs_obj.get('buyingOptions', [])
            if isinstance(buying_options, list):
                all_ob_entries = []
                for bo in buying_options:
                    bo_product = bo.get('product', {})
                    if not isinstance(bo_product, dict):
                        continue
                    bo_sku = bo_product.get('skuId') or sku_id

                    # Get regular price from buying option product if not yet found
                    if regular_price is None:
                        bo_price = bo_product.get('price', {})
                        if isinstance(bo_price, dict):
                            regular_price = bo_price.get('displayableRegularPrice') or bo_price.get('customerPrice')

                    entries = _extract_open_box_entries(bo_product, bo_sku)
                    all_ob_entries.extend(entries)

                if all_ob_entries or sku_id not in sku_map:
                    # Only overwrite if we found new data or the SKU wasn't already mapped
                    existing = sku_map.get(sku_id, {'regular_price': None, 'open_box_options': []})
                    if all_ob_entries:
                        # Merge open_box_options, deduplicating by condition+sku_id
                        existing_conditions = {
                            (e['condition'], e['sku_id']) for e in existing['open_box_options']
                            if e.get('condition') and e.get('sku_id')
                        }
                        for entry in all_ob_entries:
                            key = (entry.get('condition'), entry.get('sku_id'))
                            if key not in existing_conditions:
                                existing['open_box_options'].append(entry)
                                existing_conditions.add(key)

                    if regular_price is not None:
                        existing['regular_price'] = regular_price
                    elif existing.get('regular_price') is None:
                        existing['regular_price'] = regular_price

                    sku_map[sku_id] = existing
            else:
                # No buyingOptions, but still register the SKU with whatever we have
                if sku_id not in sku_map:
                    sku_map[sku_id] = {
                        'regular_price': regular_price,
                        'open_box_options': [],
                    }

    # --- Path 3: React SSR streaming data (page 2+ fallback) ---
    # Best Buy embeds open-box pricing in RSC streaming HTML when Apollo payloads are sparse.
    ob_pattern = r'"customerPrice":([\d.]+),"skuId":"(\d+)","openBoxSavings":([\d.]+),"openBoxCondition":(\d+)'
    for price_str, sku_id, savings_str, cond_code in re.findall(ob_pattern, html):
        cond_name = {0: 'Fair', 1: 'Good', 2: 'Excellent'}.get(int(cond_code))
        if not cond_name:
            continue
        if sku_id not in sku_map:
            sku_map[sku_id] = {'regular_price': None, 'open_box_options': []}
        existing = sku_map[sku_id]
        # Set regular price from displayableRegularPrice if found nearby
        reg_pattern = rf'"displayableRegularPrice":([\d.]+).*?"skuId":"{sku_id}"'
        reg_match = re.search(reg_pattern, html)
        if reg_match and existing.get('regular_price') is None:
            existing['regular_price'] = float(reg_match.group(1))
        # Add open-box entry if not already present for this condition
        existing_conditions = {
            (e['condition'], e['sku_id']) for e in existing['open_box_options']
            if e.get('condition') and e.get('sku_id')
        }
        entry_key = (cond_name, sku_id)
        if entry_key not in existing_conditions:
            existing['open_box_options'].append({
                'condition': cond_name,
                'customer_price': float(price_str),
                'open_box_savings': float(savings_str),
                'sku_id': sku_id,
                'url': '',
            })
            existing_conditions.add(entry_key)

    # Fallback: compute regular_price from customerPrice + openBoxSavings if still missing
    for sku_id, data in sku_map.items():
        if data.get('regular_price') is None:
            for ob in data.get('open_box_options', []):
                cp = ob.get('customer_price')
                sv = ob.get('open_box_savings')
                if cp is not None and sv is not None:
                    data['regular_price'] = round(cp + sv, 2)
                    break

    return sku_map


def _extract_body_meta(body_text: str) -> tuple[int | None, str | None, str | None, str | None]:
    result_count = None
    count_match = re.search(r'5070 Ti laptop in .*?\((\d+)\)', body_text)
    if count_match:
        result_count = int(count_match.group(1))

    pickup_summary = None
    shipping_summary = None
    shipping_zip = None

    pickup_match = re.search(r'Pickup · ([^\n]+)', body_text)
    if pickup_match:
        pickup_summary = pickup_match.group(1).strip()

    shipping_match = re.search(r'Shipping · ([^\n]+)\n(\d{5})', body_text)
    if shipping_match:
        shipping_summary = shipping_match.group(1).strip()
        shipping_zip = shipping_match.group(2)

    return result_count, pickup_summary, shipping_summary, shipping_zip


def _scroll_page(page) -> None:
    for y in [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]:
        page.evaluate(f'window.scrollTo(0, {y})')
        page.wait_for_timeout(1000)


def _extract_results_from_page(page) -> list[BrowserResult]:
    collected: dict[str, BrowserResult] = {}
    for _ in range(2):
        cards = page.locator(RESULT_CARD_SELECTOR)
        for index in range(cards.count()):
            card = cards.nth(index)
            try:
                text = card.inner_text().strip()
            except Exception:
                continue
            links = card.locator('a.product-list-item-link').evaluate_all(
                "els => els.map(e => ({href: e.href, text: (e.innerText || '').trim()}))"
            )
            href = links[0]['href'] if links else None
            if not href:
                continue
            parsed = parse_card_text(text, href)
            if parsed is not None and parsed.available:
                collected[href] = parsed
        page.wait_for_timeout(1000)
    return list(collected.values())


def _enrich_with_apollo(results: list[BrowserResult], sku_map: dict[str, dict[str, Any]]) -> None:
    """Enrich BrowserResult items with regular_price, savings, and condition from Apollo data.

    Matches by extracting skuId from the result href, then finding the matching
    open-box condition in the Apollo data.
    """
    for result in results:
        # Extract SKU ID from href (patterns like /sku/6619196/ or sku/6619196)
        sku_match = re.search(r'/sku/(\d+)', result.href)
        if not sku_match:
            continue
        sku_id = sku_match.group(1)

        apollo_data = sku_map.get(sku_id)
        if not apollo_data:
            continue

        # Set regular price
        if apollo_data.get('regular_price') is not None:
            result.regular_price = f"{apollo_data['regular_price']:,.2f}"

        # Find the matching open-box condition
        condition_lower = (result.condition or '').lower()
        for ob in apollo_data.get('open_box_options', []):
            ob_cond_lower = (ob.get('condition') or '').lower()
            if ob_cond_lower == condition_lower:
                if ob.get('open_box_savings') is not None:
                    result.savings = f"{ob['open_box_savings']:,.2f}"
                if ob.get('customer_price') is not None and result.open_box_price is None:
                    result.open_box_price = f"{ob['customer_price']:,.2f}"
                # If we don't have condition from URL, use Apollo's
                if not result.condition and ob.get('condition'):
                    result.condition = ob.get('condition')
                break


def fetch_available_results_browser(
    search_url: str,
    *,
    store_name: str = 'Union City',
    store_cookie_id: str = DEFAULT_STORE_COOKIE,
    geolocation: dict[str, float] | None = None,
    max_pages: int = 4,
    headless: bool = True,
):
    from playwright.sync_api import sync_playwright

    fetched_at = datetime.now(timezone.utc).isoformat()
    effective_geolocation = geolocation or DEFAULT_GEOLOCATION
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        all_results: list[BrowserResult] = []
        result_count_label = None
        pickup_summary = None
        shipping_summary = None
        shipping_zip = None
        pages_scanned = 0
        combined_sku_map: dict[str, dict[str, Any]] = {}

        for page_number in range(1, max_pages + 1):
            context = browser.new_context(
                viewport={'width': 1440, 'height': 2200},
                locale='en-US',
                geolocation=effective_geolocation,
                permissions=['geolocation'],
            )
            context.add_cookies([
                {'name': 'locStoreId', 'value': store_cookie_id, 'domain': '.bestbuy.com', 'path': '/'},
            ])
            page = context.new_page()

            page.goto(HOME_URL, wait_until='domcontentloaded', timeout=120000)
            page.wait_for_timeout(8000)
            page.goto(set_page_number(search_url, page_number), wait_until='domcontentloaded', timeout=120000)
            page.wait_for_timeout(12000)
            _scroll_page(page)
            page_results = _extract_results_from_page(page)

            # Extract Apollo SSR data from this page's HTML
            html = page.content()
            page_sku_map = parse_apollo_ssr(html)
            combined_sku_map.update(page_sku_map)

            body_text = page.locator('body').inner_text()
            if result_count_label is None:
                result_count_label, pickup_summary, shipping_summary, shipping_zip = _extract_body_meta(body_text)
            context.close()
            if not page_results:
                break
            pages_scanned += 1
            all_results.extend(page_results)

        browser.close()

    # Enrich results with Apollo data
    _enrich_with_apollo(all_results, combined_sku_map)

    deduped: list[dict[str, Any]] = []
    seen = set()
    for result in all_results:
        key = result.href
        if key in seen:
            continue
        seen.add(key)
        deduped.append(asdict(result))

    return BrowserReport(
        query_url=search_url,
        fetched_at=fetched_at,
        store_name=store_name,
        result_count_label=result_count_label,
        page_count=pages_scanned,
        available_count=len(deduped),
        pickup_summary=pickup_summary,
        shipping_summary=shipping_summary,
        shipping_zip=shipping_zip,
        results=deduped,
    )


def format_browser_report(report: BrowserReport) -> str:
    lines = [
        'Best Buy hourly laptop report',
        f'Generated: {report.fetched_at}',
        f'Store context: {report.store_name} (locStoreId cookie)',
    ]
    if report.result_count_label is not None:
        lines.append(f'Results on Best Buy page: {report.result_count_label}')
    lines.extend(
        [
            f'Pages scanned: {report.page_count}',
            f'Currently available items found: {report.available_count}',
            f'Pickup: {report.pickup_summary or "n/a"}',
            f'Shipping: {report.shipping_summary or "n/a"}',
            f'Shipping ZIP shown by site: {report.shipping_zip or "n/a"}',
            f'Query: {report.query_url}',
            '',
        ]
    )

    if not report.results:
        lines.append('No currently available laptops found.')
        return '\n'.join(lines)

    for index, result in enumerate(report.results, start=1):
        price = f"${result['open_box_price']}" if result.get('open_box_price') else 'n/a'
        savings = ''
        if result.get('savings'):
            savings = f" (save ${result['savings']})"
        condition = ''
        if result.get('condition'):
            condition = f" [{result['condition']}]"
        rating = ''
        if result.get('rating') is not None:
            rating = f" | Rating: {result['rating']} ({result.get('review_count') or 0} reviews)"
        note = f" | {result['availability_note']}" if result.get('availability_note') else ''
        lines.append(f"{index}. {result['title']} — {price}{savings}{condition}{rating}{note}")
        lines.append(f"   URL: {result['href']}")
        if result.get('regular_price'):
            lines.append(f"   Regular price: ${result['regular_price']}")
        lines.append('')

    return '\n'.join(lines).rstrip()
