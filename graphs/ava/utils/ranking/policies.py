# Version & tiny policy knobs in one place (easy to bump later)
VERSION = "norm.v1"

# Default weights (frozen per artifact)
# You can override at runtime via policy={"weights": {...}}
# -------- Hotels --------
HOTELS_WEIGHTS = {
    "userFit": 0.45,   # amenities + distance (distance neutral if unknown) (Does it match what they want?)
    "value":   0.25,   # price position vs median (Is the price fair vs others?)
    "margin":  0.20,   # proxy from publishedRate/discount or pricing engine (Do we make money on it?)
    "quality": 0.10,   # stars + review score + small review-count bonus (Is it a nice hotel?)
}

# -------- Rooms --------
ROOMS_WEIGHTS = {
    "userFit": 0.50,   # beds/bedType/views/breakfast/refundable (soft/fuzzy)
    "value":   0.25,   # estAllIn vs cohort median
    "margin":  0.25,   # pricing engine margin proxy
}

# TTLs used in rankers' meta (seconds)
DEFAULT_TTLS = {
    # hotels
    "geo_hotel_search":  900,
    "hotel_search":       600,

    # rooms (add these)
    "rooms_and_rates":    600,
    "direct_rooms_and_rates": 600,
}

# Safety caps to keep memory bounded if providers return huge lists
CAPS = {
    "hotels": 20,  # keep top N before final freeze sort
    "rooms": 10,   # keep top N before final freeze sort
}

# Margin clip band (used to normalize margin proxies into [0..1])
MARGIN_CLIP = (0.0, 0.40)  # interpret <=40% apparent discount as 1.0