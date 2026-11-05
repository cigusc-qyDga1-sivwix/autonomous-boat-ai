import unittest
from weather_lab import regional_jma

class RegionalJMAModelTests(unittest.TestCase):
    def test_has_24_locations(self):
        self.assertEqual(len(regional_jma.POINTS),24)

    def test_model_schema_and_provenance(self):
        from datetime import datetime
        from weather_lab.regional_jma import parse
        row=lambda lat,lon:{"latitude":lat,"longitude":lon,
          "hourly":{"time":["2026-11-06T08:00"],"wind_speed_10m":[5],
          "wind_direction_10m":[180],"temperature_2m":[14],"precipitation":[0]},
          "current":{"time":"2026-11-06T07:45","wind_speed_10m":5,
          "wind_direction_10m":180,"temperature_2m":14}}
        source=[row(lat,lon) for lat,lon in regional_jma.POINTS]
        now=datetime.fromisoformat("2026-11-06T07:52:00+09:00")
        doc=parse(source,now)
        self.assertEqual(doc["provider"]["model_source"],"JMA MSM/GSM")
        self.assertEqual(len(doc["venues"]),24)
        self.assertTrue(doc["scope"]["no_track_water_wind_or_wave_measured"])
        self.assertFalse(doc["venues"][2]["boat_lab_prediction_in_scope"])
        self.assertEqual(doc["venues"][9]["model_current"]["wind_mps"],5)
