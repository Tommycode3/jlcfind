"""HTTP client for jlcsearch + LCSC detail. stdlib urllib, cached, rate-limited."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .cache import Cache
from .config import Config
from .models import Part


class JlcError(RuntimeError):
    pass


class JlcClient:
    def __init__(self, config: Optional[Config] = None, cache: Optional[Cache] = None,
                 fresh: bool = False):
        self.cfg = config or Config.load()
        self.cache = cache if cache is not None else Cache()
        self.fresh = fresh
        self._last_call = 0.0

    # ---- low level ----
    def _throttle(self) -> None:
        delta = time.monotonic() - self._last_call
        wait = self.cfg.rate_limit_seconds - delta
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, url: str, ttl_hours: Optional[float] = None, retries: int = 3) -> dict:
        ttl = (self.cfg.cache_ttl_hours if ttl_hours is None else ttl_hours) * 3600.0
        key = url
        if not self.fresh:
            cached = self.cache.get(key, ttl)
            if cached is not None:
                return json.loads(cached)

        last_err: Optional[Exception] = None
        for attempt in range(retries):
            self._throttle()
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": self.cfg.user_agent,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    body = resp.read().decode("utf-8", "replace")
                data = json.loads(body)
                self.cache.set(key, json.dumps(data))
                return data
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise JlcError(f"HTTP {e.code} for {url}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                time.sleep(1.0 * (attempt + 1))
            except json.JSONDecodeError as e:
                raise JlcError(f"Non-JSON response from {url}") from e
        raise JlcError(f"Request failed after {retries} attempts: {url} ({last_err})")

    # ---- public API ----
    def components_list(self, search: str = "", package: str = "",
                        is_basic: Optional[bool] = None, category: str = "",
                        limit: int = 50) -> list[Part]:
        """Rich endpoint: includes price tiers, category, basic/preferred flags."""
        params = {"limit": str(limit)}
        if search:
            params["search"] = search
        if package:
            params["package"] = package
        if category:
            params["category"] = category
        if is_basic is not None:
            params["is_basic"] = "true" if is_basic else "false"
        url = f"{self.cfg.base_url}/components/list?" + urllib.parse.urlencode(params)
        data = self._get(url)
        return [Part.from_api(c) for c in data.get("components", [])]

    def search_text(self, q: str, limit: int = 10) -> list[Part]:
        """Fallback full-text endpoint."""
        params = {"q": q, "limit": str(limit), "full": "true"}
        url = f"{self.cfg.base_url}/api/search?" + urllib.parse.urlencode(params)
        data = self._get(url)
        return [Part.from_api(c) for c in data.get("components", [])]

    def lookup(self, code_or_mpn: str, limit: int = 25) -> list[Part]:
        """Resolve a known LCSC code (Cxxxx) or MPN to candidate parts."""
        term = code_or_mpn.strip()
        if term.upper().startswith("C") and term[1:].isdigit():
            term = term[1:]  # jlcsearch matches the numeric id within the MPN/full-text
        parts = self.components_list(search=term, limit=limit)
        if not parts:
            parts = self.search_text(code_or_mpn, limit=limit)
        return parts

    def datasheet_url(self, lcsc_code: str) -> str:
        """LCSC product-detail endpoint exposes the canonical PDF URL."""
        code = lcsc_code if lcsc_code.upper().startswith("C") else f"C{lcsc_code}"
        url = f"{self.cfg.lcsc_detail_url}?productCode={urllib.parse.quote(code)}"
        try:
            data = self._get(url, ttl_hours=24 * 30)  # datasheets are stable
        except JlcError:
            return ""
        result = data.get("result") or data
        for k in ("pdfUrl", "datasheetUrl", "datasheet"):
            v = result.get(k) if isinstance(result, dict) else None
            if v:
                return str(v)
        return ""
