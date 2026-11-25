"""Synthetic fixtures; live venue HTML is a separate acceptance test."""
import unittest
from datetime import datetime
from scripts.karatsu_official_preview import parse, JST

class KaratsuPreviewTest(unittest.TestCase):
    def setUp(self):
        self.names = [f"選手{i}" for i in range(1, 7)]
        self.cutoff = datetime(2026, 11, 26, 8, 35, tzinfo=JST)
        self.start = [[str(i), str(i), "------", "S" if i <= 3 else "D", "", ".15", "------"] for i in range(1, 7)]
        self.metrics = [[str(i), "52.4", "", "-0.5", "6.68", "36.77", "5.33", "7.67", "4"] for i in range(1, 7)]

    def html(self):
        def table(rows):
            return "<table>" + "".join("<tr>"+"".join("<td>"+v+"</td>" for v in row)+"</tr>" for row in rows)+"</table>"
        return "<h3>1R 朝１戦</h3><p>締切時刻 08:35</p>" + " ".join(self.names) + table(self.start) + table(self.metrics)

    def test_complete(self):
        rows = parse(self.html(), 1, self.names, self.cutoff)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["turn_time"], 5.33)
        self.assertEqual(rows[0]["start_timing"], .15)

    def test_missing_measurement(self):
        self.metrics[0][6] = "-"
        with self.assertRaises(ValueError):
            parse(self.html(), 1, self.names, self.cutoff)

    def test_duplicate_course(self):
        self.start[1][0] = "1"
        with self.assertRaises(ValueError):
            parse(self.html(), 1, self.names, self.cutoff)

    def test_wrong_names(self):
        with self.assertRaises(ValueError):
            parse(self.html(), 1, ["別選手"] * 6, self.cutoff)

    def test_flying(self):
        self.start[0][-2] = "F.03"
        self.assertEqual(parse(self.html(), 1, self.names, self.cutoff)[0]["start_timing"], -.03)

if __name__ == "__main__":
    unittest.main()
