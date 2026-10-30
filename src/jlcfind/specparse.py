"""Parse human spec strings like '100nF 0402 X7R 16V' into a structured SearchSpec."""
from __future__ import annotations

import re

from .models import SearchSpec, RESISTOR, CAPACITOR, INDUCTOR, UNKNOWN

# Common SMD/THT package tokens (case-insensitive match against the token).
_PACKAGE_RE = re.compile(
    r"^(0201|0402|0603|0805|1206|1210|1812|2010|2512|"
    r"sot-?23(?:-\d)?|sot-?89|sot-?223|sod-?123|sod-?323|sod-?882|"
    r"sma|smb|smc|do-?214[a-c]{2}|"
    r"qfn-?\d*|tqfp-?\d*|lqfp-?\d*|tssop-?\d*|ssop-?\d*|msop-?\d*|"
    r"soic-?\d*|sop-?\d*|dfn-?\d*|bga-?\d*|to-?\d+|sot-?\d+)$",
    re.IGNORECASE,
)

_DIELECTRIC = {"x7r", "x5r", "x7s", "x6s", "c0g", "np0", "y5v", "x8r", "x8l"}

_VALUE_RE = re.compile(
    r"^([0-9]*\.?[0-9]+)\s*"
    r"(p|n|u|µ|m|k|meg|M|g)?\s*"
    r"(f|farad|h|henry|r|ohm|ohms|Ω|R)?$",
    re.IGNORECASE,
)
# Resistor "R/k/M" code style: 4k7, 1R0, 100R, 10k, 2M2
_RES_CODE_RE = re.compile(r"^([0-9]+)([rkm])([0-9]*)$", re.IGNORECASE)

_SI = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
    "": 1.0, "k": 1e3, "meg": 1e6, "g": 1e9,
}
_RES_MULT = {"r": 1.0, "k": 1e3, "m": 1e6}


def _norm_package(tok: str) -> str:
    return tok.upper().replace("SOT23", "SOT-23")


def _parse_resistor_code(tok: str):
    m = _RES_CODE_RE.match(tok)
    if not m:
        return None
    whole, mult, frac = m.groups()
    base = float(f"{whole}.{frac}") if frac else float(whole)
    return base * _RES_MULT[mult.lower()]


def _parse_value(tok: str):
    """Return (value_in_SI, ctype, normalized_text) or None."""
    rc = _parse_resistor_code(tok)
    if rc is not None:
        return rc, RESISTOR, tok
    m = _VALUE_RE.match(tok)
    if not m:
        return None
    num, prefix, unit = m.groups()
    num = float(num)
    prefix = (prefix or "").lower()
    unit = (unit or "").lower()
    if unit in ("f", "farad"):
        mult = _SI.get(prefix, None)
        if mult is None:
            return None
        return num * mult, CAPACITOR, tok
    if unit in ("h", "henry"):
        mult = _SI.get(prefix, None)
        if mult is None:
            return None
        return num * mult, INDUCTOR, tok
    if unit in ("r", "ohm", "ohms", "ω"):
        # k/M here mean kilo/mega-ohm
        mult = {"k": 1e3, "m": 1e6, "meg": 1e6, "": 1.0}.get(prefix, 1.0)
        return num * mult, RESISTOR, tok
    # bare number + magnitude prefix and no unit -> ambiguous, treat as resistor
    if prefix in ("k", "m", "meg") and not unit:
        mult = {"k": 1e3, "m": 1e6, "meg": 1e6}[prefix]
        return num * mult, RESISTOR, tok
    return None


def parse_spec(text: str) -> SearchSpec:
    spec = SearchSpec(raw=text.strip())
    tokens = text.replace(",", " ").split()
    for tok in tokens:
        low = tok.lower()
        # package
        if _PACKAGE_RE.match(tok):
            spec.package = _norm_package(tok)
            continue
        # dielectric
        if low in _DIELECTRIC:
            spec.dielectric = tok.upper()
            if spec.ctype == UNKNOWN:
                spec.ctype = CAPACITOR
            continue
        # tolerance
        if re.fullmatch(r"[±+-]?\d+(\.\d+)?%", tok) or low in ("1%", "5%", "10%", "0.1%"):
            spec.tolerance = tok.lstrip("+±")
            continue
        # voltage
        if re.fullmatch(r"\d+(\.\d+)?v", low):
            spec.voltage = tok.upper()
            continue
        # value
        v = _parse_value(tok)
        if v is not None and spec.value is None:
            spec.value, ctype, vtext = v
            spec.value_text = vtext
            if spec.ctype == UNKNOWN:
                spec.ctype = ctype
            continue
        # leftover keyword
        spec.keywords.append(tok)
    # dielectric implies capacitor; H implies inductor (already set)
    if spec.dielectric and spec.ctype == UNKNOWN:
        spec.ctype = CAPACITOR
    return spec
