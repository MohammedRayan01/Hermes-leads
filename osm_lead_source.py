#!/usr/bin/env python3
"""
OpenStreetMap lead source — a second, independent discovery source that
runs alongside the Google Maps scraper. Free public API (Nominatim +
Overpass), no API key, no anti-bot/scraping risk: it's a structured JSON
API, not an HTML page to parse.

Why this exists: Google Maps' scroll-based feed is non-deterministic and
sometimes misses businesses. Merging in OSM's results (a) surfaces extra
candidates Maps didn't show, and (b) lets "no website" be cross-validated
against a second source instead of trusted on Maps data alone.

Output schema matches the `biz` dicts produced by parse_feed_text() in
gmaps_lead_scraper.py, so callers can merge OSM results straight into the
same candidate pipeline (activity check → enrichment → scoring) with no
special-casing beyond checking biz["source"].
"""

import re
import time
import urllib.parse
import urllib.request
import json

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Hermes-Lead-Finder/1.0 (contact: local-lead-gen-tool)"

# ── KEYWORD → OSM TAG MAPPING ──────────────────────────────────────
# OSM classifies businesses by structured tags (amenity=dentist,
# shop=hairdresser, ...), not free-text category strings like Maps. This
# table covers common niches; unmapped keywords fall back to a name-based
# search (still useful, just less precise about category).
KEYWORD_OSM_TAGS = {
    "dentist": [("amenity", "dentist")],
    "dentists": [("amenity", "dentist")],
    "dental clinic": [("amenity", "dentist")],
    "doctor": [("amenity", "doctors")],
    "clinic": [("amenity", "clinic"), ("amenity", "doctors")],
    "hospital": [("amenity", "hospital")],
    "pharmacy": [("amenity", "pharmacy")],
    "hair salon": [("shop", "hairdresser")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "spa": [("leisure", "spa"), ("shop", "beauty")],
    "gym": [("leisure", "fitness_centre")],
    "fitness center": [("leisure", "fitness_centre")],
    "restaurant": [("amenity", "restaurant")],
    "restaurants": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "coffee shop": [("amenity", "cafe")],
    "bakery": [("shop", "bakery")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "hotels": [("tourism", "hotel"), ("tourism", "guest_house")],
    "resort": [("tourism", "hotel"), ("tourism", "resort"), ("tourism", "guest_house")],
    "resorts": [("tourism", "hotel"), ("tourism", "resort"), ("tourism", "guest_house")],
    "homestay": [("tourism", "guest_house")],
    "real estate": [("office", "estate_agent")],
    "real estate agent": [("office", "estate_agent")],
    "law firm": [("office", "lawyer")],
    "lawyer": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
    "car repair": [("shop", "car_repair")],
    "auto repair": [("shop", "car_repair")],
    "car dealer": [("shop", "car")],
    "supermarket": [("shop", "supermarket")],
    "grocery store": [("shop", "supermarket"), ("shop", "convenience")],
    "electronics store": [("shop", "electronics")],
    "furniture store": [("shop", "furniture")],
    "clothing store": [("shop", "clothes")],
    "boutique": [("shop", "boutique"), ("shop", "clothes")],
    "jewelry store": [("shop", "jewelry")],
    "bank": [("amenity", "bank")],
    "school": [("amenity", "school")],
    "veterinary": [("amenity", "veterinary")],
    "vet": [("amenity", "veterinary")],
    "photographer": [("shop", "photo"), ("craft", "photographer")],
    "photography studio": [("shop", "photo"), ("craft", "photographer")],
}


def _osm_tags_for_keyword(keyword: str) -> list:
    """Look up the niche keyword (case-insensitive, loose match) in the
    tag table. Falls back to [] (caller does a name-text search instead)
    if the niche isn't mapped."""
    kw = keyword.strip().lower()
    if kw in KEYWORD_OSM_TAGS:
        return KEYWORD_OSM_TAGS[kw]
    # Loose containment match, e.g. "Hair Salons in Indiranagar" -> "salon"
    for key, tags in KEYWORD_OSM_TAGS.items():
        if key in kw or kw in key:
            return tags
    return []


_GEOCODE_CACHE = {}


def geocode_area(location: str, timeout: int = 10) -> dict:
    """Resolve a free-text location (e.g. "Kalpetta, Wayanad India") via
    Nominatim. Returns {"bbox": (south, north, west, east), "country_code":
    "gb"} or None on failure — caller should skip OSM enrichment for this
    area rather than fail the whole run over a geocoding miss. Cached per
    location string since both OSM discovery and phone-region detection
    (see guess_region_code) need this same lookup within one scrape_area
    call — no reason to hit Nominatim twice for the same area."""
    if location in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[location]

    params = urllib.parse.urlencode({
        "q": location, "format": "json", "limit": 1, "addressdetails": 1,
    })
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}", headers={"User-Agent": USER_AGENT}
    )
    result = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data:
            bbox = data[0].get("boundingbox")
            if bbox and len(bbox) == 4:
                result = {
                    "bbox": tuple(float(x) for x in bbox),
                    "country_code": (data[0].get("address", {}) or {}).get("country_code", ""),
                }
    except Exception as e:
        print(f"     ⚠ OSM geocode failed for '{location}': {e}")

    _GEOCODE_CACHE[location] = result
    return result


