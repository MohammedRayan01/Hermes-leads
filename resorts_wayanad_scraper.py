#!/usr/bin/env python3
"""
Google Maps Lead Scraper — Browser-based (Playwright) v3
Strategy: Sidebar feed text parse + place page enrichment
Niche: Resorts | Location: Wayanad, India
Target: Exactly 10 verified active businesses WITHOUT websites.
"""

import asyncio
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from ddgs import DDGS
import phonenumbers

from osm_lead_source import fetch_osm_listings, dedupe_against, guess_region_code


def _extract_phone(text: str, region: str = "IN") -> str:
    """Find the first valid phone number in `text` using Google's
    libphonenumber (the `phonenumbers` package) instead of a hand-rolled,
    country-specific regex. This is what makes phone extraction actually
    work outside India: a number written in international format
    ("+44 20 7490 1483") parses correctly regardless of `region`; a number
    written in local format (no country code, e.g. "020 7490 1483") needs
    `region` as a hint to know how to interpret the leading digits. Returns
    "" if no valid number is found — never raises, callers already treat a
    missing phone as "skip this lead", not a fatal error."""
    try:
        for match in phonenumbers.PhoneNumberMatcher(text, region):
            return phonenumbers.format_number(
                match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
    except Exception:
        pass
    return ""

# ── CONFIG ──────────────────────────────────────────────────
KEYWORD = "Resorts"
LOCATION = "Wayanad India"
SEARCH_QUERY = f"{KEYWORD} {LOCATION}"
DISCOVERY_CAP = 100  # Raised for smaller market
TARGET_LEADS = 10
MIN_RATING = 3.0
MIN_REVIEWS = 0  # Lowered for smaller market - many new resorts have low review counts

# ── URL CLASSIFICATION ──────────────────────────────────────────
# A link in a Google Business Profile's "website" field (or found via web
# search) is not necessarily a REAL website — owners commonly paste an
# Instagram/Facebook link instead, or it's a directory/OTA listing page
# nothing to do with the business's own site. classify_url() sorts any URL
# into a category; only "own_domain" counts as a real website for outreach.
SOCIAL_MEDIA_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "pinterest.com", "tiktok.com", "linkedin.com",
    "threads.net", "snapchat.com", "whatsapp.com", "wa.me",
    "telegram.me", "t.me",
}

LINK_IN_BIO_DOMAINS = {
    "linktr.ee", "bio.link", "linkin.bio", "beacons.ai", "campsite.bio",
    "carrd.co", "milkshake.app", "lnk.bio", "solo.to", "flowcode.com",
}

DIRECTORY_OTA_DOMAINS = {
    "booking.com", "agoda.com", "makemytrip.com", "goibibo.com",
    "tripadvisor.com", "tripadvisor.in", "trivago.com", "trivago.in",
    "expedia.com", "cleartrip.com", "yatra.com", "oyorooms.com",
    "justdial.com", "quickerala.com", "sulekha.com", "indiamart.com",
    "airbnb.com", "holidify.com", "zomy.in", "trip.com", "in.trip.com",
    "yelp.com", "google.com", "ixigo.com", "hotels.com",
    "freelistingindia.in",
}

# Union, kept for the web-search exclusion check in _search_once.
BLOCKED_DOMAINS = SOCIAL_MEDIA_DOMAINS | LINK_IN_BIO_DOMAINS | DIRECTORY_OTA_DOMAINS


def classify_url(url: str) -> str:
    """Classify a URL as 'own_domain' (a real, independent business
    website), 'social_media', 'link_in_bio', or 'directory_or_aggregator'.
    Only 'own_domain' should ever count as "this business has a website" —
    a Facebook/Instagram link pasted into the website field is not a
    substitute for owning a real site."""
    if not url:
        return "unknown"
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return "unknown"
    netloc = netloc[4:] if netloc.startswith("www.") else netloc
    if netloc in SOCIAL_MEDIA_DOMAINS:
        return "social_media"
    if netloc in LINK_IN_BIO_DOMAINS:
        return "link_in_bio"
    if netloc in DIRECTORY_OTA_DOMAINS:
        return "directory_or_aggregator"
    return "own_domain"


