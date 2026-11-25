"""Synthetic contract tests, not a live website verification."""
import unittest
from scripts.official_exhibition_preview import parse_preview
from scripts.entry_exhibition_gate import validated_preview


class OfficialPreviewTest(unittest.TestCase):
    racers = {str(i): {"name": f"選手{i}"} for i in range(1, 7)}

    def fixture(self, order=(1, 2, 4, 3, 5, 6)):
        rows = "".join(
            f"<tr><td>{i}</td><td></td><td><a>選手{i}</a></td>"
            f"<td>52.0kg</td><td>6.7{i}</td></tr>"
            for i in range(1, 7))
        starts = "".join(
            f'<tr><td><div class="table1_boatImage1">'
            f'<span class="table1_boatImage1Number is-type{i}">{i}</span>'
            f'<span class="table1_boatImage1Time">{"F.02" if i == 4 else ".10"}</span>'
            f"</div></td></tr>" for i in order)
        return f"<table>{rows}</table><table>{starts}</table>"

    def test_actual_course_and_flying(self):
        result = parse_preview(self.fixture(), self.racers)
        self.assertEqual(validated_preview(result), (1, 2, 4, 3, 5, 6))
        self.assertEqual(result["racers"]["4"]["start_timing"], -.02)
        self.assertEqual(result["racers"]["3"]["exhibition_time"], 6.73)

    def test_nested_past_race_table_preserves_outer_row(self):
        html = self.fixture().replace(
            "</td></tr>", "</td><td><table><tr><td>R</td><td>2</td></tr></table></td></tr>")
        result = parse_preview(html, self.racers)
        self.assertEqual(validated_preview(result), (1, 2, 4, 3, 5, 6))

    def test_reject_missing_duplicate_or_mismatched(self):
        self.assertIsNone(parse_preview(self.fixture((1, 2, 3, 4, 5)), self.racers))
        self.assertIsNone(parse_preview(self.fixture((1, 2, 3, 4, 5, 5)), self.racers))
        self.assertIsNone(parse_preview(self.fixture().replace("選手3", "別人"), self.racers))
        self.assertIsNone(parse_preview(self.fixture().replace("6.73", ""), self.racers))
        self.assertIsNone(parse_preview(self.fixture().replace("F.02", "欠場"), self.racers))


if __name__ == "__main__":
    unittest.main()
