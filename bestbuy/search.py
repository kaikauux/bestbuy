from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

APOLLO_PREFIX = '(window[Symbol.for("ApolloSSRDataTransport")] ??= []).push('
SCRIPT_RE = re.compile(r'<script[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)


class BestBuyParseError(RuntimeError):
    pass


@dataclass
class FetchConfig:
    impersonate: str = 'chrome124'
    timeout: int = 30


def fetch_search_html(url: str, *, config: FetchConfig | None = None) -> str:
    from curl_cffi import requests

    cfg = config or FetchConfig()
    session = requests.Session(impersonate=cfg.impersonate)
    response = session.get(url, timeout=cfg.timeout, allow_redirects=True)
    response.raise_for_status()
    return response.text


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


def _extract_open_box_options(product: dict[str, Any]) -> list[dict[str, Any]]:
    options = []
    for option in product.get('openBoxOptions') or []:
        option_product = option.get('product') or {}
        option_price = option_product.get('price') or {}
        option_url = option_product.get('url') or {}
        options.append(
            {
                'condition': option.get('type'),
                'price': option_price.get('customerPrice'),
                'savings': option_price.get('openBoxSavings'),
                'url': option_url.get('pdp'),
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
                'button_state': _extract_button_state(product),
                'open_box_options': _extract_open_box_options(product),
            }
        )

    return {
        'search_tag': (detailed.get('track') or {}).get('searchTag'),
        'result_count': len(results),
        'results': results,
    }