def score_lead(biz: dict) -> tuple:
    """Score a no-website lead's purchase intent for a website-sales pitch,
    0-100, using signals already captured per lead (no extra scraping).
    Returns (score, tier) where tier is 'Hot' (70+), 'Warm' (40-69), or
    'Cold' (<40). Higher = more likely to convert.

    Weights: review count 40 (established businesses can afford + benefit
    from a site), existing social-media-only presence 25 (strongest intent
    signal — they've already invested effort online and hit a ceiling with
    a free tool), rating 20 (reputable = safer/easier pitch), profile
    claimed status 15 (claimed = more engaged owner, warmer lead)."""
    score = 0

    reviews = biz.get("reviews", 0) or 0
    if reviews > 100:
        score += 40
    elif reviews > 20:
        score += 30
    elif reviews >= 5:
        score += 15
    else:
        score += 5

    social_class = biz.get("social_or_directory_class", "")
    if social_class == "social_media":
        score += 25
    elif social_class == "link_in_bio":
        score += 20
    elif social_class == "directory_or_aggregator":
        score += 10
    else:
        score += 5

    rating = biz.get("rating", 0) or 0
    if rating >= 4.5:
        score += 20
    elif rating >= 4.0:
        score += 15
    elif rating >= 3.5:
        score += 10
    else:
        score += 5

    claimed = biz.get("profile_claimed", "Unknown")
    if claimed == "Yes":
        score += 15
    elif claimed == "No":
        score += 3
    else:
        score += 8

    if score >= 70:
        tier = "Hot"
    elif score >= 40:
        tier = "Warm"
    else:
        tier = "Cold"

    return score, tier


# Truly niche-agnostic connector/filler words, plus a handful of common
# hospitality terms kept as a helpful default (harmless no-op for other
# niches). The niche-specific part (resort/dentist/salon/...) is derived
# dynamically from the search KEYWORD at call time via
# _keyword_generic_words(), so this doesn't need hand-maintaining per niche.
_BASE_GENERIC_WORDS = {
    "the", "by", "and", "in", "at", "of", "for", "wayanad",
    "resort", "resorts", "hotel", "homestay", "villa",
    "farm", "lodge", "inn", "wild", "holiday",
    "cottage", "nest", "stay", "camp", "tent", "estate",
    # Common business-type suffix words that recur across many verticals
    # (medical, retail, services, ...). This is a safety net for when a
    # business's category couldn't be captured (e.g. Maps hadn't finished
    # rendering it on the scroll pass that first saw the business name) —
    # the keyword/category-derived exclusion below is the primary source
    # of niche words, this just covers the gap when that's unavailable.
    "clinic", "clinics", "center", "centre", "care", "hospital",
    "studio", "services", "shop", "store", "spa", "salon",
}


def _keyword_generic_words(keyword: str) -> set:
    """Derive niche words to exclude from token comparison out of the
    search KEYWORD itself (e.g. "Dentists" -> {"dentist", "dentists"}),
    so the domain-matching heuristic generalizes to any niche without a
    hardcoded per-vertical word list. Unicode-aware (\\w, not [a-z]) so a
    niche keyword given in a non-Latin script works the same way."""
    words = re.findall(r"\w+", keyword.lower())
    extra = set(words)
    for w in words:
        # Naive English pluralization is a no-op (harmless) for non-Latin
        # words — CJK/Arabic/etc. don't inflect this way, this just adds
        # an extra generic-word entry that will never match anything.
        if w.endswith("s") and len(w) > 3:
            extra.add(w[:-1])  # naive singular
        else:
            extra.add(w + "s")  # naive plural
    return extra


def _name_tokens(name: str, extra_generic: set = frozenset()) -> set:
    """Tokenize a business name into comparable words. Unicode-aware (\\w
    matches CJK/Japanese/Korean/Arabic/etc. scripts, not just a-z0-9) —
    previously a name written in any non-Latin script tokenized to nothing
    here, which silently disabled web-search verification for it entirely
    (see the "no comparable tokens in name" bail in
    web_search_verify_website)."""
    words = re.findall(r"\w+", name.lower())
    generic = _BASE_GENERIC_WORDS | extra_generic
    tokens = set()
    for w in words:
        if w in generic:
            continue
        # CJK and other dense scripts pack far more meaning per character
        # than Latin letters — a 2-character Chinese/Japanese word is
        # often a complete, distinctive word. The length filter below
        # exists to drop short/generic LATIN filler ("of", "at", ...), not
        # to discard legitimately meaningful short non-Latin tokens.
        min_len = 1 if re.search(r"[^\x00-\x7F]", w) else 3
        if len(w) >= min_len:
            tokens.add(w)
    return tokens


def _title_corroborates(business_name: str, title: str) -> bool:
    """For weak/short names (few distinctive tokens after generic-word
    filtering), a single shared word matching a domain isn't enough evidence
    — e.g. "My Garden Homestay" matching some unrelated "...garden...com".
    Require the result's own title to substantially contain the FULL
    original name (including short/generic words) as extra corroboration.
    Unicode-aware for the same reason as _name_tokens()."""
    name_words = [w for w in re.findall(r"\w+", business_name.lower()) if len(w) > 1]
    if not name_words:
        return False
    title_norm = title.lower()
    hits = sum(1 for w in name_words if w in title_norm)
    return hits / len(name_words) >= 0.7


