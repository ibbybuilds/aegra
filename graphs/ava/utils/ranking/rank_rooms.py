# utils/ranking/rank_rooms.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import heapq
import time
import re

from .policies import VERSION, DEFAULT_TTLS, CAPS, MARGIN_CLIP, ROOMS_WEIGHTS
from .cursors import make_cursor
from .dedupe import search_key, rate_key

# -------------------------- tiny text / fuzzy --------------------------

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
    if not a or not b:
        return 0.0
    A = set(_norm(a).split())
    B = set(_norm(b).split())
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return (2.0 * inter) / (len(A) + len(B))

def _soft_match_any(needles: List[str], haystacks: List[str], threshold: float = 0.6) -> Tuple[float, List[str]]:
    best = 0.0
    matched: List[str] = []
    hs = [h for h in haystacks if h]
    for n in needles or []:
        n_norm = _norm(n)
        hit = False
        for h in hs:
            score = _token_set_ratio(n_norm, h)
            best = max(best, score)
            if score >= threshold:
                hit = True
        if hit:
            matched.append(n)
    return best, matched

# --------------------- pricing / value helpers -------------------

def _sum_taxes(taxes_field: Any) -> float:
    """
    Support list-of-objects [{'amount': ...}, ...] or numeric or None.
    """
    if taxes_field is None:
        return 0.0
    if isinstance(taxes_field, (int, float)):
        return float(taxes_field)
    if isinstance(taxes_field, list):
        total = 0.0
        for t in taxes_field:
            try:
                amt = t.get("amount")
                if isinstance(amt, (int, float)):
                    total += float(amt)
            except Exception:
                continue
        return total
    return 0.0

def _compute_est_all_in(
    published: Optional[float],
    total: Optional[float],
    base: Optional[float],
    taxes_any: Any,
    fee: Optional[float],
) -> Optional[float]:
    """
    estAllInPrice = parity + ourServiceFee + taxes_if_needed
      - publishedRate (parity) is pre-tax -> add taxes + fee
      - totalRate is usually tax-inclusive -> add fee only
      - baseRate is pre-tax -> add taxes + fee
    """
    fee_f = float(fee) if isinstance(fee, (int, float)) else 0.0
    taxes_f = _sum_taxes(taxes_any)

    if isinstance(published, (int, float)) and published > 0:
        return float(published) + fee_f + taxes_f
    if isinstance(total, (int, float)) and total > 0:
        return float(total) + fee_f
    if isinstance(base, (int, float)) and base > 0:
        return float(base) + fee_f + taxes_f
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

def _value_score(price: Optional[float], cohort_median: Optional[float]) -> float:
    if not price or price <= 0 or not cohort_median or cohort_median <= 0:
        return 0.5
    v = cohort_median / price
    return 1.0 if v >= 1.0 else max(0.0, float(v))

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

def _compact_beds(beds_raw: Any) -> List[Dict[str, str]]:
    """
    Return a list of {"description": "..."} as per your desired output.
    """
    out: List[Dict[str, str]] = []
    if isinstance(beds_raw, list):
        for b in beds_raw:
            if isinstance(b, dict) and b.get("description"):
                out.append({"description": str(b["description"])})
            elif isinstance(b, str):
                out.append({"description": b})
    return out

