#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bestbuy.search import FetchConfig, fetch_search_html, summarize_search_results


def main() -> int:
    parser = argparse.ArgumentParser(description='Fetch and parse a Best Buy search page.')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--url', help='Best Buy search URL to fetch live')
    source.add_argument('--html', help='Path to previously saved HTML')
    parser.add_argument('--save-html', help='Optional path to save fetched HTML')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    args = parser.parse_args()

    if args.url:
        html = fetch_search_html(args.url, config=FetchConfig())
        if args.save_html:
            Path(args.save_html).write_text(html, encoding='utf-8')
    else:
        html = Path(args.html).read_text(encoding='utf-8', errors='ignore')

    summary = summarize_search_results(html)
    print(json.dumps(summary, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
