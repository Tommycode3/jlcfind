"""jlcfind command-line interface (stdlib argparse)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .bomio import detected_columns, read_bom
from .cache import Cache
from .client import JlcClient
from .config import Config
from .cost import estimate_cost
from .datasheets import download_datasheets
from .outputs import (
    build_fab_package,
    validate_cpl,
    write_cost_report_md,
    write_jlcpcb_bom,
    write_resolved_csv,
)
from .render import info, money, rule, table
from .resolve import resolve_bom
from .search import search_parts
from .specparse import parse_spec


def _client(args) -> JlcClient:
    return JlcClient(config=Config.load(), fresh=getattr(args, "fresh", False))


def _bool_flag(args, name: str, default):
    return getattr(args, name) if getattr(args, name) is not None else default


# ---------- commands ----------
def cmd_search(args) -> int:
    cfg = Config.load()
    client = _client(args)
    spec = parse_spec(args.query)
    cands = search_parts(
        spec, client=client,
        prefer_basic=_bool_flag(args, "prefer_basic", cfg.prefer_basic),
        min_stock=args.min_stock, package=args.package or "",
        limit=args.limit, config=cfg,
    )
    if args.json:
        print(json.dumps([{**c.part.to_dict(), "score": c.score,
                           "reasons": c.reasons} for c in cands], indent=2))
        return 0
    if not cands:
        info("No parts found. Try a broader query or different package.")
        return 1
    info(f"Parsed: type={spec.ctype} value={spec.value_text or '—'} "
         f"package={spec.package or '—'} dielectric={spec.dielectric or '—'} "
         f"query='{spec.query}'")
    rows = [[
        c.part.lcsc_code, c.part.mpn[:26], c.part.package, c.part.tier,
        f"{c.part.stock:,}", money(c.part.min_price, cfg.currency),
        f"{c.score:.0f}", "; ".join(c.reasons[:2]),
    ] for c in cands]
    table("Search results", ["LCSC", "MPN", "Pkg", "Tier", "Stock", "Price",
                             "Score", "Why"], rows,
          justify=["left", "left", "left", "left", "right", "right", "right", "left"])
    return 0


def cmd_part(args) -> int:
    cfg = Config.load()
    client = _client(args)
    parts = client.lookup(args.code)
    if not parts:
        info(f"Nothing found for {args.code!r}.")
        return 1
    # prefer an exact match
    needle = args.code.strip().lower()
    part = next((p for p in parts if needle in (p.mpn.lower(), p.lcsc_code.lower())),
                parts[0])
    if not part.datasheet_url:
        part.datasheet_url = client.datasheet_url(part.lcsc_code)
    if args.json:
        print(json.dumps(part.to_dict(), indent=2))
        return 0
    rule(f"{part.mpn}  ({part.lcsc_code})")
    info(f"Tier:        {part.tier}")
    info(f"Package:     {part.package}")
    info(f"Category:    {part.category} / {part.subcategory}")
    info(f"Stock:       {part.stock:,}")
    info(f"Setup fee:   {'yes ($' + format(cfg.extended_part_fee_usd, '.2f') + ')' if part.has_setup_fee else 'none'}")
    info(f"Datasheet:   {part.datasheet_url or '—'}")
    if part.price_breaks:
        rows = [[f"{b.qty_from}+" if b.qty_to is None else f"{b.qty_from}-{b.qty_to}",
                 money(b.price, cfg.currency)] for b in part.price_breaks]
        table("Price breaks", ["Qty", "Unit"], rows, justify=["right", "right"])
    return 0


def _load_and_resolve(args, cfg, client):
    lines = read_bom(args.bom)
    info(f"Loaded {len(lines)} BOM lines from {args.bom}")
    cols = detected_columns(args.bom)
    info(f"Detected columns: {cols or '(none — check headers)'}")

    def prog(i, n, line):
        sys.stderr.write(f"\r  resolving {i}/{n} ...")
        sys.stderr.flush()
        if i == n:
            sys.stderr.write("\n")
    resolved = resolve_bom(lines, client=client, cfg=cfg, progress=prog)
    return lines, resolved


def cmd_resolve(args) -> int:
    cfg = Config.load()
    client = _client(args)
    _, resolved = _load_and_resolve(args, cfg, client)
    out = args.out or str(Path(args.bom).with_suffix("")) + ".resolved.csv"
    write_resolved_csv(resolved, out)
    ok = sum(1 for r in resolved if r.ok)
    amb = sum(1 for r in resolved if r.status == "ambiguous")
    unr = sum(1 for r in resolved if r.status == "unresolved")
    rows = [[
        r.line.designator_str[:18], (r.line.value or r.line.mpn or r.line.lcsc)[:18],
        r.status, r.source, (r.part.lcsc_code if r.part else "—"),
        (r.part.tier if r.part else ""), r.note[:30],
    ] for r in resolved]
    table("Resolution", ["Designators", "Value/MPN", "Status", "Src", "LCSC",
                         "Tier", "Note"], rows)
    rule()
    info(f"Resolved {ok} · ambiguous {amb} · unresolved {unr}  →  {out}")
    return 0 if unr == 0 else 2


def cmd_cost(args) -> int:
    cfg = Config.load()
    client = _client(args)
    qty = args.qty or cfg.default_board_qty
    _, resolved = _load_and_resolve(args, cfg, client)
    rep = estimate_cost(resolved, qty, cfg)
    if args.json:
        print(json.dumps({
            "board_qty": rep.board_qty, "components_cost": rep.components_cost,
            "setup_fees": rep.setup_fees, "grand_total": rep.grand_total,
            "per_board": rep.per_board, "basic": rep.basic_parts,
            "preferred": rep.preferred_parts, "extended": rep.extended_parts,
            "ambiguous": rep.ambiguous, "unresolved": rep.unresolved,
            "stock_warnings": rep.stock_warnings,
        }, indent=2))
    else:
        rows = [[cl.designators[:16], cl.description[:24], cl.lcsc_code, cl.tier,
                 str(cl.qty_total), money(cl.unit_price, cfg.currency),
                 money(cl.line_total, cfg.currency), f"{cl.setup_fee:.2f}"]
                for cl in rep.lines]
        table(f"Cost @ {qty} boards", ["Designators", "Part", "LCSC", "Tier",
              "QtyTot", "Unit", "Line", "Fee"], rows)
        rule("Totals")
        info(f"Components ({qty} boards): {money(rep.components_cost, cfg.currency)}")
        info(f"Extended setup fees:      {money(rep.setup_fees, cfg.currency)}")
        info(f"GRAND TOTAL:              {money(rep.grand_total, cfg.currency)}")
        info(f"Per board:                {money(rep.per_board, cfg.currency)}")
        if rep.stock_warnings:
            rule("Stock warnings")
            for w in rep.stock_warnings:
                info(f"  ⚠ {w}")
        if rep.ambiguous:
            info(f"\n{rep.ambiguous} line(s) auto-picked but flagged — included in "
                 f"estimate; run `jlcfind resolve` to review.")
        if rep.unresolved:
            info(f"{rep.unresolved} line(s) unresolved (no part) — not in estimate.")
    if args.out:
        write_cost_report_md(rep, resolved, args.out, project=Path(args.bom).stem)
        info(f"\nReport written: {args.out}")
    return 0


def cmd_bom(args) -> int:
    cfg = Config.load()
    client = _client(args)
    _, resolved = _load_and_resolve(args, cfg, client)
    out = args.out or str(Path(args.bom).with_suffix("")) + ".jlcpcb.csv"
    res = write_jlcpcb_bom(resolved, out)
    info(f"Wrote {res['lines']} parts → {out}")
    if res["skipped"]:
        info(f"Skipped {len(res['skipped'])} unresolved: {', '.join(res['skipped'][:8])}"
             + (" ..." if len(res["skipped"]) > 8 else ""))
    return 0


def cmd_datasheets(args) -> int:
    cfg = Config.load()
    client = _client(args)
    _, resolved = _load_and_resolve(args, cfg, client)
    out = args.out or str(Path(args.bom).with_suffix("")) + "_datasheets"

    def prog(i, n, key):
        sys.stderr.write(f"\r  datasheet {i}/{n}: {key} ...")
        sys.stderr.flush()
        if i == n:
            sys.stderr.write("\n")
    res = download_datasheets(resolved, out, client=client, progress=prog)
    info(f"Datasheets: {res['ok']}/{res['total']} ok → {res['outdir']}")
    return 0


def cmd_package(args) -> int:
    cfg = Config.load()
    client = _client(args)
    qty = args.qty or cfg.default_board_qty
    base = Path(args.bom).with_suffix("")
    stem = base.name
    _, resolved = _load_and_resolve(args, cfg, client)

    bom_path = Path(f"{base}.jlcpcb.csv")
    write_jlcpcb_bom(resolved, bom_path)
    rep = estimate_cost(resolved, qty, cfg)
    report_path = Path(f"{base}.report.md")
    write_cost_report_md(rep, resolved, report_path, project=stem)

    ds_dir = None
    if not args.no_datasheets:
        ds_dir = Path(f"{base}_datasheets")
        download_datasheets(resolved, ds_dir, client=client)

    if args.cpl:
        v = validate_cpl(args.cpl)
        info(f"CPL check: rows={v['rows']} ok={v['ok']} {v['checks']}")

    out_zip = args.out or f"{base}_fab_package.zip"
    res = build_fab_package(
        out_zip, bom_path, report_md=report_path,
        cpl=Path(args.cpl) if args.cpl else None,
        gerbers_dir=Path(args.gerbers) if args.gerbers else None,
        datasheets_dir=ds_dir,
    )
    rule("Fab package ready")
    info(f"Zip: {res['zip']} ({res['size_bytes']/1024:.1f} KB)")
    info(f"Contents: {', '.join(res['contents'])}")
    info(f"Grand total @ {qty} boards: {money(rep.grand_total, cfg.currency)}")
    return 0


def cmd_config(args) -> int:
    cfg = Config.load()
    if args.set:
        for pair in args.set:
            if "=" not in pair:
                info(f"Ignoring {pair!r} (use key=value)")
                continue
            k, v = pair.split("=", 1)
            if not hasattr(cfg, k):
                info(f"Unknown key {k!r}")
                continue
            cur = getattr(cfg, k)
            try:
                if isinstance(cur, bool):
                    nv = v.lower() in ("1", "true", "yes", "on")
                elif isinstance(cur, int):
                    nv = int(v)
                elif isinstance(cur, float):
                    nv = float(v)
                else:
                    nv = v
                setattr(cfg, k, nv)
            except ValueError:
                info(f"Bad value for {k}: {v!r}")
        cfg.save()
        info("Saved.")
    print(json.dumps(cfg.__dict__, indent=2))
    return 0


def cmd_cache(args) -> int:
    c = Cache()
    if args.clear:
        n = c.clear()
        info(f"Cleared {n} cached responses.")
    else:
        info("Use --clear to wipe the response cache.")
    return 0


# ---------- parser ----------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jlcfind",
        description="Search JLCPCB/LCSC parts, resolve BOMs, estimate cost, build fab packages.",
    )
    p.add_argument("--version", action="version", version=f"jlcfind {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp, fresh=True):
        if fresh:
            sp.add_argument("--fresh", action="store_true", help="bypass local cache")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    s = sub.add_parser("search", help="parametric part search")
    s.add_argument("query", help='e.g. "100nF 0402 X7R 16V" or "10k 0402"')
    s.add_argument("--package", help="force a package filter")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--min-stock", type=int, default=1)
    s.add_argument("--prefer-basic", dest="prefer_basic", action="store_true", default=None)
    s.add_argument("--no-prefer-basic", dest="prefer_basic", action="store_false")
    add_common(s)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("part", help="look up a single MPN or LCSC code")
    s.add_argument("code", help="MPN or Cxxxxx")
    add_common(s)
    s.set_defaults(func=cmd_part)

    s = sub.add_parser("resolve", help="resolve every BOM line to a JLCPCB part")
    s.add_argument("bom", help="BOM file (.csv/.tsv/.json)")
    s.add_argument("--out", help="resolved audit CSV path")
    add_common(s)
    s.set_defaults(func=cmd_resolve)

    s = sub.add_parser("cost", help="estimate assembly cost")
    s.add_argument("bom")
    s.add_argument("--qty", type=int, help="board quantity")
    s.add_argument("--out", help="write Markdown report to this path")
    add_common(s)
    s.set_defaults(func=cmd_cost)

    s = sub.add_parser("bom", help="emit a JLCPCB-format assembly BOM")
    s.add_argument("bom")
    s.add_argument("--out")
    add_common(s)
    s.set_defaults(func=cmd_bom)

    s = sub.add_parser("datasheets", help="download datasheet PDFs for the BOM")
    s.add_argument("bom")
    s.add_argument("--out", help="output directory")
    add_common(s)
    s.set_defaults(func=cmd_datasheets)

    s = sub.add_parser("package", help="build a complete fab package zip")
    s.add_argument("bom")
    s.add_argument("--qty", type=int)
    s.add_argument("--gerbers", help="directory of gerber files to bundle")
    s.add_argument("--cpl", help="CPL/placement file to bundle + validate")
    s.add_argument("--no-datasheets", action="store_true")
    s.add_argument("--out", help="output zip path")
    add_common(s)
    s.set_defaults(func=cmd_package)

    s = sub.add_parser("config", help="view/set configuration")
    s.add_argument("--set", nargs="*", help="key=value pairs")
    s.set_defaults(func=cmd_config)

    s = sub.add_parser("cache", help="manage the response cache")
    s.add_argument("--clear", action="store_true")
    s.set_defaults(func=cmd_cache)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except FileNotFoundError as e:
        sys.stderr.write(f"File not found: {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
