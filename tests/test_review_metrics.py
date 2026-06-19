import importlib
import importlib.util
import unittest


class ReviewMetricsTests(unittest.TestCase):
    def test_calculate_pass_rate_returns_percentage(self):
        spec = importlib.util.find_spec("src.review_metrics")
        self.assertIsNotNone(spec)
        review_metrics = importlib.import_module("src.review_metrics")

        self.assertEqual(
            review_metrics.calculate_pass_rate(8, 10),
            80.0,
        )


if __name__ == "__main__":
    unittest.main()
