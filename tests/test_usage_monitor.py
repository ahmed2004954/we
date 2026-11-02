import unittest

from usage_monitor import PackageUsage, evaluate_alerts, parse_usage_text


class UsageParsingTests(unittest.TestCase):
    def test_multiple_quota_rows_are_parsed_with_names_and_values(self):
        page_text = """Home Internet
Main Quota
232.84 GB / 250 GB
Used 17.16 GB
GAME ON
35.78 GB / 40 GB
Used 4.22 GB"""

        self.assertEqual(
            parse_usage_text(page_text),
            [
                PackageUsage("Main Quota", 232.84, 250.0, 17.16),
                PackageUsage("GAME ON", 35.78, 40.0, 4.22),
            ],
        )

    def test_missing_usage_rows_fail_instead_of_returning_empty_success(self):
        with self.assertRaises(ValueError):
            parse_usage_text("Home Internet\nNo quota details available")


class AlertEvaluationTests(unittest.TestCase):
    def test_crossing_percentage_thresholds_alerts_once_per_threshold(self):
        previous = PackageUsage("Main Quota", 100, 250, 150)
        current = PackageUsage("Main Quota", 62.5, 250, 187.5)

        alert, state = evaluate_alerts(current, previous, {"thresholds": [25, 50]})

        self.assertEqual(alert, ["75%"])
        self.assertEqual(state["thresholds"], [25, 50, 75])

    def test_unchanged_usage_does_not_repeat_percentage_alert(self):
        previous = PackageUsage("Main Quota", 125, 250, 125)
        alert, state = evaluate_alerts(previous, previous, {"thresholds": [25, 50]})

        self.assertEqual(alert, [])
        self.assertEqual(state["thresholds"], [25, 50])

    def test_main_quota_alerts_for_each_two_gb_after_ninety_percent(self):
        previous = PackageUsage("Main Quota", 25, 250, 225)
        current = PackageUsage("Main Quota", 21, 250, 229)

        alert, state = evaluate_alerts(
            current,
            previous,
            {"thresholds": [25, 50, 75, 90], "two_gb_steps": 0, "ninety_used": 225},
            is_main_quota=True,
        )

        self.assertEqual(alert, ["2 GB after 90%", "4 GB after 90%"])
        self.assertEqual(state["two_gb_steps"], 2)

    def test_new_cycle_resets_percentage_and_two_gb_alerts(self):
        previous = PackageUsage("Main Quota", 10, 250, 240)
        renewed = PackageUsage("Main Quota", 245, 250, 5)

        alert, state = evaluate_alerts(
            renewed,
            previous,
            {"thresholds": [25, 50, 75, 90], "two_gb_steps": 3, "ninety_used": 225},
            is_main_quota=True,
        )

        self.assertEqual(alert, [])
        self.assertEqual(state["thresholds"], [])
        self.assertEqual(state["two_gb_steps"], 0)

    def test_additional_package_never_gets_two_gb_after_ninety_alert(self):
        previous = PackageUsage("GAME ON", 4, 40, 36)
        current = PackageUsage("GAME ON", 1.5, 40, 38.5)

        alert, state = evaluate_alerts(
            current,
            previous,
            {"thresholds": [25, 50, 75, 90]},
            is_main_quota=False,
        )

        self.assertEqual(alert, [])
        self.assertNotIn("two_gb_steps", state)


if __name__ == "__main__":
    unittest.main()
