# utils/ranking/rank_hotels.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import heapq
import time
import math
import re

from .policies import HOTELS_WEIGHTS, VERSION, DEFAULT_TTLS, CAPS, MARGIN_CLIP
from .dedupe import hotel_key, search_key
from .cursors import make_cursor

# If you use the typed path:
try:
    from ava.utils.parsers.hotel_schema import Envelope  # soft import
except Exception:  # pragma: no cover
    Envelope = object  # type: ignore

# -------------------------- tiny text utils --------------------------

_ws_re = re.compile(r"\s+")
_punct_re = re.compile(r"[^\w\s]")

def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower()
    s = _punct_re.sub(" ", s)
    s = _ws_re.sub(" ", s).strip()
    return s

def _token_set_ratio(a: str, b: str) -> float:
    """
    Lightweight fuzzy score in [0,1]: 2*|∩|/(|A|+|B|) over token sets.
    Works like a simplified token-set ratio; fast, no deps.
    """
    if not a or not b:
        return 0.0
    A = set(_norm(a).split())
    B = set(_norm(b).split())
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return (2.0 * inter) / (len(A) + len(B))

def _fuzzy_contains_any(needles: List[str], haystacks: List[str], threshold: float = 0.6) -> Tuple[float, List[str]]:
    """
    Returns (best_score, matched_needles[]) where best_score is the max fuzzy score across pairs,
    and matched_needles are those needles that achieved >= threshold against ANY haystack.
    """
    best = 0.0
    matched: List[str] = []
    hs = [h for h in haystacks if h]
    for n in needles or []:
        n_norm = _norm(n)
        hit = False
        for h in hs:
            score = _token_set_ratio(n_norm, h)
            if score > best:
                best = score
            if score >= threshold:
                hit = True
        if hit:
            matched.append(n)
    return best, matched

# -------------------------- geo helpers --------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def _distance_score_within_radius(dist_km: Optional[float], radius_km: Optional[float]) -> float:
    """
    Returns a smooth score in [0,1] where:
      - 1.0 at the center, smoothly decays to ~0 at radius
      - 0.0 if outside radius
      - neutral 0.5 if radius or distance is unknown
    """
    if dist_km is None or radius_km is None or radius_km <= 0:
        return 0.5
    if dist_km >= radius_km:
        return 0.0
    x = dist_km / radius_km
    return max(0.0, 1.0 - x * x)

# --------------------- pricing / value helpers -------------------

def _compute_est_all_in(
    published: Optional[float],
    total: Optional[float],
    base: Optional[float],
    taxes: Optional[float],
    fee: Optional[float],
) -> Optional[float]:
    """
    estAllInPrice = parity + ourServiceFee + taxes_if_needed

    Assumptions:
    - publishedRate ("parity") is pre-tax -> add taxes + fee.
    - totalRate already includes taxes -> add fee only.
    - baseRate is pre-tax -> add taxes + fee.
    """
    f = float(fee) if isinstance(fee, (int, float)) else 0.0
    t = float(taxes) if isinstance(taxes, (int, float)) else 0.0

    if isinstance(published, (int, float)) and published > 0:
        return float(published) + f + t
    if isinstance(total, (int, float)) and total > 0:
        return float(total) + f
    if isinstance(base, (int, float)) and base > 0:
        return float(base) + f + t
    return None

def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    m = n // 2
    if n % 2:
        return float(s[m])
    return 0.5 * (s[m - 1] + s[m])

# ------------------ feature / scoring helpers --------------------

def _amenity_soft_score(required: List[str], got: List[str], threshold: float = 0.6) -> Tuple[float, List[str]]:
    """
    Soft fuzzy: for each required amenity term, consider it matched if ANY got amenity has fuzzy >= threshold.
    Score = (#matched / #required) in [0,1]. Returns (score, matched_required_list).
    """
    if not required:
        return 0.5, []  # Neutral score when no amenities requested
    matched = []
    got_norm = [_norm(g) for g in got if g]
    for req in required:
        req_norm = _norm(req)
        if any(_token_set_ratio(req_norm, g) >= threshold for g in got_norm):
            matched.append(req)
    return (len(matched) / max(1, len(required))), matched