def guess_region_code(location: str, default: str = "IN") -> str:
    """Best-effort 2-letter ISO region code for `location`, used as a
    parsing hint for locally-formatted (no country-code prefix) phone
    numbers. Falls back to `default` if geocoding fails or returns no
    country — this pipeline's original scope was India, so that stays the
    fallback rather than an arbitrary guess."""
    geo = geocode_area(location)
    if geo and geo.get("country_code"):
        return geo["country_code"].upper()
    return default


def _biz_from_osm_tags(tags: dict, category_label: str) -> dict:
    """Build a biz dict in the same shape parse_feed_text() produces."""
    name = tags.get("name", "").strip()
    phone = (tags.get("contact:phone") or tags.get("phone") or "").strip()
    website = (tags.get("contact:website") or tags.get("website") or "").strip()

    addr_parts = [
        tags.get("addr:housenumber", ""), tags.get("addr:street", ""),
        tags.get("addr:suburb", ""), tags.get("addr:city", ""),
    ]
    address = " ".join(p for p in addr_parts if p).strip()

    biz = {
        "name": name, "place_id": "", "phone": phone, "address": address,
        "rating": 0.0, "reviews": 0, "has_website": False, "website_url": "",
        "has_phone_icon": bool(phone),
        "social_or_directory_link": "", "social_or_directory_class": "",
        "category": category_label, "source": "OpenStreetMap",
    }

    if website:
        # classify_url is imported lazily by the caller to avoid a circular
        # import; caller sets has_website/website_url or
        # social_or_directory_* based on classification before merging.
        biz["_raw_website"] = website

    return biz


def fetch_osm_listings(location: str, keyword: str, timeout: int = 25) -> list:
    """Query Overpass for businesses matching `keyword` inside the
    bounding box for `location`. Returns a list of biz dicts (see
    _biz_from_osm_tags), or [] on any failure — this is a supplementary
    source, so a failure here should never block the primary Maps run."""
    geo = geocode_area(location)
    if not geo:
        print(f"     ⚠ OSM: could not geocode '{location}', skipping OSM source for this area")
        return []
    south, north, west, east = geo["bbox"]

    tags = _osm_tags_for_keyword(keyword)
    if tags:
        clauses = "".join(
            f'node["{k}"="{v}"]({south},{west},{north},{east});'
            f'way["{k}"="{v}"]({south},{west},{north},{east});'
            for k, v in tags
        )
    else:
        # Unmapped niche — fall back to a case-insensitive name search
        # within the area. Less precise (matches on name text, not
        # category), but still a useful supplementary net.
        safe_kw = re.sub(r'["\\]', "", keyword)
        clauses = (
            f'node["name"~"{safe_kw}",i]({south},{west},{north},{east});'
            f'way["name"~"{safe_kw}",i]({south},{west},{north},{east});'
        )

    query = f'[out:json][timeout:{timeout - 5}];({clauses});out center tags 200;'

    # The public Overpass instance queues/rejects (504 "too busy") under
    # request bursts — common, not a real outage. One short-backoff retry
    # clears most of these; if both attempts fail, this is a supplementary
    # source, so log and move on rather than blocking the whole run.
    result = None
    last_err = None
    for attempt in range(2):
        try:
            data = urllib.parse.urlencode({"data": query}).encode("utf-8")
            req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(5)
    if result is None:
        print(f"     ⚠ OSM Overpass query failed for '{keyword}' in '{location}' (2 attempts): {last_err}")
        return []

    category_label = tags[0][1].replace("_", " ") if tags else keyword
    listings = []
    for el in result.get("elements", []):
        el_tags = el.get("tags", {})
        if not el_tags.get("name"):
            continue
        listings.append(_biz_from_osm_tags(el_tags, category_label))

    return listings


def _phone_digits(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else digits


def dedupe_against(osm_listings: list, existing: list) -> list:
    """Drop OSM listings that are very likely the same business as one
    already discovered via Maps (matched by phone, or by a strong name
    match), so scrape_area() only gains genuinely NEW candidates from OSM."""
    existing_phones = {_phone_digits(b.get("phone", "")) for b in existing if b.get("phone")}
    existing_names = {b["name"].strip().lower() for b in existing if b.get("name")}

    new_listings = []
    for biz in osm_listings:
        phone_key = _phone_digits(biz.get("phone", ""))
        if phone_key and phone_key in existing_phones:
            continue
        name_key = biz["name"].strip().lower()
        if name_key in existing_names:
            continue
        # Loose containment match catches near-duplicates like "Cafe Coffee
        # Day" vs "Cafe Coffee Day - MG Road"
        if any(name_key[:15] in n or n[:15] in name_key for n in existing_names if len(n) > 3):
            continue
        new_listings.append(biz)
    return new_listings
