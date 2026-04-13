from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

APOLLO_PREFIX = '(window[Symbol.for("ApolloSSRDataTransport")] ??= []).push('
SCRIPT_RE = re.compile(r'<script[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
AVAILABLE_BUTTON_STATES = {'ADD_TO_CART', 'CHECK_STORES'}
DEFAULT_RESULTS_PER_PAGE = 18


class BestBuyParseError(RuntimeError):
    pass


@dataclass
class FetchConfig:
    impersonate: str = 'chrome124'
    timeout: int = 30


def create_session(*, config: FetchConfig | None = None):
    from curl_cffi import requests

    cfg = config or FetchConfig()
    return requests.Session(impersonate=cfg.impersonate)


def fetch_search_html(url: str, *, config: FetchConfig | None = None, session=None) -> str:
    cfg = config or FetchConfig()
    active_session = session or create_session(config=cfg)
    response = active_session.get(url, timeout=cfg.timeout, allow_redirects=True)
    response.raise_for_status()
    return response.text


def set_page_number(url: str, page_number: int) -> str:
    if page_number < 1:
        raise ValueError('page_number must be >= 1')

    parts = urlsplit(url)
    params = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'cp']
    if page_number != 1:
        params.append(('cp', str(page_number)))
    query = urlencode(params, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _load_apollo_payload(script_content: str) -> dict[str, Any] | None:
    if not script_content.startswith(APOLLO_PREFIX):
        return None
    if not script_content.endswith(')'):
        return None

    payload = script_content[len(APOLLO_PREFIX):-1]
    payload = payload.replace(':undefined', ':null')
    payload = payload.replace('[undefined', '[null')
    payload = payload.replace(',undefined', ',null')

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _iter_apollo_payloads(html: str):
    for script_content in SCRIPT_RE.findall(html):
        payload = _load_apollo_payload(script_content)
        if payload is not None:
            yield payload


def extract_detailed_product_search(html: str) -> dict[str, Any]:
    for payload in _iter_apollo_payloads(html):
        rehydrate = payload.get('rehydrate')
        if not isinstance(rehydrate, dict):
            continue
        for value in rehydrate.values():
            if not isinstance(value, dict):
                continue
            data = value.get('data')
            if not isinstance(data, dict):
                continue
            detailed = data.get('detailedProductSearch')
            if isinstance(detailed, dict) and isinstance(detailed.get('documents'), list):
                return detailed
    raise BestBuyParseError('Could not find detailedProductSearch payload in HTML')


def _extract_button_state(product: dict[str, Any]) -> str | None:
    fulfillment = product.get('fulfillmentOptions') or {}
    button_states = fulfillment.get('buttonStates') or []
    if not button_states:
        return None
    state = button_states[0]
    return state.get('displayText') or state.get('buttonState')


def _normalize_button_state(button_state: str | None) -> str | None:
    if not button_state:
        return None
    return button_state.strip().replace('-', '_').replace(' ', '_').upper()


def is_available_button_state(button_state: str | None) -> bool:
    normalized = _normalize_button_state(button_state)
    return normalized in AVAILABLE_BUTTON_STATES


def _extract_open_box_options(product: dict[str, Any]) -> list[dict[str, Any]]:
    options = []
    for option in product.get('openBoxOptions') or []:
        option_product = option.get('product') or {}
        option_price = option_product.get('price') or {}
        option_url = option_product.get('url') or {}
        option_button_state = _extract_button_state(option_product)
        options.append(
            {
                'condition': option.get('type'),
                'price': option_price.get('customerPrice'),
                'savings': option_price.get('openBoxSavings'),
                'url': option_url.get('pdp'),
                'button_state': option_button_state,
                'available': is_available_button_state(option_button_state),
            }
        )
    return options


def summarize_search_results(html: str) -> dict[str, Any]:
    detailed = extract_detailed_product_search(html)
    documents = detailed.get('documents') or []
    results = []

    for document in documents:
        product = document.get('product') or {}
        name = product.get('name') or {}
        price = product.get('price') or {}
        review = product.get('reviewInfo') or {}
        image = product.get('primaryImage') or {}
        url = product.get('url') or {}
        manufacturer = product.get('manufacturer') or {}
        condition = product.get('condition') or {}
        button_state = _extract_button_state(product)
        open_box_options = _extract_open_box_options(product)
        results.append(
            {
                'sku_id': product.get('skuId'),
                'title': name.get('title') or name.get('short'),
                'short_name': name.get('short'),
                'brand': product.get('brand'),
                'model_number': manufacturer.get('modelNumber'),
                'condition': condition.get('type'),
                'customer_price': price.get('customerPrice'),
                'regular_price': price.get('regularPrice'),
                'displayable_customer_price': price.get('displayableCustomerPrice'),
                'price_with_cart': price.get('priceWithCart'),
                'product_url': url.get('pdp') or url.get('skuSpecificUrl') or url.get('relativePdp'),
                'sku_url': url.get('skuSpecificUrl'),
                'image_url': image.get('href') or image.get('piscesHref'),
                'average_rating': review.get('averageRating'),
                'review_count': review.get('reviewCount'),
                'button_state': button_state,
                'available': is_available_button_state(button_state) or any(
                    option['available'] for option in open_box_options
                ),
                'open_box_options': open_box_options,
            }
        )

    return {
        'search_tag': (detailed.get('track') or {}).get('searchTag'),
        'result_count': len(results),
        'results': results,
    }


def fetch_search_page_summary(
    url: str,
    *,
    config: FetchConfig | None = None,
    session=None,
    page_number: int | None = None,
) -> dict[str, Any]:
    html = fetch_search_html(url, config=config, session=session)
    summary = summarize_search_results(html)
    summary['source_url'] = url
    summary['page_number'] = page_number
    return summary


def fetch_all_search_results(
    url: str,
    *,
    config: FetchConfig | None = None,
    max_pages: int = 20,
) -> dict[str, Any]:
    cfg = config or FetchConfig()
    session = create_session(config=cfg)
    seen_skus: set[str] = set()
    results: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []

    for page_number in range(1, max_pages + 1):
        page_url = set_page_number(url, page_number)
        try:
            page_summary = fetch_search_page_summary(
                page_url,
                config=cfg,
                session=session,
                page_number=page_number,
            )
        except BestBuyParseError as exc:
            if page_number == 1:
                raise
            warnings.append(f'Page {page_number} could not be parsed: {exc}')
            break
        page_results = page_summary['results']
        if not page_results:
            break

        new_results = []
        for result in page_results:
            sku_id = result.get('sku_id')
            if sku_id and sku_id in seen_skus:
                continue
            if sku_id:
                seen_skus.add(sku_id)
            new_results.append(result)

        pages.append(
            {
                'page_number': page_number,
                'url': page_url,
                'result_count': len(page_results),
                'new_result_count': len(new_results),
                'search_tag': page_summary.get('search_tag'),
            }
        )
        results.extend(new_results)

        if not new_results or len(page_results) < DEFAULT_RESULTS_PER_PAGE:
            break

    return {
        'query_url': url,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'page_count': len(pages),
        'result_count': len(results),
        'available_count': len(filter_available_results(results)),
        'pages': pages,
        'warnings': warnings,
        'results': results,
    }


def filter_available_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [result for result in results if result.get('available')]


def _format_price(value: float | int | None) -> str:
    if value is None:
        return 'n/a'
    if float(value).is_integer():
        return f'${int(value)}'
    return f'${value:.2f}'


def format_hourly_report(report: dict[str, Any], *, available_only: bool = True) -> str:
    results = report['results']
    if available_only:
        results = filter_available_results(results)

    lines = [
        'Best Buy hourly laptop report',
        f"Generated: {report['fetched_at']}",
        f"Pages scanned: {report['page_count']}",
        f"Results returned: {report['result_count']}",
        f"Results shown: {len(results)}",
        f"Query: {report['query_url']}",
    ]

    for warning in report.get('warnings', []):
        lines.append(f"Warning: {warning}")

    lines.append('')

    if not results:
        lines.append('No currently available laptops matched this query.')
        return '\n'.join(lines)

    for index, result in enumerate(results, start=1):
        lines.append(
            f"{index}. {result['title']} — {_format_price(result['customer_price'])} — {result.get('button_state') or 'Unknown'}"
        )
        lines.append(f"   SKU: {result.get('sku_id')} | Model: {result.get('model_number') or 'n/a'}")
        if result.get('average_rating') is not None:
            lines.append(
                f"   Rating: {result['average_rating']} ({result.get('review_count') or 0} reviews)"
            )
        open_box_available = [option for option in result.get('open_box_options', []) if option.get('available')]
        if open_box_available:
            rendered_options = '; '.join(
                f"{option['condition']} {_format_price(option['price'])}"
                for option in open_box_available
            )
            lines.append(f"   Open-box: {rendered_options}")
        elif result.get('open_box_options'):
            rendered_options = '; '.join(
                f"{option['condition']} {_format_price(option['price'])} ({option.get('button_state') or 'Unknown'})"
                for option in result['open_box_options']
            )
            lines.append(f"   Open-box seen: {rendered_options}")
        lines.append(f"   URL: {result.get('product_url')}")
        lines.append('')

    return '\n'.join(lines).rstrip()
