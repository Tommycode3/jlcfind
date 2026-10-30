"""Assembly cost estimation from resolved BOM lines."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import Config
from .resolve import ResolvedLine


@dataclass
class CostLine:
    designators: str
    description: str
    lcsc_code: str
    tier: str
    qty_per_board: int
    qty_total: int
    unit_price: Optional[float]
    line_total: Optional[float]
    setup_fee: float
    stock: int
    enough_stock: bool


@dataclass
class CostReport:
    board_qty: int
    currency: str
    lines: list[CostLine] = field(default_factory=list)
    components_cost: float = 0.0       # parts for ALL boards
    setup_fees: float = 0.0            # one-time, all distinct extended parts
    distinct_parts: int = 0
    extended_parts: int = 0
    basic_parts: int = 0
    preferred_parts: int = 0
    unresolved: int = 0
    ambiguous: int = 0
    stock_warnings: list[str] = field(default_factory=list)

    @property
    def grand_total(self) -> float:
        return round(self.components_cost + self.setup_fees, 4)

    @property
    def per_board(self) -> float:
        if self.board_qty <= 0:
            return 0.0
        # setup fee is one-time -> amortised across the run
        return round(self.grand_total / self.board_qty, 4)


def estimate_cost(resolved: list[ResolvedLine], board_qty: int,
                  cfg: Optional[Config] = None) -> CostReport:
    cfg = cfg or Config.load()
    rep = CostReport(board_qty=board_qty, currency=cfg.currency)
    seen_fee_parts: set[int] = set()

    for r in resolved:
        if r.part is None:
            rep.unresolved += 1
            continue
        if not r.ok:
            rep.ambiguous += 1  # has a part but flagged for review; still costed
        p = r.part
        rep.distinct_parts += 1
        qty_total = r.line.qty * board_qty
        unit = p.unit_price_at(qty_total)
        line_total = round(unit * qty_total, 4) if unit is not None else None

        # one-time setup fee per distinct extended part
        fee = 0.0
        if p.has_setup_fee and p.lcsc not in seen_fee_parts:
            fee = cfg.extended_part_fee_usd
            seen_fee_parts.add(p.lcsc)

        if p.is_basic:
            rep.basic_parts += 1
        elif p.is_preferred:
            rep.preferred_parts += 1
        else:
            rep.extended_parts += 1

        enough = p.stock >= qty_total
        if not enough:
            rep.stock_warnings.append(
                f"{r.line.designator_str or p.lcsc_code}: need {qty_total}, stock {p.stock}"
            )

        rep.lines.append(CostLine(
            designators=r.line.designator_str,
            description=(r.line.value or p.mpn or p.description)[:48],
            lcsc_code=p.lcsc_code,
            tier=p.tier,
            qty_per_board=r.line.qty,
            qty_total=qty_total,
            unit_price=unit,
            line_total=line_total,
            setup_fee=fee,
            stock=p.stock,
            enough_stock=enough,
        ))
        if line_total is not None:
            rep.components_cost = round(rep.components_cost + line_total, 4)
        rep.setup_fees = round(rep.setup_fees + fee, 4)

    return rep
