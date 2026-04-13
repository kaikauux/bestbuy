from pathlib import Path
import unittest

from bestbuy.search import summarize_search_results


FIXTURE = Path(__file__).parent / 'fixtures' / 'searchpage.html'


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
        self.assertGreaterEqual(len(first['open_box_options']), 1)


if __name__ == '__main__':
    unittest.main()
