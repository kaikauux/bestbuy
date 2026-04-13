import unittest

from bestbuy.browser_search import parse_card_text


SAMPLE_CARD = '''ASUS - ROG Zephyrus G14 14" 3K OLED 120Hz Gaming Laptop - Copilot+ PC - AMD Ryzen AI 9 HX - 32GB RAM - NVIDIA RTX 5070 Ti - 1TB - Platinum White

Rating 4.5 out of 5 stars with 443 reviews

4.5
(443 reviews)
Open-box as low as
$1,605.99
$1,605.99
Open-Box
Several available in your area.
Shop Open-Box
Compare'''


class BrowserSearchTests(unittest.TestCase):
    def test_parse_card_text(self):
        result = parse_card_text(SAMPLE_CARD, 'https://example.com/product/openbox')
        assert result is not None
        self.assertEqual(result.title.split(' - ')[0], 'ASUS')
        self.assertEqual(result.open_box_price, '1,605.99')
        self.assertEqual(result.rating, 4.5)
        self.assertEqual(result.review_count, 443)
        self.assertTrue(result.available)
        self.assertEqual(result.availability_note, 'Several available in your area.')


if __name__ == '__main__':
    unittest.main()