def _search_once(business_name: str, location: str, target_tokens: set):
    """One search + scan pass. Returns (found, url, note) or None on error."""
    query = f"{business_name} {location}"
    try:
        results = list(DDGS().text(query, max_results=15))
    except Exception as e:
        return None, "", f"search failed: {e}"

    # Domain names are almost always ASCII/punycode (romanized/transliterated)
    # even for a business whose real name is written in Chinese, Japanese,
    # Korean, Arabic, etc. — so "is a name token a substring of the ASCII
    # domain root" (below) can never succeed for such a name, structurally,
    # no matter how confident a real match would be. For these names, match
    # the original-script name directly against each result's TITLE instead
    # — search result titles commonly do carry a business's native-script
    # name even when its own domain is romanized.
    name_has_no_ascii_letters = not re.search(r"[a-z0-9]", business_name.lower())

    for r in results:
        href = r.get("href", "")
        if not href:
            continue
        try:
            netloc = urlparse(href).netloc.lower()
        except Exception:
            continue
        netloc = netloc[4:] if netloc.startswith("www.") else netloc
        if not netloc or netloc in BLOCKED_DOMAINS:
            continue

        if name_has_no_ascii_letters:
            if _title_corroborates(business_name, r.get("title", "")):
                return True, href, "native-script name matched result title (domain is romanized, not directly comparable)"
            continue

        # Domain names concatenate words with no delimiter (e.g.
        # "blackforestwayanad.com"), so compare via substring containment
        # against the raw domain root, not token-set equality.
        domain_root_raw = re.sub(r"[^a-z0-9]", "", netloc.split(".")[0].lower())

        # Require the domain ROOT (not a path on some other company's
        # domain, e.g. voyehomes.com/maryland-...) to resemble the business
        # name — this is what distinguishes an owned site from a listing
        # on a hospitality-management company's domain.
        matched = {t for t in target_tokens if t in domain_root_raw}
        # Names with only 1-2 distinctive tokens need a FULL match — a single
        # shared word (e.g. "jungle", "green", "mountain" — common regional
        # nature-theme words) is not enough evidence and causes false
        # positives against unrelated resorts. Longer names can pass on a
        # strong partial match (2+ tokens) since more distinctive words agree.
        is_confident = matched == target_tokens or len(matched) >= 2
        if matched and is_confident:
            # Weak signal (only 1 distinctive token, e.g. a common word like
            # "garden") needs the title to corroborate the full name too.
            if len(target_tokens) < 2 and not _title_corroborates(business_name, r.get("title", "")):
                continue
            return True, href, f"domain '{netloc}' contains name tokens {matched}"

    return False, "", "no matching own-domain result in top results"


def web_search_verify_website(business_name: str, location: str = "Wayanad",
                               keyword: str = "", category: str = "", attempts: int = 2):
    """Secondary check: does this business have a website anywhere on the
    web (even if it's not linked on its Google Business Profile)? DDG result
    sets aren't fully deterministic between calls, and a missed real website
    is worse for outreach than an extra check — so this runs the search
    multiple times and treats ANY confident match as authoritative; only
    concludes "no website" if every attempt comes back clean.
    Returns (found: bool, url: str, note: str)."""
    extra_generic = _keyword_generic_words(keyword) if keyword else set()
    if category:
        # The MAPS-REPORTED category (e.g. "Dental clinic") often reveals
        # the niche's actual common words better than the user's search
        # phrase does — e.g. searching "Dentists" doesn't tell you "dental"
        # and "clinic" are near-universal terms, but the category does.
        # Only use the category word(s), not any address text combined
        # into the same field for some Maps card layouts.
        extra_generic |= _keyword_generic_words(category.split('\xb7')[0])
    target_tokens = _name_tokens(business_name, extra_generic)
    if not target_tokens:
        return False, "", "no comparable tokens in name"

    last_note = "no matching own-domain result in top results"
    for attempt in range(attempts):
        found, url, note = _search_once(business_name, location, target_tokens)
        if found is True:
            return True, url, note
        if found is None:
            # search itself errored — don't let a transient failure count
            # as a clean pass; retry, and only report the error if we never
            # get a working attempt at all.
            last_note = note
            continue
        last_note = note
        if attempt < attempts - 1:
            time.sleep(2)

    return False, "", f"{last_note} (checked {attempts}x)"

