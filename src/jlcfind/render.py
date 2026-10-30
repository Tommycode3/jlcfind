"""Console rendering. Uses `rich` if installed, else clean aligned plain text."""
from __future__ import annotations

from typing import Optional

try:  # optional pretty output
    from rich.console import Console
    from rich.table import Table
    _RICH = True
    _console = Console()
except Exception:  # pragma: no cover
    _RICH = False
    _console = None


def table(title: str, headers: list[str], rows: list[list[str]],
          justify: Optional[list[str]] = None) -> None:
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    if _RICH:
        t = Table(title=title, header_style="bold cyan", title_style="bold")
        for i, h in enumerate(headers):
            j = (justify[i] if justify and i < len(justify) else "left")
            t.add_column(h, justify=j, overflow="fold")
        for r in rows:
            t.add_row(*r)
        _console.print(t)
        return
    # plain fallback
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    if title:
        print(f"\n{title}")
    sep = "  "
    print(sep.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print(sep.join("-" * widths[i] for i in range(len(headers))))
    for r in rows:
        print(sep.join(c.ljust(widths[i]) for i, c in enumerate(r)))


def info(msg: str) -> None:
    if _RICH:
        _console.print(msg)
    else:
        print(msg)


def rule(msg: str = "") -> None:
    if _RICH:
        _console.rule(msg)
    else:
        print("\n" + "=" * 60 + (f" {msg}" if msg else ""))


def money(v: Optional[float], cur: str = "USD") -> str:
    if v is None:
        return "—"
    return f"{cur} {v:.5f}" if v < 1 else f"{cur} {v:.2f}"
