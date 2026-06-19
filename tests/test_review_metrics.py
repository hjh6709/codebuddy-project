import unittest

from src.review_metrics import calculate_pass_rate


class ReviewMetricsTests(unittest.TestCase):
    def test_calculate_pass_rate_returns_percentage(self):
        self.assertEqual(
            calculate_pass_rate(8, 10),
            80.0,
        )

    def test_calculate_pass_rate_handles_boundaries_and_rounding(self):
        self.assertEqual(calculate_pass_rate(10, 10), 100.0)
        self.assertEqual(calculate_pass_rate(0, 10), 0.0)
        self.assertEqual(calculate_pass_rate(1, 3), 33.33)

    def test_calculate_pass_rate_rejects_zero_total(self):
        try:
            calculate_pass_rate(0, 0)
        except ValueError as exc:
            self.assertRegex(str(exc), "total")
        except ZeroDivisionError:
            self.fail("zero total must raise ValueError")
        else:
            self.fail("zero total must be rejected")

    def test_calculate_pass_rate_rejects_negative_passed(self):
        with self.assertRaisesRegex(ValueError, "passed"):
            calculate_pass_rate(-1, 10)

    def test_calculate_pass_rate_rejects_passed_above_total(self):
        with self.assertRaisesRegex(ValueError, "passed"):
            calculate_pass_rate(11, 10)


if __name__ == "__main__":
    unittest.main()