# ── HELPERS ────────────────────────────────────────────────
def parse_feed_text(feed_text, cards_info, region="IN"):
    """Parse sidebar feed text to extract business data. `region` (2-letter
    ISO code, e.g. "GB") is a phone-parsing hint — see _extract_phone()."""
    listings = []
    lines = [l.strip() for l in feed_text.split('\n') if l.strip()]
    
    skip_patterns = [
        r'^Results$', r'^Share$', r'^\uf022$', r'^\uf0ea$', r'^\uf05a$',
        r'^Book online$', r'^On-site services$', r'^Sponsored$',
        r"You're seeing a limited view", r'Get the most out',
        r'^Sign in$', r'^\uf0e8$', r'^\uf0d1\s+\uf0e8',
    ]
    
    i = 0
    current_biz = None
    rating_reviews_buffer = None
    
    while i < len(lines):
        line = lines[i]
        
        should_skip = any(re.search(pat, line) for pat in skip_patterns)
        if should_skip:
            i += 1
            continue
        
        # Rating line: "4.8" or "4.9(980)"
        rating_only = re.match(r'^(\d+\.?\d*)$', line)
        rating_with_reviews = re.match(r'^(\d+\.?\d*)\((\d[\d,]*)\)$', line)
        
        if rating_only or rating_with_reviews:
            if rating_with_reviews:
                rating_reviews_buffer = (
                    float(rating_with_reviews.group(1)),
                    int(rating_with_reviews.group(2).replace(",", ""))
                )
            else:
                rating_reviews_buffer = (float(rating_only.group(1)), 0)
            i += 1
            continue

        # Standalone review count line: "(128)" rendered on its own line,
        # separate from the rating line above it (seen on hotel/resort cards)
        reviews_only = re.match(r'^\((\d[\d,]*)\)$', line)
        if reviews_only and rating_reviews_buffer:
            rating_reviews_buffer = (
                rating_reviews_buffer[0],
                int(reviews_only.group(1).replace(",", ""))
            )
            i += 1
            continue

        # Detail line: category, sometimes combined with "· address · hours".
        # Structural detection instead of a hardcoded category-word
        # whitelist: the first substantive line captured for a business
        # (right after its name/rating) IS the category/detail line,
        # whatever word(s) it contains -- this generalizes to any niche
        # (resorts, dentists, salons, ...) with no per-vertical word list.
        # Guard against swallowing the NEXT business's name-duplicate line.
        is_next_name_duplicate = (
            i + 1 < len(lines) and line == lines[i + 1] and len(line) > 3
        )

        if current_biz and "category" not in current_biz and not is_next_name_duplicate:
            current_biz["category"] = line
            parts = [p.strip() for p in line.split('\xb7')]

            address_parts = []
            has_phone = False

            # parts[0] is the category text itself, not address -- only
            # look at what follows a bullet separator (the original
            # combined-line format some Maps card types still use).
            for part in parts[1:]:
                # Phone icon variants (from Google Maps PUA characters)
                if part in ['\ue924', '\ue934', '\uf095', '\uf54a', '\uf0e8']:
                    has_phone = True
                elif re.match(r'^(Closed|Open|Opens|Open 24)', part):
                    continue
                elif part:
                    address_parts.append(part)

            if address_parts:
                current_biz["address"] = " \xb7 ".join(address_parts)

            if has_phone:
                current_biz["has_phone_icon"] = True
                found_phone = _extract_phone(line, region)
                if found_phone:
                    current_biz["phone"] = found_phone

            if rating_reviews_buffer:
                current_biz["rating"] = rating_reviews_buffer[0]
                current_biz["reviews"] = rating_reviews_buffer[1]
                rating_reviews_buffer = None

            i += 1
            continue
        
        # Website URL line — either a full URL ("https://example.com") or a
        # bare domain with no protocol ("coffeegreensresort.com"), which is
        # how Google Maps commonly renders hotel/resort website fields.
        web_match = re.match(r'^(https?://[^\s]+)', line)
        bare_domain_match = re.match(
            r'^(?:www\.)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/\S*)?$', line
        )
        if (web_match or bare_domain_match) and current_biz and '@' not in line:
            found_url = web_match.group(1) if web_match else line
            url_class = classify_url(found_url)
            if url_class == "own_domain":
                current_biz["has_website"] = True
                current_biz["website_url"] = found_url
            else:
                # A social/directory link is NOT a real website — record it
                # for context but don't treat it as one. Leave has_website
                # False so this business still goes through full candidate
                # evaluation instead of being wrongly excluded here.
                current_biz["social_or_directory_link"] = found_url
                current_biz["social_or_directory_class"] = url_class
            i += 1
            continue
        
        # Business name (two identical lines)
        if i + 1 < len(lines) and line == lines[i + 1] and len(line) > 3:
            name = line
            current_biz = {
                "name": name, "place_id": "", "phone": "", "address": "",
                "rating": 0.0, "reviews": 0, "has_website": False,
                "website_url": "", "has_phone_icon": False,
                "social_or_directory_link": "", "social_or_directory_class": "",
                "source": "Google Maps",
            }
            listings.append(current_biz)
            i += 2
            continue
        
        # Standalone address/phone line
        looks_like_garbage = re.match(r'^[\d\s\.·\-]+$', line) or re.search(r'[\ue000-\uf8ff]', line)
        if len(line) > 3 and not looks_like_garbage:
            if current_biz:
                found_phone = _extract_phone(line, region)
                if found_phone and not current_biz["phone"]:
                    current_biz["phone"] = found_phone
                elif re.search(r'(?:Road|Street|Nagar|Layout|Main|Cross|Signal|near|opposite|above|Floor|Wayanad)', line, re.IGNORECASE):
                    if not current_biz["address"]:
                        current_biz["address"] = line
        
        i += 1
    
    # Cross-reference with cards
    for biz in listings:
        for card in cards_info:
            if (biz["name"].lower()[:15] in card["name"].lower() or 
                card["name"].lower()[:15] in biz["name"].lower()):
                biz["place_id"] = card["place_id"]
                if card.get("phone"):
                    biz["phone"] = biz["phone"] or card["phone"]
                break
    
    return listings


