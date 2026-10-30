"""Parametric search + deterministic, explainable ranking."""
from __future__ import annotations

from typing import Optional

from .client import JlcClient
from .config import Config
from .models import Candidate, Part, SearchSpec, stock_score
from .specparse import parse_spec

# Category hints to bias full-text queries toward the right family.
_CATEGORY_HINT = {
    "resistor": "Resistors",
    "capacitor": "Capacitors",
    "inductor": "Inductors",
}


def _value_matches(spec: SearchSpec, part: Part) -> bool:
    """Best-effort: confirm the spec's value token appears in MPN/description."""
    if not spec.value_text:
        return False
    needle = spec.value_text.lower().replace("µ", "u")
    hay = f"{part.mpn} {part.description}".lower().replace("µ", "u")
    return needle in hay


def score_part(spec: SearchSpec, part: Part, cfg: Config) -> Candidate:
    score = 0.0
    reasons: list[str] = []

    if part.is_basic:
        score += 1000
        reasons.append("Basic part (no setup fee)")
    elif part.is_preferred:
        score += 650
        reasons.append("Preferred part (no setup fee)")
    else:
        reasons.append(f"Extended (+${cfg.extended_part_fee_usd:.2f} setup fee)")

    if spec.package and part.package:
        if spec.package.upper() == part.package.upper():
            score += 220
            reasons.append(f"package match {part.package}")
        elif spec.package.upper() in part.package.upper():
            score += 120
            reasons.append(f"package ~{part.package}")
        else:
            score -= 150
            reasons.append(f"package mismatch ({part.package} != {spec.package})")

    if _value_matches(spec, part):
        score += 160
        reasons.append(f"value match {spec.value_text}")

    if part.stock <= 0:
        score -= 500
        reasons.append("OUT OF STOCK")
    else:
        s = stock_score(part.stock)
        score += s
        if part.stock < 1000:
            reasons.append(f"low stock {part.stock}")

    mp = part.min_price
    if mp is not None and mp > 0:
        # cheaper is better; gentle, capped so it never overrides tier/stock
        import math
        score += max(0.0, 60.0 - 12.0 * math.log10(mp * 1000 + 1))

    return Candidate(part=part, score=round(score, 2), reasons=reasons)


def search_parts(spec_or_text, client: Optional[JlcClient] = None,
                 prefer_basic: Optional[bool] = None, min_stock: Optional[int] = None,
                 package: str = "", limit: int = 10,
                 config: Optional[Config] = None) -> list[Candidate]:
    cfg = config or (client.cfg if client else Config.load())
    client = client or JlcClient(config=cfg)
    spec = spec_or_text if isinstance(spec_or_text, SearchSpec) else parse_spec(str(spec_or_text))
    if package:
        spec.package = package
    if min_stock is None:
        min_stock = cfg.min_stock
    if prefer_basic is None:
        prefer_basic = cfg.prefer_basic

    category = _CATEGORY_HINT.get(spec.ctype, "")
    # Over-fetch unfiltered, then rank — keeps basic/extended both visible.
    parts = client.components_list(
        search=spec.query, package=spec.package,
        category=category, limit=cfg.search_overfetch,
    )
    if not parts and category:
        parts = client.components_list(
            search=spec.query, package=spec.package, limit=cfg.search_overfetch
        )
    if not parts:
        parts = client.search_text(spec.query or spec.raw, limit=cfg.search_overfetch)

    cands = [score_part(spec, p, cfg) for p in parts]
    cands = [c for c in cands if c.part.stock >= min_stock]
    if prefer_basic:
        cands.sort(key=lambda c: c.score, reverse=True)
    else:
        # de-emphasise the basic bonus when user explicitly disables the preference
        cands.sort(key=lambda c: (c.part.stock > 0, c.score), reverse=True)
    return cands[:limit]
