"""Output generators: JLCPCB BOM, CPL validation, cost report, fab-package zip."""
from __future__ import annotations

import csv
import io
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from .cost import CostReport
from .resolve import ResolvedLine


def write_jlcpcb_bom(resolved: list[ResolvedLine], path: str | Path) -> dict:
    """JLCPCB assembly BOM: Comment, Designator, Footprint, LCSC Part #."""
    path = Path(path)
    rows, skipped = [], []
    for r in resolved:
        if r.ok and r.part:
            comment = r.line.value or r.part.mpn or r.part.description
            rows.append([
                comment,
                r.line.designator_str,
                r.line.footprint or r.part.package,
                r.part.lcsc_code,
            ])
        else:
            skipped.append(r.line.designator_str or r.line.value or "(unknown)")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        w.writerows(rows)
    return {"path": str(path), "lines": len(rows), "skipped": skipped}


def write_resolved_csv(resolved: list[ResolvedLine], path: str | Path) -> str:
    """Full audit CSV: every input line + chosen part + price/tier/stock/status."""
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "Designator", "Qty", "Value", "Footprint", "Status", "Source",
            "MPN", "LCSC", "Tier", "Stock", "UnitPrice", "Datasheet", "Note",
        ])
        for r in resolved:
            p = r.part
            w.writerow([
                r.line.designator_str, r.line.qty, r.line.value, r.line.footprint,
                r.status, r.source,
                p.mpn if p else r.line.mpn,
                p.lcsc_code if p else r.line.lcsc,
                p.tier if p else "",
                p.stock if p else "",
                (p.min_price if p else "") or "",
                p.datasheet_url if p else "",
                r.note,
            ])
    return str(path)


def validate_cpl(path: str | Path) -> dict:
    """Light CPL/placement sanity check (Designator, Mid X/Y, Rotation, Layer)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    headers = [h.lower().strip() for h in (reader.fieldnames or [])]
    def has(*opts):
        return any(any(o in h for h in headers) for o in opts)
    checks = {
        "designator": has("designator", "ref"),
        "x": has("mid x", "midx", "posx", "x"),
        "y": has("mid y", "midy", "posy", "y"),
        "rotation": has("rotation", "rot"),
        "layer": has("layer", "side"),
    }
    rows = sum(1 for _ in reader)
    return {"path": str(path), "rows": rows, "checks": checks,
            "ok": all(checks.values())}


def write_cost_report_md(rep: CostReport, resolved: list[ResolvedLine],
                         path: str | Path, project: str = "") -> str:
    path = Path(path)
    cur = rep.currency
    lines = []
    lines.append(f"# JLCPCB sourcing & cost report{(' — ' + project) if project else ''}")
    lines.append("")
    lines.append(f"- Board quantity: **{rep.board_qty}**")
    lines.append(f"- Distinct parts: **{rep.distinct_parts}** "
                 f"(Basic {rep.basic_parts} · Preferred {rep.preferred_parts} · "
                 f"Extended {rep.extended_parts})")
    lines.append(f"- Auto-picked but flagged (costed): **{rep.ambiguous}**")
    lines.append(f"- Unresolved lines (no part, excluded): **{rep.unresolved}**")
    lines.append("")
    lines.append("## Totals")
    lines.append(f"- Components ({rep.board_qty} boards): **{cur} {rep.components_cost:.2f}**")
    lines.append(f"- Extended setup fees (one-time): **{cur} {rep.setup_fees:.2f}**")
    lines.append(f"- **Grand total: {cur} {rep.grand_total:.2f}**")
    lines.append(f"- **Per board: {cur} {rep.per_board:.4f}**")
    lines.append("")
    if rep.stock_warnings:
        lines.append("## ⚠️ Stock warnings")
        for w in rep.stock_warnings:
            lines.append(f"- {w}")
        lines.append("")
    lines.append("## Line items")
    lines.append("| Designators | Part | LCSC | Tier | Qty/brd | Qty tot | Unit | Line | Fee |")
    lines.append("|---|---|---|---|--:|--:|--:|--:|--:|")
    for cl in rep.lines:
        unit = f"{cl.unit_price:.5f}" if cl.unit_price is not None else "—"
        tot = f"{cl.line_total:.4f}" if cl.line_total is not None else "—"
        lines.append(
            f"| {cl.designators} | {cl.description} | {cl.lcsc_code} | {cl.tier} | "
            f"{cl.qty_per_board} | {cl.qty_total} | {unit} | {tot} | "
            f"{cl.setup_fee:.2f} |"
        )
    review = [r for r in resolved if not r.ok]
    if review:
        lines.append("")
        lines.append("## Lines to review")
        for r in review:
            who = r.line.designator_str or r.line.value or r.line.mpn or "(?)"
            chosen = f" → {r.part.lcsc_code} ({r.part.tier})" if r.part else ""
            lines.append(f"- **{who}** — {r.status}{chosen}: {r.note}")
    lines.append("")
    lines.append("_Generated by jlcfind. Prices/stock from jlcsearch (LCSC); "
                 "verify on jlcpcb.com before ordering._")
    path.write_text("\n".join(lines))
    return str(path)


def build_fab_package(out_zip: str | Path, jlcpcb_bom: Path,
                      report_md: Optional[Path] = None,
                      cpl: Optional[Path] = None,
                      gerbers_dir: Optional[Path] = None,
                      datasheets_dir: Optional[Path] = None) -> dict:
    out_zip = Path(out_zip)
    contents = []
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(jlcpcb_bom, arcname=f"BOM/{jlcpcb_bom.name}")
        contents.append(jlcpcb_bom.name)
        if cpl and Path(cpl).exists():
            z.write(cpl, arcname=f"CPL/{Path(cpl).name}")
            contents.append(Path(cpl).name)
        if report_md and Path(report_md).exists():
            z.write(report_md, arcname=Path(report_md).name)
            contents.append(Path(report_md).name)
        if gerbers_dir and Path(gerbers_dir).is_dir():
            for f in sorted(Path(gerbers_dir).rglob("*")):
                if f.is_file():
                    z.write(f, arcname=f"gerbers/{f.relative_to(gerbers_dir)}")
            contents.append("gerbers/")
        if datasheets_dir and Path(datasheets_dir).is_dir():
            for f in sorted(Path(datasheets_dir).rglob("*")):
                if f.is_file():
                    z.write(f, arcname=f"datasheets/{f.relative_to(datasheets_dir)}")
            contents.append("datasheets/")
    return {"zip": str(out_zip), "contents": contents,
            "size_bytes": out_zip.stat().st_size}