def extract_place_id_from_href(href):
    if not href:
        return "", ""
    pid_match = re.search(r'!1s(0x[0-9a-f]+:[0-9a-f]+)', href)
    if pid_match:
        return pid_match.group(1), href
    return "", href


async def enrich_business(page, biz, cards_info, region="IN"):
    """Visit place page: extract phone, owner, claim status. `region`
    (2-letter ISO code) is a phone-parsing hint — see _extract_phone()."""
    biz.setdefault("owner_name", "")
    biz.setdefault("profile_claimed", "Unknown")
    biz.setdefault("maps_url", "")
    biz.setdefault("social_or_directory_link", "")
    biz.setdefault("social_or_directory_class", "")
    
    card = next((c for c in cards_info 
                if c["name"] == biz["name"] or 
                biz["name"][:15].lower() in c["name"].lower()), None)
    
    place_url = None
    if card and card["href"]:
        place_url = card["href"]
    elif biz["place_id"]:
        place_url = f"https://www.google.com/maps/place/?q=place_id:{biz['place_id']}"
    
    if not place_url:
        return

    biz["maps_url"] = place_url

    try:
        await page.goto(place_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2)
        page_text = await page.inner_text("body")
        
        # ── Phone (libphonenumber-based — works for any country's
        # format/grouping, not just Indian numbers) ─────
        if not biz["phone"]:
            found_phone = _extract_phone(page_text, region)
            if found_phone:
                biz["phone"] = found_phone
        
        # ── Website (authoritative — feed text often omits it entirely
        # for hotel/resort cards) ─────────────────────
        website_link = await page.query_selector('a[data-item-id="authority"]')
        if website_link:
            href = await website_link.get_attribute("href")
            if href:
                url_class = classify_url(href)
                if url_class == "own_domain":
                    biz["has_website"] = True
                    biz["website_url"] = href
                else:
                    # Owner pasted an Instagram/Facebook/directory link into
                    # the website field — not a real website. Record it but
                    # don't count it as one.
                    biz["social_or_directory_link"] = href
                    biz["social_or_directory_class"] = url_class

        # ── Review count (authoritative — hotel/resort feed cards don't
        # show a review count at all, only the place page does) ───
        review_match = re.search(r'([\d,]+)\s+[Rr]eviews?\b', page_text)
        if review_match:
            biz["reviews"] = int(review_match.group(1).replace(",", ""))

        # ── Claim status ─────────────────────────────
        claim_btn = await page.query_selector(
            '[aria-label*="Claim this business"], '
            'button:has-text("Claim this business")'
        )
        if claim_btn:
            biz["profile_claimed"] = "No"
        elif re.search(r'Claim this business|Own this business\?', page_text, re.I):
            biz["profile_claimed"] = "No"
        elif re.search(r'You manage this|Business Profile', page_text, re.I):
            biz["profile_claimed"] = "Yes"
        
        # ── Owner name ────────────────────────────
        owner = re.search(
            r'(?:Manager|Owner|Proprietor)[\s:]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
            page_text
        )
        if owner:
            biz["owner_name"] = owner.group(1).strip()
        
        print(f"     📞 {biz['phone'] or '—'} | Owner: {biz['owner_name'] or '—'} | Claimed: {biz['profile_claimed']}")
        
    except Exception as e:
        print(f"     ⚠ {e}")


