#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bestbuy.search import FetchConfig, fetch_all_search_results, format_hourly_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Fetch every page for a Best Buy search query and print available laptops.'
    )
    parser.add_argument('--url', required=True, help='Best Buy search URL to scan')
    parser.add_argument('--max-pages', type=int, default=20, help='Max pages to scan')
    parser.add_argument(
        '--include-unavailable',
        action='store_true',
        help='Print every parsed result, not just currently available ones',
    )
    args = parser.parse_args()

    report = fetch_all_search_results(args.url, config=FetchConfig(), max_pages=args.max_pages)
    print(format_hourly_report(report, available_only=not args.include_unavailable))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
