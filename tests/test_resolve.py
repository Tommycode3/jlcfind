import unittest
from unittest import mock

from jlcfind import resolve as R
from jlcfind.config import Config
from jlcfind.models import BomLine, Candidate, Part


def _part(mpn, desc, package="0402", basic=True):
    return Part.from_api({"lcsc": 1, "mfr": mpn, "description": desc,
                          "package": package, "is_basic": basic, "stock": 10_000,
                          "price": 0.001})


class TestParametricStatus(unittest.TestCase):
    def _run(self, part):
        line = BomLine(designators=["R1"], qty=1, value="10k", footprint="0402")
        with mock.patch.object(R, "search_parts",
                               return_value=[Candidate(part, 1.0, [])]):
            return R.resolve_line(line, client=None, cfg=Config())

    def test_value_match_basic_is_resolved(self):
        rl = self._run(_part("0402WGF1002TCE", "10kΩ ±1% 62.5mW 0402 Chip Resistor"))
        self.assertEqual(rl.status, R.RESOLVED)

    def test_wrong_value_is_never_resolved(self):
        # upstream search can return an unrelated Basic part (here: an inductor)
        rl = self._run(_part("SDCL1005C10NJTDF", "10nH 0402 Inductor"))
        self.assertEqual(rl.status, R.AMBIGUOUS)
        self.assertIn("value not confirmed", rl.note)


class TestLcscStatus(unittest.TestCase):
    def test_non_exact_lcsc_is_ambiguous(self):
        other = Part.from_api({"lcsc": 9999, "mfr": "X", "stock": 1})
        client = mock.Mock()
        client.lookup.return_value = [other]
        line = BomLine(designators=["D1"], qty=1, lcsc="C2128")
        rl = R.resolve_line(line, client=client, cfg=Config())
        self.assertEqual(rl.status, R.AMBIGUOUS)


if __name__ == "__main__":
    unittest.main()