# ── MAIN PIPELINE ──────────────────────────────────────────
async def scrape_area(location: str, keyword: str = KEYWORD,
                       target_leads: int = TARGET_LEADS,
                       discovery_cap: int = DISCOVERY_CAP) -> list:
    """Run the full discovery -> verify -> enrich pipeline for one area.
    Returns the list of confirmed (no-website, phone-verified) lead dicts.
    Does NOT write a CSV — callers (single-area __main__ or a multi-area
    orchestrator) own persistence, so this is safe to call repeatedly."""
    search_query = f"{keyword} {location}"
    # Phone-parsing region hint — reuses the same Nominatim lookup OSM
    # augmentation makes for this area (cached in osm_lead_source), so this
    # costs nothing extra. Falls back to "IN" (this pipeline's original
    # scope) if geocoding fails; a wrong hint only affects LOCAL-format
    # numbers (no country code) — internationally-formatted numbers
    # ("+44 ...") parse correctly regardless.
    region = guess_region_code(location)
    print(f"\n{'#'*60}")
    print(f"#  GOOGLE MAPS LEAD SCRAPER v3 (BROWSER)")
    print(f"#  Niche: {keyword}  |  Location: {location}  |  Region hint: {region}")
    print(f"#  Target: {target_leads} leads (no website, active)")
    print(f"{'#'*60}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-IN",
        )
        page = await context.new_page()

        # ── STEP 1: DISCOVERY ─────────────────────────────
        search_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        
        try:
            await page.wait_for_selector('[role="feed"]', timeout=30000)
        except Exception:
            print("⚠ Feed not found, trying anyway...")
        
        await asyncio.sleep(3)
        
        print(f"{'='*60}")
        print(f"STEP 1: DISCOVERY — Browser-based Google Maps search")
        print(f"Search: {search_query}")
        print(f"Cap: {discovery_cap} listings")
        print(f"{'='*60}\n")
        
        listings = []
        seen_names = set()
        cards_info = []
        scroll_attempts = 0
        max_scrolls = 30  # Increased for potentially smaller market
        
        while len(listings) < discovery_cap and scroll_attempts < max_scrolls:
            scroll_attempts += 1
            
            # Collect card links
            cards = await page.query_selector_all('a.hfpxzc')
            for card in cards:
                aria = await card.get_attribute("aria-label")
                href = await card.get_attribute("href")
                if aria and len(aria) > 3:
                    pid, _ = extract_place_id_from_href(href)
                    cards_info.append({
                        "name": aria.strip(),
                        "place_id": pid,
                        "href": href,
                    })
            
            # Parse sidebar feed
            feed = await page.query_selector('[role="feed"]')
            if feed:
                feed_text = await feed.inner_text()
                parsed = parse_feed_text(feed_text, cards_info, region)
                for biz in parsed:
                    if biz["name"] not in seen_names:
                        seen_names.add(biz["name"])
                        listings.append(biz)
            
            print(f"  [{scroll_attempts}] {len(listings)}/{discovery_cap} listings")
            
            if len(listings) >= discovery_cap:
                break
            
            try:
                await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
            except Exception:
                pass
            await asyncio.sleep(1.5)
        
        print(f"\n  ✓ Discovery: {len(listings)} raw listings\n")

        # ── STEP 1B: OSM AUGMENT ──────────────────────────
        # Second, independent discovery source (free Overpass API — no
        # scraping/anti-bot risk). Adds businesses Maps' scroll-based feed
        # missed. Failures here (geocoding miss, Overpass timeout) are
        # non-fatal — this is a supplementary net, not the primary source.
        print(f"{'='*60}")
        print(f"STEP 1B: OSM AUGMENT — cross-checking OpenStreetMap")
        print(f"{'='*60}\n")
        try:
            osm_raw = fetch_osm_listings(location, keyword)
            for biz in osm_raw:
                raw_website = biz.pop("_raw_website", "")
                if raw_website:
                    url_class = classify_url(raw_website)
                    if url_class == "own_domain":
                        biz["has_website"] = True
                        biz["website_url"] = raw_website
                    else:
                        biz["social_or_directory_link"] = raw_website
                        biz["social_or_directory_class"] = url_class
            osm_new = dedupe_against(osm_raw, listings)
            for biz in osm_new:
                seen_names.add(biz["name"])
                listings.append(biz)
            print(f"  ── OSM: {len(osm_raw)} found, {len(osm_new)} new (not already in Maps results)\n")
        except Exception as e:
            print(f"  ⚠ OSM augment failed, continuing with Maps-only results: {e}\n")

        # ── STEP 2: WEBSITE FILTER ────────────────────────
        print(f"{'='*60}")
        print(f"STEP 2: WEBSITE FILTER — Input: {len(listings)}")
        print(f"{'='*60}\n")
        
        no_website = [b for b in listings if not b["has_website"]]
        wc = len(listings) - len(no_website)
        print(f"  ── {len(no_website)} pass (no website) | {wc} disqualified\n")
        
        # ── STEP 3: ACTIVITY CHECK (soft: phone icon counts) ─
        print(f"{'='*60}")
        print(f"STEP 3: ACTIVITY VERIFICATION")
        print(f"Requirements: Phone icon/num ✓ | Rating ≥ {MIN_RATING} | Reviews ≥ {MIN_REVIEWS}")
        print(f"{'='*60}\n")
        
        qualified = []
        phone_icon_but_no_number = []  # has icon, needs phone digits
        dumped = 0
        
        for biz in no_website:
            has_phone_signal = bool(biz["phone"]) or biz.get("has_phone_icon")
            
            # Accept if either: (rating >= MIN_RATING) OR (has reviews > 0).
            # OSM has no rating/review data at all, so an OSM-sourced lead
            # with a phone number is treated as active by default — it has
            # no Maps signal to judge "active" by, and a listed phone
            # number is itself a decent proxy for a maintained business.
            has_activity = (
                (biz["rating"] >= MIN_RATING) or (biz["reviews"] > MIN_REVIEWS)
                or (biz.get("source") == "OpenStreetMap" and has_phone_signal)
            )
            
            if has_activity:
                if has_phone_signal:
                    if biz["phone"]:
                        qualified.append(biz)
                        print(f"  ✓ QUAL: {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']}) | 📞 {biz['phone']}")
                    else:
                        phone_icon_but_no_number.append(biz)
                        print(f"  ➤ PHONE-ICON: {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']}) | need digits")
                else:
                    # Still try to enrich - might have phone on place page
                    phone_icon_but_no_number.append(biz)
                    print(f"  ➤ NO-PHONE-SIGNAL: {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']}) | will enrich")
            else:
                dumped += 1
                print(f"  ✗ DUMP (low activity): {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']})")
        
        print(f"\n  ── {len(qualified)} qualified + {len(phone_icon_but_no_number)} phone-icon-needs-enrich | {dumped} dumped\n")

        # ── STEP 4: ENRICH CANDIDATES, SORT INTO TWO LEAD LISTS ──
        # The place page is the *authoritative* source for website presence
        # and review count — hotel/resort feed cards frequently omit both,
        # so every candidate must be individually verified, not just the
        # first target_leads. Every candidate ends up in exactly one of two
        # buckets: no_website_leads (real website-sales pitch) or
        # has_website_leads (already has a site — different pitch, e.g.
        # WhatsApp automation). Only a real own-domain site counts as
        # "has a website" — see classify_url(); a Facebook/Instagram link
        # in the Maps profile does NOT move a business out of no_website.
        candidates = qualified + phone_icon_but_no_number
        no_website_leads = []
        has_website_leads = []

        print(f"{'='*60}")
        print(f"STEP 4: ENRICHMENT — verifying candidates, need {target_leads} confirmed no-website")
        print(f"Pool: {len(candidates)} candidates")
        print(f"{'='*60}\n")

        checked = 0
        for biz in candidates:
            if len(no_website_leads) >= target_leads:
                print(f"\n  ── Reached {target_leads} confirmed no-website leads, stopping early\n")
                break
            checked += 1
            print(f"  [{checked}/{len(candidates)}] {biz['name'][:45]}...")
            await enrich_business(page, biz, cards_info, region)
            await asyncio.sleep(1)

            if not biz["phone"]:
                print(f"     ✗ No phone found — skipped (not usable for either list)")
                continue

            if biz["has_website"]:
                has_website_leads.append(biz)
                print(f"     ★ HAS-WEBSITE LEAD ({biz['website_url']}) — {len(has_website_leads)} so far")
                continue

            # No real website on the Maps profile — cross-check via a real
            # web search, since owners often have a site but never linked
            # it to their Google Business Profile.
            found, url, note = web_search_verify_website(
                biz["name"], location, keyword, biz.get("category", "")
            )
            biz["web_search_website"] = url
            biz["web_search_note"] = note
            if found:
                biz["website_url"] = url
                has_website_leads.append(biz)
                print(f"     ★ HAS-WEBSITE LEAD, found via web search ({url}) — {len(has_website_leads)} so far")
                continue

            no_website_leads.append(biz)
            print(f"     ✓ CONFIRMED no-website lead ({len(no_website_leads)}/{target_leads})")

        print(f"\n  ── Final: {len(no_website_leads)}/{target_leads} confirmed no-website leads, "
              f"{len(has_website_leads)} has-website leads (checked {checked}/{len(candidates)} candidates)\n")

        for label, leads in [("NO-WEBSITE", no_website_leads), ("HAS-WEBSITE", has_website_leads)]:
            print(f"\n{'='*80}")
            print(f"{label} LEAD TABLE — {keyword} in {location}")
            print(f"{'='*80}")
            print(f"{'#':<3} {'Business Name':<38} {'Phone':<18} {'★':<5} {'Rev':<5}")
            print(f"{'-'*3} {'-'*38} {'-'*18} {'-'*5} {'-'*5}")
            for i, biz in enumerate(leads, 1):
                name = biz["name"][:36] if len(biz["name"]) > 36 else biz["name"]
                phone = biz["phone"][:16] if len(biz["phone"]) > 16 else biz["phone"]
                print(f"{i:<3} {name:<38} {phone:<18} {biz['rating']:<5.1f} {biz['reviews']:<5}")
            print(f"{'='*80}\n")

        await browser.close()

    return no_website_leads, has_website_leads


