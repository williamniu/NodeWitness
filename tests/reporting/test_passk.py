import random
import unittest

from scripts.passk_report import pass_at_k, summarize


class PassAtK(unittest.TestCase):
    def test_closed_form(self):
        self.assertEqual(pass_at_k(5, 0, 1), 0.0)
        self.assertEqual(pass_at_k(5, 5, 5), 1.0)
        self.assertAlmostEqual(pass_at_k(5, 2, 1), 0.4)
        self.assertEqual(pass_at_k(5, 1, 5), 1.0)       # any pass in 5 draws of 5
        self.assertAlmostEqual(pass_at_k(10, 3, 5), 1 - 21 / 252)
        with self.assertRaises(ValueError):
            pass_at_k(3, 1, 5)

    def test_bootstrap_is_deterministic_and_brackets_the_estimate(self):
        rows = {t: [{"passed": p} for p in pattern] for t, pattern in
                {"a": [1, 1, 0, 1, 0], "b": [0, 0, 0, 0, 1], "c": [1, 1, 1, 1, 1]}.items()}
        first = summarize(rows, 1, random.Random("x"))
        self.assertEqual(first, summarize(rows, 1, random.Random("x")))
        low, high = first["ci95"]
        self.assertLessEqual(low, first["pass_at_k"])
        self.assertLessEqual(first["pass_at_k"], high)


if __name__ == "__main__":
    unittest.main()
