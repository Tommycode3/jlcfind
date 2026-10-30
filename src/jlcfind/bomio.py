"""Read BOMs from CSV/JSON with flexible column mapping.

Minimal accepted schema (documented in README):
  - a value/comment column        (value, comment, val, ...)         [optional]
  - a footprint/package column     (footprint, package, pkg, ...)     [optional]
  - and/or an MPN column           (mpn, "manufacturer part number")  [optional]
  - and/or an LCSC column          (lcsc, "lcsc part #", jlcpcb, ...)  [optional]
  - a designator column            (designator, reference, refdes)    [recommended]
  - an optional quantity column    (qty, quantity)

A line is resolvable if it has at least one of {lcsc, mpn} OR {value + footprint}.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .models import BomLine

# canonical -> accepted header aliases (lowercased, alnum-only compared)
_ALIASES = {
    "designators": [
        "designator", "designators", "reference", "references", "refdes",
        "ref", "refs", "part reference",
    ],
    "qty": ["qty", "quantity", "qnty", "count", "amount"],
    "value": ["value", "comment", "val", "comments"],
    "footprint": ["footprint", "package", "pkg", "fp", "case", "footprints"],
    "mpn": [
        "mpn", "manufacturer part number", "mfr part number", "mfg part number",
        "mfr part #", "mfg part #", "part number", "manufacturerpartnumber",
        "mfrpart", "partno", "pn",
    ],
    "lcsc": [
        "lcsc", "lcsc part", "lcsc part #", "lcsc part number", "lcscpart",
        "jlcpcb", "jlcpcb part #", "jlc", "jlc part", "supplier part",
        "supplier part number", "lcsc#",
    ],
    "manufacturer": ["manufacturer", "mfr", "mfg", "brand", "make"],
    "description": ["description", "desc", "details"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _build_header_map(headers: list[str]) -> dict[str, str]:
    """Map canonical field -> actual header present in the file."""
    norm_alias = {
        canon: {_norm(a) for a in aliases} for canon, aliases in _ALIASES.items()
    }
    mapping: dict[str, str] = {}
    for h in headers:
        nh = _norm(h)
        for canon, aset in norm_alias.items():
            if canon in mapping:
                continue
            if nh in aset:
                mapping[canon] = h
                break
    return mapping


def _split_designators(value: str) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for chunk in re.split(r"[,\s;]+", value.strip()):
        if not chunk:
            continue
        # expand simple ranges like R1-R4 only when prefix matches
        m = re.match(r"^([A-Za-z]+)(\d+)-([A-Za-z]*)(\d+)$", chunk)
        if m:
            pfx, a, pfx2, b = m.groups()
            if (not pfx2 or pfx2 == pfx) and int(b) >= int(a):
                out.extend(f"{pfx}{i}" for i in range(int(a), int(b) + 1))
                continue
        out.append(chunk)
    return out


def _line_from_row(row: dict, hmap: dict[str, str]) -> BomLine:
    def get(field: str) -> str:
        col = hmap.get(field)
        return str(row.get(col, "")).strip() if col else ""

    designators = _split_designators(get("designators"))
    qty_raw = get("qty")
    if qty_raw:
        try:
            qty = int(float(qty_raw))
        except ValueError:
            qty = len(designators) or 1
    else:
        qty = len(designators) or 1
    return BomLine(
        designators=designators,
        qty=qty,
        value=get("value"),
        footprint=get("footprint"),
        mpn=get("mpn"),
        lcsc=get("lcsc"),
        manufacturer=get("manufacturer"),
        description=get("description"),
        raw=dict(row),
    )


def read_bom(path: str | Path) -> list[BomLine]:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("components") or data.get("bom") or []
        if not rows:
            return []
        headers = list({k for r in rows for k in r.keys()})
        hmap = _build_header_map(headers)
        return [_line_from_row(r, hmap) for r in rows]
    # CSV / TSV
    sample = text[:4096]
    delim = "\t" if sample.count("\t") > sample.count(",") else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delim)
    headers = reader.fieldnames or []
    hmap = _build_header_map(headers)
    lines = [_line_from_row(r, hmap) for r in reader]
    return [ln for ln in lines if any(
        [ln.lcsc, ln.mpn, ln.value, ln.footprint, ln.designators]
    )]


def detected_columns(path: str | Path) -> dict[str, str]:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("components") or []
        headers = list({k for r in rows for k in r.keys()}) if rows else []
    else:
        sample = text[:4096]
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
        headers = (csv.DictReader(text.splitlines(), delimiter=delim).fieldnames) or []
    return _build_header_map(headers)