def write_leads_csv(leads: list, csv_path: str, has_website: bool = False) -> None:
    """Write a list of lead dicts (as returned by scrape_area) to a CSV
    file. Shared by single-area runs and the multi-area orchestrator.
    Set has_website=True when writing the has-website bucket — adds
    Website URL/Type columns instead of the web-search-verification note.

    For the no-website bucket (has_website=False), each row is also scored
    for purchase intent (see score_lead()) and the list is written sorted
    best-prospect-first, so the CSV itself reads in call priority order."""
    if not has_website:
        leads = sorted(leads, key=lambda b: score_lead(b)[0], reverse=True)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        base_cols = [
            "Business Name", "Contact Person", "Phone Number",
            "Location", "Google Rating", "Review Count", "Profile Claimed?",
            "Google Maps URL",
        ]
        if has_website:
            writer.writerow(base_cols + ["Website URL", "Source"])
        else:
            writer.writerow(base_cols + ["Lead Score", "Priority", "Social Presence",
                                          "Web Search Verification", "Source"])

        for biz in leads:
            row = [
                biz["name"],
                biz.get("owner_name", ""),
                biz["phone"],
                biz["address"],
                biz["rating"],
                biz["reviews"],
                biz.get("profile_claimed", "Unknown"),
                biz.get("maps_url", ""),
            ]
            if has_website:
                row.append(biz.get("website_url", ""))
            else:
                score, tier = score_lead(biz)
                row.append(score)
                row.append(tier)
                row.append(biz.get("social_or_directory_class", "") or "none")
                row.append(biz.get("web_search_note", ""))
            row.append(biz.get("source", "Google Maps"))
            writer.writerow(row)


