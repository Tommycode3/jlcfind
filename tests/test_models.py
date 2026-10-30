import unittest

from jlcfind.models import Part


class TestPriceParsing(unittest.TestCase):
    def test_float_price(self):
        p = Part.from_api({"lcsc": 1525, "mfr": "X", "price": 0.01})
        self.assertEqual(len(p.price_breaks), 1)
        self.assertAlmostEqual(p.unit_price_at(100), 0.01)

    def test_tiered_price_string(self):
        raw = '[{"qFrom": 20, "qTo": 19980, "price": 0.001}, {"qFrom": 20000, "qTo": null, "price": 0.0008}]'
        p = Part.from_api({"lcsc": 1, "mfr": "Y", "price": raw})
        self.assertEqual(len(p.price_breaks), 2)
        self.assertAlmostEqual(p.unit_price_at(100), 0.001)
        self.assertAlmostEqual(p.unit_price_at(50000), 0.0008)

    def test_below_moq_uses_first_break(self):
        raw = '[{"qFrom": 20, "qTo": 100, "price": 0.005}]'
        p = Part.from_api({"lcsc": 1, "mfr": "Z", "price": raw})
        self.assertAlmostEqual(p.unit_price_at(5), 0.005)

    def test_tier_and_fee(self):
        basic = Part.from_api({"lcsc": 1, "mfr": "A", "is_basic": True})
        pref = Part.from_api({"lcsc": 2, "mfr": "B", "is_preferred": True})
        ext = Part.from_api({"lcsc": 3, "mfr": "C"})
        self.assertEqual(basic.tier, "Basic")
        self.assertFalse(basic.has_setup_fee)
        self.assertEqual(pref.tier, "Preferred")
        self.assertFalse(pref.has_setup_fee)
        self.assertEqual(ext.tier, "Extended")
        self.assertTrue(ext.has_setup_fee)

    def test_lcsc_code(self):
        p = Part.from_api({"lcsc": 8734, "mfr": "STM32"})
        self.assertEqual(p.lcsc_code, "C8734")


if __name__ == "__main__":
    unittest.main()


class TestRangeStringPrice(unittest.TestCase):
    """jlcsearch /components/list returns price tiers as 'lo-hi:price,...'."""

    def test_range_string(self):
        p = Part.from_api({"lcsc": 2128, "mfr": "1N4148WS",
                           "price": "1-499:0.0115,500-2999:0.0093,51000-:0.0073"})
        self.assertEqual(len(p.price_breaks), 3)
        self.assertAlmostEqual(p.unit_price_at(1), 0.0115)
        self.assertAlmostEqual(p.unit_price_at(500), 0.0093)
        self.assertAlmostEqual(p.unit_price_at(100_000), 0.0073)
        self.assertEqual(p.min_order_qty, 1)

