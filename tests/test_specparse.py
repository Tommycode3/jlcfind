import unittest

from jlcfind.specparse import parse_spec
from jlcfind.models import CAPACITOR, RESISTOR, INDUCTOR


class TestSpecParse(unittest.TestCase):
    def test_capacitor(self):
        s = parse_spec("100nF 0402 X7R 16V")
        self.assertEqual(s.ctype, CAPACITOR)
        self.assertAlmostEqual(s.value, 100e-9)
        self.assertEqual(s.package, "0402")
        self.assertEqual(s.dielectric, "X7R")
        self.assertEqual(s.voltage, "16V")

    def test_resistor_k(self):
        s = parse_spec("10k 0603 1%")
        self.assertEqual(s.ctype, RESISTOR)
        self.assertAlmostEqual(s.value, 10000.0)
        self.assertEqual(s.package, "0603")
        self.assertEqual(s.tolerance, "1%")

    def test_resistor_code(self):
        s = parse_spec("4k7 0402")
        self.assertEqual(s.ctype, RESISTOR)
        self.assertAlmostEqual(s.value, 4700.0)

    def test_resistor_ohm(self):
        s = parse_spec("100R 0805")
        self.assertEqual(s.ctype, RESISTOR)
        self.assertAlmostEqual(s.value, 100.0)

    def test_inductor(self):
        s = parse_spec("4.7uH 0805")
        self.assertEqual(s.ctype, INDUCTOR)
        self.assertAlmostEqual(s.value, 4.7e-6)

    def test_microfarad(self):
        s = parse_spec("10uF 0805 X5R")
        self.assertEqual(s.ctype, CAPACITOR)
        self.assertAlmostEqual(s.value, 10e-6)

    def test_query_build(self):
        s = parse_spec("100nF 0402 X7R")
        self.assertIn("100nF", s.query)
        self.assertIn("X7R", s.query)

    def test_sot23_package(self):
        s = parse_spec("BC847 SOT-23")
        self.assertTrue(s.package.upper().startswith("SOT-23"))


if __name__ == "__main__":
    unittest.main()
