"""End-to-end forward-only matched weather shadow, not formal picks."""
from copy import deepcopy
from datetime import datetime
from unittest import TestCase

from scripts import autonomous_daily as A
from tests.test_four_factor_main import race


NOW = datetime.fromisoformat("2026-11-06T09:00:00+09:00")


class WeatherShadowIntegrationTests(TestCase):
    def test_special_site_wind_produces_alternative_only(self):
        r=race("2026-11-06")
        r["preview"]["wind_speed"]=6
        r["preview"]["wave_height"]=2
        base=deepcopy(r)
        main=A.prediction(r,"尼崎",1,"exhibition",NOW,"fixture")
        compare=main["weather_special_shadow"]
        self.assertEqual(main["model_version"],A.LINKED_MAIN_MODEL)
        self.assertEqual(compare["condition"]["condition"],"amagasaki_wind_6m")
        self.assertTrue(compare["main_bets_unchanged"])
        self.assertTrue(compare["not_part_of_formal_performance"])
        self.assertFalse(compare["result_data_used"])
        self.assertEqual(sum(x["virtual_yen"] for x in compare["forecast_alternative_bets"]),50000)
        self.assertEqual(sum(x["virtual_yen"] for x in main["bets"]),50000)
        self.assertEqual(r,base)

    def test_no_special_condition_leaves_formal_prediction_alone(self):
        r=race("2026-11-06")
        r["preview"]["wind_speed"]=5
        result=A.prediction(r,"尼崎",1,"exhibition",NOW,"fixture")
        self.assertNotIn("weather_special_shadow",result)
        r["preview"]["wind_speed"]=6
        normal=A.prediction(r,"徳山",1,"exhibition",NOW,"fixture")
        self.assertNotIn("weather_special_shadow",normal)

    def test_result_never_enters_shadow_or_main(self):
        r=race("2026-11-06")
        r["preview"]["wind_speed"]=9
        r["preview"]["wave_height"]=5
        original=A.prediction(r,"尼崎",1,"exhibition",NOW,"fixture")
        r["result"]={"finish":"6-4-5","payout":999999}
        after=A.prediction(r,"尼崎",1,"exhibition",NOW,"fixture")
        self.assertEqual(original["bets"],after["bets"])
        self.assertEqual(original["weather_special_shadow"],after["weather_special_shadow"])


if __name__ == "__main__":
    import unittest
    unittest.main()
