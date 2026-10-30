"""User config + filesystem paths. JSON config so it is read/write with stdlib."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

APP_DIR = Path(os.environ.get("JLCFIND_HOME", Path.home() / ".jlcfind"))
CONFIG_PATH = APP_DIR / "config.json"
CACHE_PATH = APP_DIR / "cache.db"

# JLCPCB economics (mid-2026 defaults; override in config.json).
# Basic AND Preferred extended parts carry no per-part setup fee at JLCPCB;
# only "standard" Extended parts do. Fees are one-time per distinct part number.
DEFAULTS = {
    "prefer_basic": True,
    "min_stock": 0,
    "default_board_qty": 5,
    "extended_part_fee_usd": 3.0,
    "currency": "USD",
    "cache_ttl_hours": 24,
    "rate_limit_seconds": 0.5,
    "base_url": "https://jlcsearch.tscircuit.com",
    "lcsc_detail_url": "https://wmsc.lcsc.com/ftps/wm/product/detail",
    "user_agent": "jlcfind/0.1 (+https://github.com/Tommycode3/jlcfind)",
    "search_overfetch": 60,  # rows pulled before ranking
}


@dataclass
class Config:
    prefer_basic: bool = DEFAULTS["prefer_basic"]
    min_stock: int = DEFAULTS["min_stock"]
    default_board_qty: int = DEFAULTS["default_board_qty"]
    extended_part_fee_usd: float = DEFAULTS["extended_part_fee_usd"]
    currency: str = DEFAULTS["currency"]
    cache_ttl_hours: float = DEFAULTS["cache_ttl_hours"]
    rate_limit_seconds: float = DEFAULTS["rate_limit_seconds"]
    base_url: str = DEFAULTS["base_url"]
    lcsc_detail_url: str = DEFAULTS["lcsc_detail_url"]
    user_agent: str = DEFAULTS["user_agent"]
    search_overfetch: int = DEFAULTS["search_overfetch"]

    @classmethod
    def load(cls) -> "Config":
        data = dict(DEFAULTS)
        if CONFIG_PATH.exists():
            try:
                data.update(json.loads(CONFIG_PATH.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
        known = {k: data[k] for k in data if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2))


def ensure_app_dir() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR
