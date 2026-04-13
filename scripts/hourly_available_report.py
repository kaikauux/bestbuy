#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bestbuy.browser_search import fetch_available_results_browser, format_browser_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Run a browser-backed Best Buy search and print currently available laptops.'
    )
    parser.add_argument('--url', required=True, help='Best Buy search URL to scan')
    parser.add_argument('--store', default='Union City', help='Store name to set before scanning')
    parser.add_argument('--max-pages', type=int, default=4, help='Max pages to scan')
    args = parser.parse_args()

    report = fetch_available_results_browser(
        args.url,
        store_name=args.store,
        max_pages=args.max_pages,
        headless=True,
    )
    print(format_browser_report(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
