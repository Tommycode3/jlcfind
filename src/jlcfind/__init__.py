"""jlcfind — JLCPCB/LCSC component sourcing toolkit.

Zero-dependency core. Public surface intended for reuse by sibling tools:

    from jlcfind import JlcClient, Part, parse_spec, search_parts
    from jlcfind.resolve import resolve_bom
    from jlcfind.cost import estimate_cost
"""

from .client import JlcClient
from .models import Part, PriceBreak, SearchSpec, BomLine, Candidate
from .specparse import parse_spec
from .search import search_parts

__version__ = "0.1.0"

__all__ = [
    "JlcClient",
    "Part",
    "PriceBreak",
    "SearchSpec",
    "BomLine",
    "Candidate",
    "parse_spec",
    "search_parts",
    "__version__",
]
