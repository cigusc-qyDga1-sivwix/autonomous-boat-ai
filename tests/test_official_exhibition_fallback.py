import unittest
from datetime import datetime, timedelta, timezone
from scripts.official_exhibition_fallback import parse, collect, JST, SOURCE
from scripts.autonomous_daily import select_exhibition_source

def fixture(order=(1,6,2,3,4,5), missing=False, mismatch=False):
    entrants = {str(i): {"name": f"選手{i}"} for i in range(1,7)}
    groups = "".join(f"<tbody><tr><td>{i}</td><td><img></td><td><a>選手{99 if mismatch and i==2 else i}</a></td><td>51.0kg</td><td>6.8{i}</td><td>0.0</td></tr></tbody>" for i in range(1,7))
    starts = "".join(f'<tr><td><div class="table1_boatImage1"><span class="table1_boatImage1Number">{i}</span><span class="table1_boatImage1Line"><span><img></span></span><span class="table1_boatImage1Time">{"-" if missing and i==2 else "F.03" if i==6 else ".12"}</span></div></td></tr>' for i in order)
    return f'<div class="grid_unit"><table>{groups}</table></div><div class="grid_unit"><table><tbody>{starts}</tbody></table></div>', entrants

class OfficialFallbackTest(unittest.TestCase):
    def test_changed_entry_and_flying(self):
        html, entrants = fixture()
        p = parse(html, entrants)["racers"]
        self.assertEqual(p["6"]["course_number"], 2)
        self.assertEqual(p["6"]["start_timing"], -.03)
        self.assertEqual(p["2"]["exhibition_time"], 6.82)
    def test_reject_missing_duplicate_and_mismatched_names(self):
        for options in ({"missing":True}, {"mismatch":True}, {"order":(1,2,3,4,5,5)}):
            html, entrants = fixture(**options)
            with self.assertRaises(ValueError):
                parse(html, entrants)
    def test_fallback_scope_and_provenance(self):
        html, entrants = fixture()
        now = datetime(2026,11,24,16,0,tzinfo=JST)
        race = {"closed_at":"2026-11-24 16:10:00","racers":entrants}
        late = {"closed_at":"2026-11-24 16:02:00","racers":entrants}
        payload = {"programs":{"stadiums":{"1":{"races":{"1":race,"2":late}}}}}
        def fetch(target):
            return (parse(html, entrants), {"source":SOURCE,"captured_before_cutoff":True,
                "six_program_names_matched":True,"captured_at_utc":now.isoformat(),
                "source_url":"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=1&jcd=01&hd=20261124"}), None
        self.assertEqual(collect(payload, now, fetch=fetch)["captured_six_boat"],1)
        self.assertNotIn("preview",late)
        live, _, source = select_exhibition_source(race,None,now,"1",1)
        self.assertEqual(source,"official_beforeinfo")
        self.assertEqual(live["_exhibition_origin"]["source"],SOURCE)
        self.assertEqual(select_exhibition_source(race,None,now+timedelta(minutes=9),"1",1)[2],"unavailable")

if __name__ == "__main__":
    unittest.main()