def _project_compact_rooms(rooms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Minimal shape to persist in VFS and return to the LLM.
    """
    out: List[Dict[str, Any]] = []
    for r in rooms:
        out.append({
            "rateId": r.get("rateId"),
            "hotelId": r.get("hotelId"),
            "name": r.get("name"),
            "description": r.get("description") or r.get("name"),  # Use name as fallback if no description
            "beds": _compact_beds(r.get("bedsRaw")),
            "priceAllIn": r.get("estAllInPrice") or r.get("priceAllIn") or r.get("totalRate"),
            "currency": r.get("currency"),
            "cancellation": r.get("cancellationText"),
            "refundable": r.get("refundable"),
            "views": r.get("views") or [],
            "filterMatch": r.get("filterMatch") or [],
            "score": r.get("score"),  # Include the calculated score
        })
    return out

# ---------------------- core ranker (dict) ----------------------

def rank_rooms(
    payload: Dict[str, Any],
    *,
    params: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
    top_k: int = 1,
    source: str = "rooms_and_rates",
) -> Dict[str, Any]:
    """
    Rank rooms & rates from a hotel. Soft/fuzzy match filters. Always returns something.

    Returns:
      {
        "room":       <top_1 compact room for the LLM>,
        "nextCursor": <cursor>,
        "vfsRooms":   <compact frozen list up to CAP (e.g., 80) for storing in VFS>,
        "meta":       <light meta>,
      }
    """
    ttl = (policy or {}).get("ttlSec") or DEFAULT_TTLS.get(source, 600)
    cap = int((policy or {}).get("cap") or CAPS.get("rooms", 80))

    # filters you mentioned for rooms
    flt = (params.get("filters") or {})
    need_beds_min = flt.get("bedsMin")
    need_bed_type = flt.get("bedType")      # e.g., "King"
    need_breakfast = flt.get("breakfast")   # True/False/None
    need_views = flt.get("views")           # str or [str, ...]
    if isinstance(need_views, str):
        need_views = [need_views]

    status = payload.get("status")
    token = payload.get("token")

    # sample structure: {"hotel": {"rooms": [ {room}, ... ]}}
    hotel = payload.get("hotel") or {}
    rooms_list = hotel.get("rooms") or []

    if status and str(status).lower() != "complete":
        meta = {
            "searchKey": search_key(params, {"ttlSec": ttl}, source),
            "fetchedAt": int(time.time()),
            "ttlSec": ttl,
            "version": VERSION,
            "params": params,
            "provenance": {"source": source, "token": token},
            "status": status,
        }
        return {
            "room": None,
            "nextCursor": make_cursor(meta["searchKey"], 0, VERSION),
            "vfsRooms": [],
            "meta": meta,
        }

    items: List[Dict[str, Any]] = []
    prices: List[float] = []

    for room in rooms_list:
        room_name = room.get("name") or ""
        room_desc = room.get("description") or ""
        beds_raw = room.get("beds") or []  # list of {count, description}
        bed_texts = []
        if isinstance(beds_raw, list):
            for b in beds_raw:
                if isinstance(b, dict) and b.get("description"):
                    bed_texts.append(str(b["description"]))
                elif isinstance(b, str):
                    bed_texts.append(b)
        bed_texts_norm = [_norm(x) for x in bed_texts]

        # room-level views (some providers put on rate)
        views = room.get("views") or []
        if isinstance(views, str):
            views = [views]
        views_norm = [_norm(v) for v in views if v]

        # each room can have multiple rates (providers)
        for rate in (room.get("rates") or []):
            rate_id = rate.get("id")
            provider_id = rate.get("providerId")
            provider_name = rate.get("providerName")
            currency = rate.get("currency")

            total = rate.get("totalRate") or rate.get("priceAllIn")
            base = rate.get("baseRate")
            taxes_any = rate.get("taxes")
            published = rate.get("publishedRate")
            engine_fee = rate.get("ourServiceFee")
            engine_markup = rate.get("ourTotalMarkup")

            total_f = float(total) if isinstance(total, (int, float)) else None
            base_f = float(base) if isinstance(base, (int, float)) else None
            published_f = float(published) if isinstance(published, (int, float)) else None
            engine_fee_f = float(engine_fee) if isinstance(engine_fee, (int, float)) else None
            engine_markup_f = float(engine_markup) if isinstance(engine_markup, (int, float)) else None

            est_all_in = _compute_est_all_in(
                published=published_f, total=total_f, base=base_f, taxes_any=taxes_any, fee=engine_fee_f
            )
            if isinstance(est_all_in, (int, float)) and est_all_in > 0:
                prices.append(float(est_all_in))
            elif total_f and total_f > 0:
                prices.append(float(total_f))

            # policy text (keep for output; not used in score)
            cancellation_text = None
            cps = rate.get("cancellationPolicies")
            if isinstance(cps, list) and cps:
                cp0 = cps[0] or {}
                cancellation_text = cp0.get("text")

            # refundable / breakfast
            refundable = rate.get("refundable")
            name_norm = _norm(room_name + " " + room_desc)
            # board/inclusions may be in boardBasis or in name/desc
            board = rate.get("boardBasis") or {}
            has_breakfast = bool(board.get("description") and "breakfast" in _norm(board.get("description"))) \
                            or ("breakfast" in name_norm)

            # --- SOFT / FUZZY FILTER MATCHES ---
            filter_match: List[str] = []

            # bedType
            bedtype_score, matched_bedtypes = (1.0, [])
            if need_bed_type:
                bedtype_score, matched_bedtypes = _soft_match_any([str(need_bed_type)], bed_texts_norm, threshold=0.6)
                if matched_bedtypes:
                    filter_match.append(f"bedType:{matched_bedtypes[0]}")

            # bedsMin - Two-tier approach: actual beds first, then sofa beds as fallback
            beds_min_pass = True
            if isinstance(need_beds_min, int) and need_beds_min > 0:
                actual_bed_count = 0
                sofa_bed_count = 0
                total_bed_count = 0
                
                # Count beds from beds array, separating actual beds from sofa beds
                if isinstance(beds_raw, list):
                    for bed in beds_raw:
                        if isinstance(bed, dict) and isinstance(bed.get("count"), int):
                            bed_desc = str(bed.get("description", "")).lower()
                            bed_count = bed["count"]
                            total_bed_count += bed_count
                            
                            # Check if it's a sofa bed
                            if any(sofa_term in bed_desc for sofa_term in ["sofa", "pull-out", "pullout", "futon", "convertible"]):
                                sofa_bed_count += bed_count
                            else:
                                actual_bed_count += bed_count
                
                # If no beds found, try parsing from room name
                if total_bed_count == 0:
                    name_match = re.search(r'(?:^|\D)(1|one|two|2|three|3|four|4|five|5)(?:\D|$)', _norm(room_name), re.IGNORECASE)
                    if name_match:
                        num_str = name_match.group(1).lower()
                        if num_str in ['1', 'one']:
                            actual_bed_count = 1
                            total_bed_count = 1
                        elif num_str in ['2', 'two']:
                            actual_bed_count = 2
                            total_bed_count = 2
                        elif num_str in ['3', 'three']:
                            actual_bed_count = 3
                            total_bed_count = 3
                        elif num_str in ['4', 'four']:
                            actual_bed_count = 4
                            total_bed_count = 4
                        elif num_str in ['5', 'five']:
                            actual_bed_count = 5
                            total_bed_count = 5
                
                # Final fallback: parse description text
                if total_bed_count == 0:
                    for t in bed_texts:
                        m = re.search(r"(\d+)", t or "")
                        if m:
                            actual_bed_count += int(m.group(1))
                            total_bed_count += int(m.group(1))
                        else:
                            actual_bed_count += 1
                            total_bed_count += 1
                
                # Two-tier matching: actual beds first, then total beds as fallback
                if actual_bed_count >= need_beds_min:
                    beds_min_pass = True
                    filter_match.append(f"bedsMin:>= {need_beds_min} (actual beds)")
                elif total_bed_count >= need_beds_min:
                    beds_min_pass = True
                    filter_match.append(f"bedsMin:>= {need_beds_min} (including sofa beds)")
                else:
                    beds_min_pass = False

            # views
            views_score, matched_views = (1.0, [])
            if need_views:
                # If no views in the views array, check the room description
                views_to_search = views_norm
                if not views_to_search:
                    room_desc_text = room_desc or ""
                    # Common view words to look for in description
                    view_keywords = ['ocean', 'sea', 'city', 'garden', 'mountain', 'pool', 'lake', 'river', 'street', 'park', 'balcony']
                    found_views = []
                    desc_norm = _norm(room_desc_text)
                    for keyword in view_keywords:
                        if keyword in desc_norm:
                            found_views.append(keyword)
                    views_to_search = found_views
                
                views_score, matched_views = _soft_match_any([_norm(v) for v in need_views], views_to_search, threshold=0.6)
                if matched_views:
                    filter_match.extend([f"view:{v}" for v in matched_views])

            # breakfast
            if need_breakfast is True and has_breakfast:
                filter_match.append("breakfast")
            elif need_breakfast is False and not has_breakfast:
                filter_match.append("no_breakfast")

            # refundable
            refundable_pref = (params.get("filters") or {}).get("refundable")
            if refundable_pref is True and refundable is True:
                filter_match.append("refundable")
            elif refundable_pref is False and refundable is False:
                filter_match.append("non_refundable")

            percent_offer = None
            offers = rate.get("offers")
            if isinstance(offers, list) and offers:
                o0 = offers[0] or {}
                if "percentageDiscountOffer" in o0:
                    try:
                        percent_offer = float(o0["percentageDiscountOffer"])
                    except Exception:
                        percent_offer = None

            item = {
                "hotelId": hotel.get("id"),
                "rateId": rate_id,
                "name": room_name,
                "bedsRaw": beds_raw,             # for compact projection
                "views": views,                  # keep original-cased views if any
                "currency": currency,
                "cancellationText": cancellation_text,
                "refundable": refundable,
                "breakfast": has_breakfast,

                "priceAllIn": total_f,           # provider all-in or total
                "baseRate": base_f,
                "publishedRate": published_f,
                "taxesAny": taxes_any,
                "ourServiceFee": engine_fee_f,
                "ourTotalMarkup": engine_markup_f,
                "estAllInPrice": est_all_in,

                "percentageDiscountOffer": percent_offer,

                # soft-match scores/flags for ranking
                "bedTypeScore": bedtype_score if need_bed_type else 1.0,
                "bedsMinPassed": beds_min_pass if isinstance(need_beds_min, int) else True,
                "viewsScore": views_score if need_views else 1.0,
                "breakfastScore": 1.0 if (need_breakfast is True and has_breakfast) else 0.7 if need_breakfast is None else 0.5,
                "refundableScore": 1.0 if (refundable_pref is True and refundable is True) else 0.7 if refundable_pref is None else 0.5,

                "filterMatch": filter_match,     # <- list for LLM output
                "providerId": provider_id,
                "providerName": provider_name,

                "score": 0.0,
                "tieBreak": rate_key(
                    hotel_id=hotel.get("id"),
                    rate_id=rate_id,
                    name=room_name,
                    bed_config=bed_texts,
                    refundable=refundable,
                    provider_id=provider_id,
                ),
            }
            items.append(item)

    # cohort median from estAllIn
    cohort_median = _median([x for x in (i.get("estAllInPrice") or i.get("priceAllIn") for i in items) if isinstance(x, (int, float))])

    # rank
    top_heap: List[Tuple[float, str, Dict[str, Any]]] = []
    for it in items:
        # userFit: 35% bedType, 20% bedsMin, 20% views, 15% refundable, 10% breakfast
        bedtype_s = it.get("bedTypeScore", 1.0)
        bedsmin_s = 1.0 if it.get("bedsMinPassed", True) else 0.6
        views_s = it.get("viewsScore", 1.0)
        refundable_s = it.get("refundableScore", 0.7)
        breakfast_s = it.get("breakfastScore", 0.7)
        user_fit = 0.35 * bedtype_s + 0.20 * bedsmin_s + 0.20 * views_s + 0.15 * refundable_s + 0.10 * breakfast_s

        # value
        price_for_value = it.get("estAllInPrice") or it.get("priceAllIn")
        value = _value_score(price_for_value, cohort_median)

        # margin
        mar = _margin_proxy(
            it.get("priceAllIn"),
            it.get("publishedRate"),
            it.get("percentageDiscountOffer"),
            it.get("ourTotalMarkup"),
            it.get("ourServiceFee"),
        )

        sc = (
            ROOMS_WEIGHTS["userFit"] * user_fit
            + ROOMS_WEIGHTS["value"] * value
            + ROOMS_WEIGHTS["margin"] * mar
        )
        it["score"] = round(float(sc), 6)

        heapq.heappush(top_heap, (it["score"], it["tieBreak"], it))
        if len(top_heap) > max(top_k, 8):
            heapq.heappop(top_heap)

    # Deduplicate: keep only the best rate per room
    room_groups = {}
    for item in items:
        room_name = item.get("name", "")
        room_key = _norm(room_name)  # Normalize room name for grouping
        
        # If we haven't seen this room, or this rate has a better score, keep it
        if room_key not in room_groups or item["score"] > room_groups[room_key]["score"]:
            room_groups[room_key] = item
    
    # Convert back to list of deduplicated items
    items = list(room_groups.values())

    # cap & freeze
    if cap and len(items) > cap:
        items = heapq.nlargest(cap, items, key=lambda x: (x["score"], x["tieBreak"]))
    rooms_sorted = sorted(items, key=lambda x: (-x["score"], x["tieBreak"]))
    top_slice = sorted([x[2] for x in top_heap], key=lambda x: (-x["score"], x["tieBreak"]))[:max(1, top_k)]

    # compact projections
    vfs_rooms_compact = _project_compact_rooms(rooms_sorted)   # up to CAP
    top_slice_compact = _project_compact_rooms(top_slice)       # top 1

    meta = {
        "searchKey": search_key(params, {"ttlSec": (ttl or 600)}, source),
        "fetchedAt": int(time.time()),
        "ttlSec": int(ttl or 600),
        "version": VERSION,
        "weights": ROOMS_WEIGHTS,
        "params": params,
        "provenance": {"source": source, "token": token, "hotelId": hotel.get("id")},
        "status": status or "complete",
    }
    next_cursor = make_cursor(meta["searchKey"], pos=len(top_slice_compact), ver=VERSION)

    return {
        "room": (top_slice_compact[0] if top_slice_compact else None),
        "nextCursor": next_cursor,
        "vfsRooms": vfs_rooms_compact,
        "meta": meta,
    }