# jlcfind

A Python CLI with no dependencies that maps a whole BOM to JLCPCB/LCSC part numbers, prices it at the quantity you actually order, downloads the datasheets and zips up a fab package. Each pick comes with the reasons it was chosen, and lines it is unsure about are marked `ambiguous` instead of guessed. The JLCPCB web UI does this one part at a time.

## Usage

Requires Python 3.11+. `rich` is optional, for nicer tables.

```bash
git clone https://github.com/Tommycode3/jlcfind && cd jlcfind
pipx install .                 # or: pip install .
PYTHONPATH=src python3 -m jlcfind --help   # without installing
```

```bash
jlcfind search "100nF 0402 X7R 16V"            # parametric search, ranked + reasons
jlcfind part C2128 --json                      # tier, stock, price breaks, datasheet
jlcfind resolve examples/sample_bom.csv        # BOM -> audit CSV (status per line)
jlcfind cost examples/sample_bom.csv --qty 50 --out cost.md
jlcfind bom examples/sample_bom.csv --out jlc_bom.csv   # JLCPCB assembly BOM format
jlcfind datasheets examples/sample_bom.csv     # PDFs + manifest.json
jlcfind package examples/sample_bom.csv --qty 50 \
    --gerbers ./gerbers --cpl ./cpl.csv --out board_fab.zip
```

Most commands accept `--json` and `--fresh` (bypass cache). Config and cache live in `~/.jlcfind/` (override with `JLCFIND_HOME`):

```bash
jlcfind config --set extended_part_fee_usd=3 default_board_qty=10 prefer_basic=true
jlcfind cache --clear
```

Tests run offline: `pip install pytest && python3 -m pytest`.

## Resolving a BOM

Headers from KiCad, JLCPCB and generic exports are matched by synonym (`LCSC Part #`, `Manufacturer Part Number`, `Comment`/`Value`, `Footprint`/`Package`, ...). Designator lists are split and ranges like `R1-R4` expanded; quantity defaults to the designator count.

Each line is tried by LCSC code, then MPN, then value + footprint, and the first match wins. An exact code or MPN match is `resolved`. A parametric hit is `resolved` only if it is Basic/Preferred, its package contains the requested one, and the requested value appears in its MPN or description. Everything else is `ambiguous` with a note on what to check, because a wrong part on an assembled board costs far more than a manual review.

Free text like `4k7 0603 1%` is parsed into package, value (SI prefixes, `4k7` $= 4.7\cdot10^{3}\,\Omega$, `1R0` $=1\,\Omega$), dielectric, tolerance and voltage. The unit picks a category hint for the API query.

## Ranking and cost

Search over-fetches 60 rows, drops parts below `min_stock`, and sorts by an additive score. For tier $t$, stock $s$ and lowest unit price $p$ (USD):

$$
S = T(t) + P + V + \sigma(s) + \pi(p),
\qquad
T = \begin{cases}1000 & \text{Basic}\\ 650 & \text{Preferred}\\ 0 & \text{Extended}\end{cases}
\qquad
P = \begin{cases}+220 & \text{package equal}\\ +120 & \text{package contains request}\\ -150 & \text{mismatch}\end{cases}
$$

$$
V = \begin{cases}+160 & \text{value token found}\\ 0 & \text{otherwise}\end{cases}
\qquad
\sigma(s) = \begin{cases}\min\!\big(20\log_{10}(s+1),\ 120\big) & s>0\\ -500 & s=0\end{cases}
\qquad
\pi(p) = \max\!\big(0,\ 60 - 12\log_{10}(1000\,p+1)\big)
$$

Tier dominates because an Extended part carries a one-time setup fee that, on small runs, dwarfs any unit-price difference. Stock and price are logarithmic and capped so they only break ties. The weights are hand-tuned, not fitted, and every term that fires is printed as a reason by `search` and written to the audit CSV by `resolve`.

For $N$ boards and line $i$ with $q_i$ parts per board, $Q_i = q_i N$ and the unit price $u_i(Q_i)$ comes from the price break containing $Q_i$ (the first break if below it). With $E$ the distinct Extended parts and $F$ the setup fee (default 3 USD):

$$
C_{\text{total}} = \sum_i u_i(Q_i)\,Q_i \;+\; F\,|E|,
\qquad
C_{\text{board}} = \frac{C_{\text{total}}}{N}
$$

`ambiguous` lines are costed, `unresolved` lines are excluded, and a warning fires when stock is below $Q_i$. Fabrication, assembly labour and shipping are not included.

Networking is stdlib `urllib` against the free jlcsearch API plus the LCSC product-detail endpoint, throttled to 0.5 s spacing, retried with linear backoff, and cached in SQLite: 24 h for search/stock/price, 30 days for datasheet URLs. Gerbers and CPL are bundled, not generated, so it works with KiCad, Altium or EasyEDA exports.

## Limitations

Version 0.1.0. 23 offline unit tests cover spec parsing, BOM I/O, price breaks, cost and resolution status; the network code is tested by hand, not in CI.

- Upstream search quality is the main limit. On 2026-10-30 jlcsearch returned unrelated parts for several queries (an MPN search for `STM32F103C8T6` returned an LDO; `10k 0402` returned an inductor). jlcfind marks these `ambiguous`, but it cannot return a part the API doesn't. Exact LCSC-code lookups were reliable in the same test.
- Value matching is a substring check: `100nF` won't match `0.1uF`, and `1k` can match `11k`.
- Fees follow JLCPCB's Basic/Preferred/Extended policy as of the default config; check jlcpcb.com before ordering.
- The LCSC detail endpoint is undocumented. If it changes, datasheet URLs come back empty.
- The CPL check only looks at headers.

## License

MIT. See [LICENSE](LICENSE).
