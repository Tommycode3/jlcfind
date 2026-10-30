"""Resolve BOM lines to concrete JLCPCB parts (enrichment + parametric search)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .client import JlcClient
from .config import Config
from .models import BomLine, Candidate, Part
from .search import _value_matches, search_parts
from .specparse import parse_spec

# resolution statuses
RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"


@dataclass
class ResolvedLine:
    line: BomLine
    part: Optional[Part] = None
    candidates: list[Candidate] = field(default_factory=list)
    status: str = UNRESOLVED
    source: str = ""        # "lcsc" | "mpn" | "parametric"
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status == RESOLVED and self.part is not None

    @property
    def has_part(self) -> bool:
        return self.part is not None


def _pick_exact(parts: list[Part], needle: str, by: str) -> Optional[Part]:
    needle_n = needle.strip().lower()
    for p in parts:
        field_val = (p.lcsc_code if by == "lcsc" else p.mpn).lower()
        if field_val == needle_n:
            return p
    return None


def resolve_line(line: BomLine, client: JlcClient, cfg: Config) -> ResolvedLine:
    # 1) Known LCSC code -> strongest signal
    if line.lcsc:
        parts = client.lookup(line.lcsc)
        exact = _pick_exact(parts, line.lcsc, "lcsc")
        if exact:
            return ResolvedLine(line, exact, [], RESOLVED, "lcsc")
        if parts:
            cands = [Candidate(p, 0.0, ["fuzzy LCSC match"]) for p in parts[:5]]
            return ResolvedLine(line, parts[0], cands, AMBIGUOUS, "lcsc",
                                "no exact LCSC code; showing closest")
        return ResolvedLine(line, None, [], UNRESOLVED, "lcsc", f"LCSC {line.lcsc} not found")

    # 2) Known MPN
    if line.mpn:
        parts = client.lookup(line.mpn)
        exact = _pick_exact(parts, line.mpn, "mpn")
        if exact:
            return ResolvedLine(line, exact, [], RESOLVED, "mpn")
        if parts:
            cands = [Candidate(p, 0.0, ["fuzzy MPN match"]) for p in parts[:5]]
            return ResolvedLine(line, parts[0], cands, AMBIGUOUS, "mpn",
                                "no exact MPN; showing closest")
        return ResolvedLine(line, None, [], UNRESOLVED, "mpn", f"MPN {line.mpn} not found")

    # 3) Parametric from value + footprint
    if line.value or line.footprint:
        spec = parse_spec(f"{line.value} {line.footprint}".strip())
        cands = search_parts(spec, client=client, package=line.footprint,
                             limit=5, config=cfg)
        if cands:
            top = cands[0].part
            # Confident when the auto-pick is fee-free (Basic/Preferred) and the
            # package matches the request. An Extended top-pick or a package
            # mismatch is worth a human look -> ambiguous.
            confident = top.is_basic or top.is_preferred
            if confident and spec.package and top.package:
                confident = spec.package.upper() in top.package.upper()
            # Never call it resolved if the requested value can't be found in
            # the part's MPN/description (upstream search can return unrelated parts).
            value_ok = not spec.value_text or _value_matches(spec, top)
            status = RESOLVED if (confident and value_ok) else AMBIGUOUS
            if status == RESOLVED:
                note = ""
            elif not value_ok:
                note = "value not confirmed — review"
            else:
                note = ("Extended auto-pick — review" if top.has_setup_fee
                        else "package uncertain — review")
            return ResolvedLine(line, top, cands, status, "parametric", note)
        return ResolvedLine(line, None, [], UNRESOLVED, "parametric",
                            "no parametric match")

    return ResolvedLine(line, None, [], UNRESOLVED, "", "no MPN/LCSC/value to resolve")


def resolve_bom(lines: list[BomLine], client: Optional[JlcClient] = None,
                cfg: Optional[Config] = None,
                progress=None) -> list[ResolvedLine]:
    cfg = cfg or Config.load()
    client = client or JlcClient(config=cfg)
    out: list[ResolvedLine] = []
    for i, line in enumerate(lines):
        if progress:
            progress(i + 1, len(lines), line)
        out.append(resolve_line(line, client, cfg))
    return out
