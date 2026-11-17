"""Offline contract tests for BOATCAST original-exhibition records."""
import unittest
from datetime import date

from scripts.boatcast_oriten_smoke import url, parse


def sample(labels=("一　周", "まわり足", "直　線"), status=1, count=6):
    line = ["data=", f"{status}\t{len(labels)}", "\t".join(labels)]
    for lane in range(1, count + 1):
        vals = []
        for metric in labels:
            if "半周" in metric:
                vals.append(f"{18 + lane/10:.2f}")
            elif "一" in metric:
                vals.append(f"{36 + lane/10:.2f}")
            elif "まわり" in metric:
                vals.append(f"{7 + lane/10:.2f}")
            else:
                vals.append(f"{7.5 + lane/100:.2f}")
        line.append(f"{lane}\tテスト選手{lane}\t" + "\t".join(vals))
    return "\n".join(line).encode("utf-8")


class BoatcastDirectSmokeTests(unittest.TestCase):
    def test_source_url(self):
        self.assertEqual(
            url(date(2026, 11, 17), 18, 2),
            "https://race.boatcast.jp/txt/18/bc_oriten_20261117_18_02.txt",
        )

    def test_six_boats_three_metrics(self):
        result = parse(sample())
        self.assertEqual(len(result["boats"]), 6)
        self.assertEqual(result["metrics"], ["lap_time", "turn_time", "straight_time"])
        self.assertAlmostEqual(result["boats"][0]["lap_time"], 36.1)

    def test_kiryu_half_lap_is_not_lap(self):
        result = parse(sample(("半周ラップ", "まわり足", "直線")))
        self.assertEqual(result["metrics"][0], "half_lap_time")
        self.assertNotIn("lap_time", result["boats"][0])

    def test_two_metric_venue(self):
        result = parse(sample(("一周", "まわり足")))
        self.assertEqual(result["metrics"], ["lap_time", "turn_time"])
        self.assertNotIn("straight_time", result["boats"][0])

    def test_incomplete_rejected(self):
        with self.assertRaises(ValueError):
            parse(sample(count=5))

    def test_not_measured_rejected(self):
        with self.assertRaises(ValueError):
            parse(sample(status=2))

    def test_invalid_numeric_rejected(self):
        with self.assertRaises(ValueError):
            parse(sample().replace(b"36.10", b"999.0"))

    def test_invalid_source_rejected(self):
        with self.assertRaises(ValueError):
            parse(b"404 Not Found")


if __name__ == "__main__":
    unittest.main()
