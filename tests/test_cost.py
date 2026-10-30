import unittest

from jlcfind.config import Config
from jlcfind.models import BomLine, Part
from jlcfind.cost import estimate_cost
from jlcfind.resolve import ResolvedLine, RESOLVED


def _rl(lcsc, qty, price, basic=False, preferred=False, stock=10_000):
    part = Part.from_api({
        "lcsc": lcsc, "mfr": f"MPN{lcsc}", "price": price,
        "is_basic": basic, "is_preferred": preferred, "stock": stock,
    })
    line = BomLine(designators=[f"R{lcsc}"], qty=qty, value="10k")
    return ResolvedLine(line=line, part=part, status=RESOLVED, source="mpn")


class TestCost(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.cfg.extended_part_fee_usd = 3.0

    def test_components_and_fees(self):
        resolved = [
            _rl(1, qty=2, price=0.01, basic=True),       # no fee
            _rl(2, qty=1, price=0.50, preferred=True),    # no fee
            _rl(3, qty=1, price=1.00),                    # extended -> fee
        ]
        rep = estimate_cost(resolved, board_qty=10, cfg=self.cfg)
        # components: (2*10*0.01) + (1*10*0.50) + (1*10*1.00) = 0.2 + 5 + 10 = 15.2
        self.assertAlmostEqual(rep.components_cost, 15.2, places=3)
        self.assertAlmostEqual(rep.setup_fees, 3.0, places=3)
        self.assertAlmostEqual(rep.grand_total, 18.2, places=3)
        self.assertEqual(rep.basic_parts, 1)
        self.assertEqual(rep.preferred_parts, 1)
        self.assertEqual(rep.extended_parts, 1)

    def test_fee_charged_once_per_distinct_part(self):
        resolved = [_rl(3, 1, 1.00), _rl(3, 1, 1.00)]  # same extended part twice
        rep = estimate_cost(resolved, board_qty=1, cfg=self.cfg)
        self.assertAlmostEqual(rep.setup_fees, 3.0, places=3)

    def test_stock_warning(self):
        resolved = [_rl(9, qty=100, price=0.01, basic=True, stock=50)]
        rep = estimate_cost(resolved, board_qty=10, cfg=self.cfg)  # need 1000 > 50
        self.assertEqual(len(rep.stock_warnings), 1)


if __name__ == "__main__":
    unittest.main()