def _brand_soft_score(allowed: List[str], brand_name: Optional[str], chain_name: Optional[str], threshold: float = 0.6) -> Tuple[float, List[str]]:
    """
    Soft fuzzy brand score in [0,1] based on the best match against brandName/chainName.
    Returns (best_score, matched_allowed_list).
    """
    if not allowed:
        return 1.0, []
    hay = []
    if brand_name:
        hay.append(brand_name)
    if chain_name:
        hay.append(chain_name)
    score, matched = _fuzzy_contains_any(allowed, hay, threshold=threshold)
    return (score if hay else 0.5), matched  # neutral if no brand/chain given

def _review_quality(score_0_5: Optional[float], count: Optional[int]) -> float:
    if score_0_5 is None:
        return 0.5
    base = max(0.0, min(1.0, float(score_0_5) / 5.0))
    bonus = 0.1 if (count or 0) > 200 else 0.0
    return max(0.0, min(1.0, base + bonus))

def _value_score(price: Optional[float], cohort_median: Optional[float]) -> float:
    if not price or price <= 0 or not cohort_median or cohort_median <= 0:
        return 0.5
    v = cohort_median / price
    return 1.0 if v >= 1.0 else max(0.0, float(v))

def _extract_percentage_offer(offers: Any) -> Optional[float]:
    if not isinstance(offers, list) or not offers:
        return None
    o = offers[0] or {}
    pct = o.get("percentageDiscountOffer")
    try:
        return float(pct) if pct is not None else None
    except Exception:
        return None

# ---------------------- margin helpers ---------------------------

def _margin_from_engine(
    total: Optional[float],
    published: Optional[float],
    engine_markup: Optional[float],  # dollars vs net
    engine_fee: Optional[float],     # dollars vs parity
) -> Optional[float]:
    if published and isinstance(published, (int, float)) and published > 0:
        if engine_markup is not None and isinstance(engine_markup, (int, float)) and engine_markup >= 0:
            return float(engine_markup) / float(published)
        if total and isinstance(total, (int, float)) and 0 < total < published:
            return (float(published) - float(total)) / float(published)
        if engine_fee is not None and isinstance(engine_fee, (int, float)) and engine_fee >= 0:
            return float(engine_fee) / float(published)
    return None

def _margin_proxy(
    total: Optional[float],
    published: Optional[float],
    percent_offer: Optional[float],
    engine_markup: Optional[float],
    engine_fee: Optional[float],
) -> float:
    lo, hi = MARGIN_CLIP
    pct = _margin_from_engine(total, published, engine_markup, engine_fee)
    if pct is None and percent_offer is not None:
        try:
            pct = max(0.0, float(percent_offer) / 100.0)
        except Exception:
            pct = None
    if pct is None:
        return 0.5
    return max(0.0, min(1.0, (float(pct) - lo) / max(1e-9, hi - lo)))

# -------------------- compact projection helpers ----------------

