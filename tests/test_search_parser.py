from pathlib import Path
import unittest

from bestbuy.search import (
    filter_available_results,
    format_hourly_report,
    set_page_number,
    summarize_search_results,
)


FIXTURE = Path(__file__).parent / 'fixtures' / 'searchpage.html'
QUERY_URL = (
    'https://www.bestbuy.com/site/searchpage.jsp?id=pcat17071&'
    'qp=parent_laptopscreensizesv_facet%3DScreen+Size%7E14%22+-+15.9%22%5E'
    'parent_laptopscreensizesv_facet%3DScreen+Size%7E12%22+-+13.9%22%5E'
    'condition_facet%3DOpen-Box%7EOpen-Box%5E'
    'systemmemoryram_facet%3DRAM%7E32+gigabytes%5E'
    'systemmemoryram_facet%3DRAM%7E64+gigabytes%5E'
    'systemmemoryram_facet%3DRAM%7E128+gigabytes%5E'
    'systemmemoryram_facet%3DRAM%7E36+gigabytes&st=5070+Ti+laptop'
)


class SearchParserTests(unittest.TestCase):
    def test_parses_saved_search_fixture(self):
        html = FIXTURE.read_text(encoding='utf-8', errors='ignore')
        summary = summarize_search_results(html)

        self.assertEqual(summary['result_count'], 4)
        self.assertTrue(summary['search_tag'])

        first = summary['results'][0]
        self.assertEqual(first['sku_id'], '6613954')
        self.assertIn('5070 Ti', first['title'])
        self.assertEqual(first['button_state'], 'Add to Cart')
        self.assertTrue(first['available'])
        self.assertGreaterEqual(len(first['open_box_options']), 1)
        self.assertIn('button_state', first['open_box_options'][0])
        self.assertIn('available', first['open_box_options'][0])

    def test_filters_available_results(self):
        html = FIXTURE.read_text(encoding='utf-8', errors='ignore')
        summary = summarize_search_results(html)
        available = filter_available_results(summary['results'])
        self.assertEqual(len(available), 4)

    def test_formats_hourly_report(self):
        html = FIXTURE.read_text(encoding='utf-8', errors='ignore')
        summary = summarize_search_results(html)
        report = {
            'fetched_at': '2026-04-13T01:00:00+00:00',
            'page_count': 1,
            'result_count': summary['result_count'],
            'query_url': QUERY_URL,
            'results': summary['results'],
        }
        rendered = format_hourly_report(report)
        self.assertIn('Best Buy hourly laptop report', rendered)
        self.assertIn('ROG Zephyrus G14', rendered)
        self.assertIn('Open-box:', rendered)

    def test_sets_page_number(self):
        self.assertNotIn('cp=', set_page_number(QUERY_URL, 1))
        self.assertIn('cp=2', set_page_number(QUERY_URL, 2))


if __name__ == '__main__':
    unittest.main()
