# utils/ranking/dedupe.py
from __future__ import annotations
from typing import Any, Dict, Optional
import hashlib
import json

# Stable, compact hashing for identity/tie-breaks
def _shorthash(obj: Any, length: int = 16) -> str:
    # json.dumps sorts keys to keep determinism
    b = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8", "ignore")
    return hashlib.sha1(b).hexdigest()[:length]

def _norm_str(x: Optional[str]) -> str:
    if not x:
        return ""
    x = x.strip().lower()
    # lightweight slugging without regex deps
    return "".join(ch if ch.isalnum() or ch in " -" else " " for ch in x).replace("  ", " ").strip()

def _round_or_none(x: Any, ndigits: int = 5) -> Optional[float]:
    try:
        xf = float(x)
    except Exception:
        return None
    return round(xf, ndigits)

# ------------ public: hotel identity (used in hotel ranker) ------------
def hotel_key(
    *,
    name: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    address_line1: Optional[str],
    city: Optional[str],
    brand: Optional[str],
) -> str:
    """
    Generate a stable identity for a hotel combining name/brand and coarse geocode/address.
    Used for deterministic tie-breaks and de-duping.
    """
    payload = {
        "n": _norm_str(name),
        "b": _norm_str(brand),
        "a": _norm_str(address_line1),
        "c": _norm_str(city),
        "lat": _round_or_none(lat, 4),
        "lon": _round_or_none(lon, 4),
    }
    return _shorthash(payload)

# ------------ public: rate/room identity (for rooms ranker) ------------
def rate_key(
    *,
    hotel_id: Any,
    rate_id: Any = None,
    name: Optional[str] = None,
    bed_config: Optional[list] = None,   # list of strings like ["1 King Bed", "Sofa Bed"]
    refundable: Optional[bool] = None,
    provider_id: Optional[str] = None,
) -> str:
    """
    Stable identity for a specific sellable rate.
    Prefer explicit rate_id if present; otherwise hash salient fields.
    """
    if rate_id:
        return _shorthash({"hid": hotel_id, "rid": rate_id})
    payload = {
        "hid": hotel_id,
        "n": _norm_str(name),
        "beds": [ _norm_str(b) for b in (bed_config or []) ],
        "ref": bool(refundable),
        "prov": _norm_str(provider_id),
    }
    return _shorthash(payload)

# ------------ public: search key (already used in hotel ranker) ------------
def search_key(params: Dict[str, Any], policy: Dict[str, Any], source: str) -> str:
    """
    Deterministic cache/VFS key based on request params (+ source + policy bits).
    Safe to use as your VFS map key.
    """
    # Remove volatile fields if any (e.g., cursor)
    p = dict(params or {})
    p.pop("cursor", None)

    base = {
        "source": source,
        "params": p,
        "policy": policy or {},
    }
    return _shorthash(base, length=24)