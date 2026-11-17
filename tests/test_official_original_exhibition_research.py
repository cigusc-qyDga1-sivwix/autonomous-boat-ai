"""Offline parser safety tests; no network or forecast writes."""
import unittest
from datetime import date

from scripts.official_original_exhibition_research import (
    official_url, parse_official,
)

DAY = date(2026, 11, 11)


def sample_html(*, missing=False, stale=False, invalid=False):
    lines = [
        "<html><body>",
        "<h1>11/10(火) 11R</h1>" if stale else "<h1>11/11(水) 11R</h1>",
        "<table><tr><th>コース</th><th>枠番</th><th>展示タイム</th>"
        "<th>一周</th><th>まわり足</th><th>直線</th></tr>",
    ]
    for lane in range(1, 7 if missing else 7):
        if missing and lane == 6:
            continue
        turn = "－" if invalid and lane == 3 else f"{5.04 + lane * .02:.2f}"
        lines.append(
            f"<tr><td>{lane}</td><td>{lane}</td>"
            f"<td>6.7{lane}</td><td>37.{lane}2</td>"
            f"<td>{turn}</td><td>6.{lane}3</td></tr>"
        )
    lines.extend(["</table>", "</body></html>"])
    return "".join(lines)


class OfficialExhibitionResearchTests(unittest.TestCase):
    def test_official_url_is_fixed_to_provider_and_venue(self):
        self.assertEqual(
            official_url(DAY, 11),
            "https://www.gamagori-kyotei.com/asp/gamagori/sp/kyogi/"
            "kyogihtml/recomend/recomend202611110711.htm",
        )
        with self.assertRaises(ValueError):
            official_url(DAY, 13)

    def test_six_boat_measured_numbers_are_parsed(self):
        boats = parse_official(sample_html(), DAY, 11)
        self.assertEqual(len(boats), 6)
        self.assertEqual([b["lane"] for b in boats], list(range(1, 7)))
        self.assertEqual(boats[0]["lap_time"], 37.12)
        self.assertEqual(boats[5]["straight_time"], 6.63)

    def test_fail_closed_on_stale_date(self):
        with self.assertRaisesRegex(ValueError, "race date"):
            parse_official(sample_html(stale=True), DAY, 11)

    def test_fail_closed_on_missing_sixth_boat(self):
        with self.assertRaisesRegex(ValueError, "six-boat"):
            parse_official(sample_html(missing=True), DAY, 11)

    def test_fail_closed_on_missing_metric(self):
        with self.assertRaisesRegex(ValueError, "invalid original"):
            parse_official(sample_html(invalid=True), DAY, 11)

    def test_empty_or_unrelated_page_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_official("<html>404 Not Found</html>", DAY, 11)


if __name__ == "__main__":
    unittest.main()
