"""Download datasheet PDFs for resolved parts; write a manifest.json."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .client import JlcClient
from .resolve import ResolvedLine


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "part"


def _download(url: str, dest: Path, user_agent: str) -> tuple[bool, str, int]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = resp.read()
        if not data:
            return False, "empty response", 0
        dest.write_bytes(data)
        return True, "", len(data)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return False, str(e), 0


def download_datasheets(resolved: list[ResolvedLine], outdir: str | Path,
                        client: Optional[JlcClient] = None,
                        progress=None) -> dict:
    client = client or JlcClient()
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_path = outdir / "manifest.json"
    manifest = {"source": "jlcfind", "parts": {}}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest.setdefault("parts", {})
        except json.JSONDecodeError:
            pass

    seen: set[str] = set()
    items = [r for r in resolved if r.has_part]
    for i, r in enumerate(items):
        p = r.part
        key = p.mpn or p.lcsc_code
        if key in seen:
            continue
        seen.add(key)
        if progress:
            progress(i + 1, len(items), key)

        url = p.datasheet_url or client.datasheet_url(p.lcsc_code)
        entry = manifest["parts"].get(key, {})
        refs = sorted(set(entry.get("references", []) + r.line.designators))
        if not url:
            manifest["parts"][key] = {
                **entry, "manufacturer": p.manufacturer, "lcsc": p.lcsc_code,
                "status": "no_url", "references": refs, "source": "jlcfind",
            }
            continue
        fname = f"{_safe_name(key)}.pdf"
        dest = outdir / fname
        if dest.exists() and dest.stat().st_size > 0:
            ok, err, size = True, "", dest.stat().st_size
        else:
            ok, err, size = _download(url, dest, client.cfg.user_agent)
            time.sleep(0.3)
        manifest["parts"][key] = {
            "file": fname if ok else "",
            "manufacturer": p.manufacturer,
            "description": p.description,
            "lcsc": p.lcsc_code,
            "datasheet_url": url,
            "status": "ok" if ok else "failed",
            "error": err,
            "size_bytes": size,
            "references": refs,
            "source": "jlcfind",
        }

    manifest_path.write_text(json.dumps(manifest, indent=2))
    ok_n = sum(1 for v in manifest["parts"].values() if v.get("status") == "ok")
    return {"outdir": str(outdir), "ok": ok_n, "total": len(seen),
            "manifest": str(manifest_path)}
