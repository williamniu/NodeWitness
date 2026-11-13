import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


    def test_pass_at_k_above_one_is_not_biased_down_by_trial_resampling(self):
        rows = {"a": [{"passed": p} for p in [1, 0, 0, 0, 0]]}
        result = summarize(rows, 5, random.Random("y"))
        self.assertEqual(result, {"pass_at_k": 1.0, "ci95": [1.0, 1.0]})


class FrozenD5Report(unittest.TestCase):
    def test_committed_report_regenerates_from_committed_trials(self):
        root = Path(__file__).resolve().parents[2]
        for experiment in ("d5", "d5-pinned"):
            with self.subTest(experiment=experiment), tempfile.TemporaryDirectory() as out:
                subprocess.run([sys.executable, "scripts/passk_report.py", experiment, "--trials", "results/%s/trials" % experiment,
                                "--out", out], cwd=root, check=True, capture_output=True)
                for name in (experiment + ".json", experiment + ".md"):
                    self.assertEqual((Path(out) / name).read_bytes(), (root / "results/passk" / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
