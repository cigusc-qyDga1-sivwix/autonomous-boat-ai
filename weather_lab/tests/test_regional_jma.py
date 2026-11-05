import unittest
from weather_lab import regional_jma

class RegionalJMAModelTests(unittest.TestCase):
    def test_has_24_locations(self):
        self.assertEqual(len(regional_jma.POINTS),24)