def _project_compact_hotels(hotels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten heavy ranked hotels into a lightweight view for in-memory VFS or LLM.
    """
    out: List[Dict[str, Any]] = []
    for h in hotels:
        out.append({
            "id": h.get("hotelId") or h.get("id"),
            "name": h.get("name"),
            "desc": h.get("description"),
            "brandName": h.get("brandName"),
            "propertyType": h.get("propertyType"),
            # Prefer original-cased facility names if present; fallback to normalized
            "facilities": h.get("facilitiesDisplay") or h.get("amenities") or [],
            "starRating": h.get("starRating"),
            "filtersMatched": h.get("filtersMatched", {}),
            "estPriceAllIn": h.get("estAllInPrice"),
        })
    return out

# ---------------------- main (dict entrypoint) -------------------

def rank_hotels(
    payload: Dict[str, Any],
    *,
    params: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
    top_k: int = 3,
    source: str = "hotel_search",
) -> Dict[str, Any]:
    """
    Soft & fuzzy filters for brands/amenities; soft region. Always returns results.
    Adds filtersMatched per hotel; includes description and estAllInPrice.

    RETURNS:
      {
        "hotels":        <top_k compact hotels for the LLM>,
        "nextCursor":    <cursor>,
        "vfsHotels":     <compact frozen list up to CAP (e.g., 50) for storing in VFS>,
        "meta":          <light meta if you want to stash it alongside>,
      }
    """
    weights = (policy or {}).get("weights") or HOTELS_WEIGHTS
    ttl = (policy or {}).get("ttlSec") or DEFAULT_TTLS.get(source, 600)
    cap = int((policy or {}).get("cap") or CAPS["hotels"] or 50)

    # honor request limit for the top slice
    top_k = int(params.get("limit", top_k) or top_k)

    status = payload.get("status")
    token = payload.get("token")
    hotels_in = payload.get("hotels") or []

    if status and status.lower() != "complete":
        meta = {
            "searchKey": search_key(params, {"weights": weights, "ttlSec": ttl}, source),
            "fetchedAt": int(time.time()),
            "ttlSec": ttl,
            "version": VERSION,
            "weights": weights,
            "params": params,
            "provenance": {"source": source, "token": token},
            "status": status,
        }
        # even when incomplete, we keep the return shape stable
        return {
            "hotels": [],
            "nextCursor": make_cursor(meta["searchKey"], 0, VERSION),
            "vfsHotels": [],
            "meta": meta,
        }

    # ---- precompute region ----
    region = params.get("circularRegion") or {}
    lat0 = region.get("centerLat")
    lon0 = region.get("centerLong")
    radius_km_param = region.get("radiusInKM")

    required = (params.get("filters") or {})
    req_amen = required.get("amenities") or []
    req_brands = required.get("brands") or []
    star_min = required.get("starMin")

    items: List[Dict[str, Any]] = []
    prices: List[float] = []

    for h in hotels_in:
        content = h.get("content") or {}
        rate = h.get("rate") or {}

        name = content.get("name")
        brand = content.get("brandName")
        chain = content.get("chainName")
        stars = content.get("starRating")
        description = content.get("description")
        property_type = content.get("propertyType")

        geo = content.get("geocode") or {}
        lat = geo.get("lat")
        lon = geo.get("long")

        # distance (soft)
        dist_km = None
        radius_km = radius_km_param if isinstance(radius_km_param, (int, float)) else None
        if lat0 is not None and lon0 is not None and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            dist_km = _haversine_km(float(lat), float(lon), float(lat0), float(lon0))

        contact = content.get("contact") or {}
        address = contact.get("address") or {}
        addr_line1 = address.get("line1")
        city_name = (address.get("city") or {}).get("name")

        facilities = content.get("facilities") or []
        # Keep original-cased names for display & normalized for matching
        facilities_display = [f.get("name") for f in facilities if isinstance(f, dict) and f.get("name")]
        amenity_names = [f.get("name", "").strip().lower() for f in facilities if isinstance(f, dict)]

        # SOFT fuzzy scores (no exclusion)
        amen_score, matched_amen = _amenity_soft_score(req_amen, amenity_names, threshold=0.6)
        brand_score, matched_brands = _brand_soft_score(req_brands, brand, chain, threshold=0.6)

        # starMin soft check (for filtersMatched; small effect on quality below)
        star_pass = True
        if star_min is not None:
            try:
                star_pass = (stars or 0) >= float(star_min)
            except Exception:
                star_pass = False

        # distance within radius? (for filtersMatched only)
        within_radius = None
        if radius_km is not None and dist_km is not None:
            within_radius = dist_km <= float(radius_km)

        total = rate.get("totalRate")
        base_rate = rate.get("baseRate")
        taxes = rate.get("taxes")
        published = rate.get("publishedRate")
        engine_fee = rate.get("ourServiceFee")
        engine_markup = rate.get("ourTotalMarkup")

        total_f = float(total) if isinstance(total, (int, float)) else None
        base_f = float(base_rate) if isinstance(base_rate, (int, float)) else None
        taxes_f = float(taxes) if isinstance(taxes, (int, float)) else None
        published_f = float(published) if isinstance(published, (int, float)) else None
        engine_fee_f = float(engine_fee) if isinstance(engine_fee, (int, float)) else None
        engine_markup_f = float(engine_markup) if isinstance(engine_markup, (int, float)) else None

        est_all_in = _compute_est_all_in(
            published=published_f, total=total_f, base=base_f, taxes=taxes_f, fee=engine_fee_f
        )

        # cohort median built on est_all_in (fallback to total)
        if isinstance(est_all_in, (int, float)) and est_all_in > 0:
            prices.append(float(est_all_in))
        elif total_f and total_f > 0:
            prices.append(float(total_f))

        percent_offer = _extract_percentage_offer(rate.get("offers"))

        item = {
            "hotelId": content.get("id", h.get("id")),
            "name": name,
            "description": description,
            "brandName": brand,
            "chainName": chain,
            "propertyType": property_type,
            "starRating": stars,
            "reviewScore": (content.get("review") or {}).get("rating"),
            "reviewCount": (content.get("review") or {}).get("count"),
            "lat": lat,
            "lon": lon,
            "distanceKm": dist_km,
            "radiusKm": radius_km,
            "addressLine1": addr_line1,
            "cityName": city_name,
            "amenities": amenity_names,
            "facilitiesDisplay": facilities_display,  # <- for compact output
            "price": {
                "total": total_f,
                "base": base_f,
                "taxes": taxes_f,
                "currency": getattr(rate, "currency", "USD"),
                "refundable": bool(getattr(rate, "refundable", False)),
                "payAtHotel": bool(getattr(rate, "payAtHotel", False)),
            },
            "provider": {"id": getattr(rate, "providerId", None), "name": getattr(rate, "providerName", None)},
            "publishedRate": published_f,
            "ourServiceFee": engine_fee_f,
            "ourTotalMarkup": engine_markup_f,
            "percentageDiscountOffer": percent_offer,
            "estAllInPrice": est_all_in,
            "estPriceAllIn": est_all_in,
            # what matched (for LLM explanations)
            "filtersMatched": {
                "matchedBrands": matched_brands,
                "matchedAmenities": matched_amen,
                "brandScore": round(brand_score, 3),
                "amenitiesScore": round(amen_score, 3),
                "starMinPassed": bool(star_pass),
                "distanceWithinRadius": within_radius,
            },
            "score": 0.0,
            "hotelKey": "",
            "tieBreak": "",
        }
        items.append(item)

    cohort_median = _median(prices) if prices else None

    # build scores
    top_heap: List[Tuple[float, str, Dict[str, Any]]] = []
    for it in items:
        # userFit combines amenities (soft), distance (soft), and brand (soft)
        amen_s = it["filtersMatched"]["amenitiesScore"] or 0.0
        dist_s = _distance_score_within_radius(it.get("distanceKm"), it.get("radiusKm"))
        brand_s = it["filtersMatched"]["brandScore"] or 0.0

        # weights within userFit: 0.4 amenities, 0.3 distance, 0.3 brand (increased brand weight)
        user_fit = 0.4 * amen_s + 0.3 * dist_s + 0.3 * brand_s

        # value uses estAllInPrice (fallback to provider total)
        price_for_value = it.get("estAllInPrice") or (it["price"] or {}).get("total")
        value = _value_score(price_for_value, cohort_median)

        # margin: prefer engine, fallback to discount math
        mar = _margin_proxy(
            (it["price"] or {}).get("total"),
            it.get("publishedRate"),
            it.get("percentageDiscountOffer"),
            it.get("ourTotalMarkup"),
            it.get("ourServiceFee"),
        )

        # quality with small malus if starMin failed (soft)
        qual = _review_quality(it.get("reviewScore"), it.get("reviewCount"))
        stars = it.get("starRating") or 0
        if isinstance(stars, (int, float)) and stars >= 4:
            qual = min(1.0, qual + 0.05)
        if (params.get("filters") or {}).get("starMin") is not None and not it["filtersMatched"]["starMinPassed"]:
            qual = max(0.0, qual * 0.9)  # small soft penalty

        # Add brand bonus for exact brand matches
        brand_bonus = 0.0
        if it["filtersMatched"]["matchedBrands"]:
            brand_bonus = 0.2  # 20% bonus for brand matches
        
        sc = (
            HOTELS_WEIGHTS["userFit"] * user_fit
            + HOTELS_WEIGHTS["value"] * value
            + HOTELS_WEIGHTS["margin"] * mar
            + HOTELS_WEIGHTS["quality"] * qual
            + brand_bonus
        )
        it["score"] = round(float(sc), 6)

        # identity & tie-break
        it["hotelKey"] = hotel_key(
            name=it.get("name"),
            lat=it.get("lat"),
            lon=it.get("lon"),
            address_line1=it.get("addressLine1"),
            city=it.get("cityName"),
            brand=it.get("brandName"),
        )
        it["tieBreak"] = it["hotelKey"]

        heapq.heappush(top_heap, (it["score"], it["tieBreak"], it))
        if len(top_heap) > max(top_k, 8):
            heapq.heappop(top_heap)

    # cap to policy (e.g., 50), then freeze order
    if cap and len(items) > cap:
        items = heapq.nlargest(cap, items, key=lambda x: (x["score"], x["tieBreak"]))

    hotels_sorted = sorted(items, key=lambda x: (-x["score"], x["tieBreak"]))
    top_slice = sorted([x[2] for x in top_heap], key=lambda x: (-x["score"], x["tieBreak"]))[:top_k]

    # --- compact projections ---
    vfs_hotels_compact = _project_compact_hotels(hotels_sorted)   # up to CAP (e.g., 50)
    top_slice_compact = _project_compact_hotels(top_slice)        # top_k only

    meta = {
        "searchKey": search_key(params, {"weights": HOTELS_WEIGHTS, "ttlSec": ttl}, source),
        "fetchedAt": int(time.time()),
        "ttlSec": int(ttl),
        "version": VERSION,
        "weights": HOTELS_WEIGHTS,
        "params": params,
        "provenance": {
            "source": source,
            "token": token,
            "completed": payload.get("completedHotelCount"),
            "expected": payload.get("expectedHotelCount"),
        },
        "status": status or "complete",
    }
    next_cursor = make_cursor(meta["searchKey"], pos=len(top_slice_compact), ver=VERSION)

    # Return only the compact top slice to the caller,
    # plus the compact 50 for VFS so your tool can store it.
    return {
        "hotels": top_slice_compact,   # <= top_k compact hotels (what the LLM sees)
        "nextCursor": next_cursor,
        "vfsHotels": vfs_hotels_compact,  # <= store this in your in-memory VFS
        "meta": meta,                    # optional to store alongside VFS
    }

# ------------------- typed entrypoint (msgspec) -------------------

def rank_hotels_typed(
    env: Envelope,
    *,
    params: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
    top_k: int = 3,
    source: str = "hotel_search",
) -> Dict[str, Any]:
    """
    Reuse dict implementation for one source of truth.
    """
    # For this msgspec version, convert to JSON and back to get plain dicts
    import msgspec
    import json
    payload_json = msgspec.json.encode(env)
    payload = msgspec.json.decode(payload_json)  # This gives us plain dicts/lists
    return rank_hotels(payload, params=params, policy=policy, top_k=top_k, source=source)