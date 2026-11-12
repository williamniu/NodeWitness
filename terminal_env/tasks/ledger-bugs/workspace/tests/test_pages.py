import unittest

from ledger.pages import page


class PageTests(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(page(list(range(10)), 1, 3), [0, 1, 2])

    def test_last_partial_page(self):
        self.assertEqual(page(list(range(10)), 4, 3), [9])


if __name__ == "__main__":
    unittest.main()