def read_leads_csv(csv_path: str, has_website: bool = False) -> list:
    """Read a CSV previously written by write_leads_csv back into a list of
    lead dicts, for resuming a multi-area run without losing (or
    re-fetching) already-confirmed leads. Returns [] if the file doesn't
    exist yet — resuming from nothing is a normal first run, not an error."""
    path = Path(csv_path)
    if not path.exists():
        return []
    leads = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            biz = {
                "name": row.get("Business Name", ""),
                "owner_name": row.get("Contact Person", ""),
                "phone": row.get("Phone Number", ""),
                "address": row.get("Location", ""),
                "rating": float(row.get("Google Rating") or 0),
                "reviews": int(row.get("Review Count") or 0),
                "profile_claimed": row.get("Profile Claimed?", "Unknown"),
                "maps_url": row.get("Google Maps URL", ""),
                # Missing column = a CSV written before OSM support existed;
                # every one of those rows came from Google Maps.
                "source": row.get("Source") or "Google Maps",
            }
            if has_website:
                biz["website_url"] = row.get("Website URL", "")
            else:
                biz["web_search_note"] = row.get("Web Search Verification", "")
                social_class = row.get("Social Presence", "none")
                biz["social_or_directory_class"] = "" if social_class == "none" else social_class
            leads.append(biz)
    return leads


async def _main():
    no_website_leads, has_website_leads = await scrape_area(LOCATION, KEYWORD, TARGET_LEADS, DISCOVERY_CAP)
    no_website_path = "/workspaces/Hermes-leads/resorts_wayanad_leads.csv"
    has_website_path = "/workspaces/Hermes-leads/resorts_wayanad_has_website_leads.csv"
    write_leads_csv(no_website_leads, no_website_path, has_website=False)
    write_leads_csv(has_website_leads, has_website_path, has_website=True)
    print(f"✓ DONE — no-website CSV: {no_website_path}")
    print(f"✓ DONE — has-website CSV: {has_website_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
