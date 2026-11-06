"""Source-specific JMA tidal height, no false tidal-flow information."""
import unittest
from datetime import date
from weather_lab.jma_tide import parse, STATIONS, _height, _events

def line(day=date(2026,11,6),st="TK"):
    # 24 hourly heights and four high/low slots, fixed 136-character format.
    hourly="".join(f"{v:3d}" for v in range(24))
    highs="1453181"+"9999999"*3
    lows="0847 77"+"9999999"*3
    row=hourly+f"{day.year%100:2d}{day.month:2d}{day.day:2d}"+st+highs+lows
    assert len(row)==136
    return row

class JmaTidesTests(unittest.TestCase):
    def test_tide_predictions_fixed_width_and_not_flow(self):
        x=parse(line(),"TK",date(2026,11,6))
        self.assertEqual(x["high_tides"][0]["time_jst"],"14:53")
        self.assertEqual(x["low_tides"][0]["height_cm_datum"],77)
        self.assertEqual(len(x["hourly_height_cm_datum"]),24)
        self.assertFalse(x["current_flow_observed"])
        self.assertIsNone(x["current_velocity_mps"])
        self.assertFalse(x["on_course_station"])

    def test_invalid_or_other_dates_do_not_impersonate_today(self):
        self.assertIsNone(parse(line(),"TK",date(2026,11,7)))
        with self.assertRaises(ValueError):
            parse(line(),"ZZ",date(2026,11,6))
        with self.assertRaises(ValueError):
            parse(line()+"\n"+line(),"TK",date(2026,11,6))

    def test_tide_table_missing_values_are_not_zero(self):
        self.assertIsNone(_height("999"))
        self.assertIsNone(_height("   "))
        self.assertEqual(_events("9999999"*4),[])
