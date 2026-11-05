"""Weather corrections are only conditional *shadow*, main unchanged."""
import copy
import itertools
import unittest
from scripts.venue_weather_special_shadow import rescore, site_condition


def ranked():
    combos=["-".join(map(str,p)) for p in itertools.permutations(range(1,7),3)]
    values=[1/(i+6) for i in range(len(combos))]
    total=sum(values)
    return [{"combination":c,"relative_score":s/total} for c,s in zip(combos,values)]


class VenueWeatherSpecialShadowTests(unittest.TestCase):
    def test_normal_weather_has_no_new_shadow(self):
        w={"source":"boatrace_preview","site_observed":True,"wind_speed":4.9,"wave_height":2}
        self.assertIsNone(rescore(ranked(),"津",w))
        w["wind_speed"]=5
        self.assertIsNone(rescore(ranked(),"常滑",w))

    def test_nearby_forecast_does_not_trigger_evidenced_venue_special(self):
        w={"source":"open-meteo","site_observed":False,"wind_speed":10,"wave_height":10}
        for venue in ["津","尼崎","三国","宮島","児島","鳴門"]:
            self.assertIsNone(rescore(ranked(),venue,w))

    def test_qualified_event_scores_reweighted_and_original_immutable(self):
        original=ranked()
        old=copy.deepcopy(original)
        w={"source":"boatrace_preview","site_observed":True,"wind_speed":5,"wave_height":2}
        result=rescore(original,"津",w)
        self.assertEqual(result["condition"]["condition"],"tsu_wind_5m")
        self.assertFalse(result["primary_bets_changed"])
        self.assertEqual(result["max_pre_normalization_relative_change"],.04)
        self.assertAlmostEqual(sum(x["relative_score"] for x in result["outcomes"]),1)
        self.assertNotEqual(result["outcomes"],original)
        self.assertEqual(original,old)

    def test_strong_wind_and_wave_allow_only_bounded_reweighting(self):
        x=rescore(ranked(),"尼崎",{"site_observed":True,"wind_speed":9,"wave_height":6})
        self.assertEqual(x["alpha"],.965)
        self.assertEqual(x["max_pre_normalization_relative_change"],.08)
        self.assertEqual(x["condition"]["condition"],"amagasaki_wind_6m")

    def test_tide_or_relative_wind_requires_verified_inputs(self):
        w={"site_observed":True,"wind_speed":8,"wave_height":5,"relative_wind":"tailwind",
           "local_tide_stage":"high"}
        for venue in ["三国","宮島","児島","鳴門"]:
            self.assertIsNone(site_condition(venue,w))
        w["relative_wind_verified"]=True
        self.assertEqual(site_condition("三国",w)["condition"],"mikuni_verified_tailwind")
        self.assertIsNone(site_condition("宮島",w))
        w["local_tide_verified"]=True
        self.assertEqual(site_condition("宮島",w)["condition"],"miyajima_verified_high_tide")
        self.assertEqual(site_condition("児島",w)["condition"],"kojima_verified_tide_and_tailwind")

    def test_invalid_canonical_ranked_rejected_if_special_triggered(self):
        w={"site_observed":True,"wind_speed":7,"wave_height":0}
        with self.assertRaises(ValueError):
            rescore([{"combination":"1-2-3","relative_score":1}],"津",w)


if __name__ == "__main__":
    unittest.main()
