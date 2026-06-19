import unittest

from review_metrics import calculate_pass_rate


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
        with self.assertRaisesRegex(ValueError, "total"):
            calculate_pass_rate(0, 0)

    def test_calculate_pass_rate_rejects_negative_passed(self):
        with self.assertRaisesRegex(ValueError, "passed"):
            calculate_pass_rate(-1, 10)

    def test_calculate_pass_rate_rejects_passed_above_total(self):
        with self.assertRaisesRegex(ValueError, "passed"):
            calculate_pass_rate(11, 10)

    def test_calculate_pass_rate_rejects_negative_total(self):
        with self.assertRaisesRegex(ValueError, "total"):
            calculate_pass_rate(0, -1)

    def test_calculate_pass_rate_rejects_non_integer_counts(self):
        cases = (
            (1.5, 10, "passed"),
            (None, 10, "passed"),
            (True, 10, "passed"),
            (1, "10", "total"),
            (1, 10.0, "total"),
        )
        for passed, total, field in cases:
            with self.subTest(passed=passed, total=total):
                with self.assertRaisesRegex(TypeError, field):
                    calculate_pass_rate(passed, total)

    def test_calculate_pass_rate_rounds_to_two_decimal_places(self):
        self.assertEqual(calculate_pass_rate(1, 7), 14.29)


if __name__ == "__main__":
    unittest.main()
