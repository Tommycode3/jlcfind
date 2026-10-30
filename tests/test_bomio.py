import tempfile
import unittest
from pathlib import Path

from jlcfind.bomio import read_bom, detected_columns


CSV_KICAD = """Reference,Value,Footprint,Qty,MPN
"R1,R2",10k,0402,2,RC0402FR-0710KL
C1,100nF,0402,1,
"""

CSV_JLCPCB = """Comment,Designator,Footprint,LCSC Part #
10k,"R1,R2",0402,C25744
100nF,C1,0402,C1525
"""

CSV_RANGE = """Designator,Comment,Package
R1-R4,1k,0603
"""


def _write(tmp, name, content):
    p = Path(tmp) / name
    p.write_text(content)
    return p


class TestBomIO(unittest.TestCase):
    def test_kicad_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "b.csv", CSV_KICAD)
            cols = detected_columns(p)
            self.assertIn("designators", cols)
            self.assertIn("mpn", cols)
            lines = read_bom(p)
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0].designators, ["R1", "R2"])
            self.assertEqual(lines[0].qty, 2)
            self.assertEqual(lines[0].mpn, "RC0402FR-0710KL")

    def test_jlcpcb_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "b.csv", CSV_JLCPCB)
            lines = read_bom(p)
            self.assertEqual(lines[0].value, "10k")
            self.assertEqual(lines[0].lcsc, "C25744")
            self.assertEqual(lines[0].footprint, "0402")

    def test_designator_range_expand(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "b.csv", CSV_RANGE)
            lines = read_bom(p)
            self.assertEqual(lines[0].designators, ["R1", "R2", "R3", "R4"])
            self.assertEqual(lines[0].qty, 4)


if __name__ == "__main__":
    unittest.main()
