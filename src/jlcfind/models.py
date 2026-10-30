"""Domain models. Pure dataclasses — the shared vocabulary for sibling tools."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class PriceBreak:
    qty_from: int
    qty_to: Optional[int]  # None == open-ended
    price: float

    def contains(self, qty: int) -> bool:
        if qty < self.qty_from:
            return False
        return self.qty_to is None or qty <= self.qty_to


@dataclass
class Part:
    lcsc: int
    mpn: str
    manufacturer: str = ""
    package: str = ""
    description: str = ""
    category: str = ""
    subcategory: str = ""
    is_basic: bool = False
    is_preferred: bool = False
    stock: int = 0
    price_breaks: list[PriceBreak] = field(default_factory=list)
    datasheet_url: str = ""

    # ---- identity ----
    @property
    def lcsc_code(self) -> str:
        return f"C{self.lcsc}"

    @property
    def has_setup_fee(self) -> bool:
        # JLCPCB: Basic and Preferred parts incur no per-part loading fee.
        return not (self.is_basic or self.is_preferred)

    @property
    def tier(self) -> str:
        if self.is_basic:
            return "Basic"
        if self.is_preferred:
            return "Preferred"
        return "Extended"

    def unit_price_at(self, qty: int) -> Optional[float]:
        """Unit price for an order of `qty`. Falls back to the nearest tier."""
        if not self.price_breaks:
            return None
        for b in self.price_breaks:
            if b.contains(qty):
                return b.price
        # qty below smallest break -> use the smallest (MOQ) break price
        first = min(self.price_breaks, key=lambda b: b.qty_from)
        if qty < first.qty_from:
            return first.price
        # qty above all -> use the highest-qty break
        return max(self.price_breaks, key=lambda b: b.qty_from).price

    @property
    def min_price(self) -> Optional[float]:
        if not self.price_breaks:
            return None
        return min(b.price for b in self.price_breaks)

    @property
    def min_order_qty(self) -> int:
        if not self.price_breaks:
            return 1
        return min(b.qty_from for b in self.price_breaks)

    # ---- parsing ----
    @staticmethod
    def _parse_price(raw: Any) -> list[PriceBreak]:
        if raw is None:
            return []
        if isinstance(raw, (int, float)):
            return [PriceBreak(1, None, float(raw))]
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                return []
            # jlcsearch /components/list format: "1-49:0.0822,50-149:0.0659,6000-:0.0397"
            if ":" in raw and not raw.startswith(("[", "{")):
                breaks = []
                for chunk in raw.split(","):
                    rng, _, price = chunk.partition(":")
                    lo, _, hi = rng.partition("-")
                    try:
                        breaks.append(PriceBreak(int(lo), int(hi) if hi.strip() else None,
                                                 float(price)))
                    except ValueError:
                        continue
                return sorted(breaks, key=lambda b: b.qty_from)
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    return [PriceBreak(1, None, float(raw))]
                except ValueError:
                    return []
        if isinstance(raw, list):
            breaks = []
            for item in raw:
                try:
                    qto = item.get("qTo")
                    breaks.append(
                        PriceBreak(
                            int(item["qFrom"]),
                            int(qto) if qto is not None else None,
                            float(item["price"]),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            return sorted(breaks, key=lambda b: b.qty_from)
        return []

    @classmethod
    def from_api(cls, d: dict) -> "Part":
        return cls(
            lcsc=int(d.get("lcsc") or 0),
            mpn=str(d.get("mfr") or d.get("mpn") or "").strip(),
            manufacturer=str(d.get("manufacturer") or "").strip(),
            package=str(d.get("package") or "").strip(),
            description=str(d.get("description") or "").strip(),
            category=str(d.get("category") or "").strip(),
            subcategory=str(d.get("subcategory") or "").strip(),
            is_basic=bool(d.get("is_basic")),
            is_preferred=bool(d.get("is_preferred")),
            stock=int(d.get("stock") or 0),
            price_breaks=cls._parse_price(d.get("price")),
            datasheet_url=str(d.get("datasheet") or d.get("datasheet_url") or "").strip(),
        )

    def to_dict(self) -> dict:
        return {
            "lcsc": self.lcsc,
            "lcsc_code": self.lcsc_code,
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "package": self.package,
            "description": self.description,
            "category": self.category,
            "subcategory": self.subcategory,
            "tier": self.tier,
            "is_basic": self.is_basic,
            "is_preferred": self.is_preferred,
            "stock": self.stock,
            "min_price": self.min_price,
            "datasheet_url": self.datasheet_url,
            "price_breaks": [
                {"qty_from": b.qty_from, "qty_to": b.qty_to, "price": b.price}
                for b in self.price_breaks
            ],
        }


# ---- component-type constants for the spec parser ----
RESISTOR = "resistor"
CAPACITOR = "capacitor"
INDUCTOR = "inductor"
UNKNOWN = "unknown"


@dataclass
class SearchSpec:
    raw: str
    ctype: str = UNKNOWN
    value: Optional[float] = None  # SI base unit (ohm / farad / henry)
    value_text: str = ""           # original token, e.g. "100nF"
    package: str = ""
    dielectric: str = ""           # X7R / X5R / C0G / NP0 ...
    tolerance: str = ""            # "1%", "5%" ...
    voltage: str = ""              # "16V" ...
    keywords: list[str] = field(default_factory=list)

    @property
    def query(self) -> str:
        """Full-text query handed to jlcsearch (it tokenises and matches)."""
        parts = []
        if self.value_text:
            parts.append(self.value_text)
        for f in (self.dielectric, self.voltage, self.tolerance):
            if f:
                parts.append(f)
        parts.extend(self.keywords)
        return " ".join(parts).strip()


@dataclass
class BomLine:
    designators: list[str] = field(default_factory=list)
    qty: int = 1
    value: str = ""
    footprint: str = ""
    mpn: str = ""
    lcsc: str = ""
    manufacturer: str = ""
    description: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def designator_str(self) -> str:
        return ",".join(self.designators)


@dataclass
class Candidate:
    part: Part
    score: float
    reasons: list[str] = field(default_factory=list)


def stock_score(stock: int) -> float:
    """Diminishing-returns reward for stock depth."""
    if stock <= 0:
        return 0.0
    return min(math.log10(stock + 1) * 20.0, 120.0)
