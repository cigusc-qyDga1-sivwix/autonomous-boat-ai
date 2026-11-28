import unittest
from scripts.official_preview_fallback import parse

class NationalOfficialPreviewTest(unittest.TestCase):
    def fixture(self, order=(1,3,2,4,5,6), missing=False):
        names=[f"選手{i}" for i in range(1,7)]
        racers="".join(f'<tbody class="is-fs12"><tr><td>{i}</td><td>写真</td><td>{names[i-1]}</td><td>52.0</td><td>{"-" if missing and i==2 else "6.70"}</td><td>-0.5</td></tr></tbody>' for i in range(1,7))
        starts="".join(f'<div class="table1_boatImage1"><span class="table1_boatImage1Number">{i}</span><span class="table1_boatImage1Time">{"F.03" if i==3 else ".15"}</span></div>' for i in order)
        return '<table>'+racers+'</table>'+starts,names
    def test_entry_change_and_flying(self):
        html,names=self.fixture()
        p=parse(html,names)["racers"]
        self.assertEqual(p["3"]["course_number"],2)
        self.assertEqual(p["3"]["start_timing"],-.03)
        self.assertEqual(p["2"]["course_number"],3)
    def test_missing_measurement(self):
        html,names=self.fixture(missing=True)
        with self.assertRaises(ValueError):
            parse(html,names)
    def test_duplicate_lane(self):
        html,names=self.fixture(order=(1,2,2,4,5,6))
        with self.assertRaises(ValueError):
            parse(html,names)
    def test_wrong_name(self):
        html,names=self.fixture()
        names[0]="別選手"
        with self.assertRaises(ValueError):
            parse(html,names)

if __name__=="__main__":
    unittest.main()
