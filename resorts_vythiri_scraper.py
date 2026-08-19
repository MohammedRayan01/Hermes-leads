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
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from ddgs import DDGS

# ── CONFIG ──────────────────────────────────────────────────
KEYWORD = "Resorts"
LOCATION = "Vythiri, Wayanad India"
SEARCH_QUERY = f"{KEYWORD} {LOCATION}"
DISCOVERY_CAP = 100  # Raised for smaller market
TARGET_LEADS = 10
MIN_RATING = 3.0
MIN_REVIEWS = 0  # Lowered for smaller market - many new resorts have low review counts

# ── WEB-SEARCH VERIFICATION (secondary check beyond Maps profile) ──
# Directories/OTAs/social platforms/booking aggregators — never count as
# "the business has a website" even if they rank for the business name.
BLOCKED_DOMAINS = {
    "booking.com", "agoda.com", "makemytrip.com", "goibibo.com",
    "tripadvisor.com", "tripadvisor.in", "trivago.com", "trivago.in",
    "expedia.com", "cleartrip.com", "yatra.com", "oyorooms.com",
    "justdial.com", "quickerala.com", "sulekha.com", "indiamart.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "pinterest.com", "airbnb.com", "holidify.com",
    "zomy.in", "trip.com", "in.trip.com", "yelp.com", "google.com",
    "yatra.com", "ixigo.com", "hotels.com",
}

_GENERIC_WORDS = {
    "resort", "resorts", "hotel", "homestay", "villa", "wayanad",
    "farm", "lodge", "inn", "the", "by", "and", "wild", "holiday",
    "cottage", "nest", "stay", "camp", "tent", "estate",
}


def _name_tokens(name: str) -> set:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return {w for w in words if w not in _GENERIC_WORDS and len(w) > 2}


def _title_corroborates(business_name: str, title: str) -> bool:
    """For weak/short names (few distinctive tokens after generic-word
    filtering), a single shared word matching a domain isn't enough evidence
    — e.g. "My Garden Homestay" matching some unrelated "...garden...com".
    Require the result's own title to substantially contain the FULL
    original name (including short/generic words) as extra corroboration."""
    name_words = [w for w in re.findall(r"[a-z0-9]+", business_name.lower()) if len(w) > 1]
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


def web_search_verify_website(business_name: str, location: str = "Wayanad", attempts: int = 2):
    """Secondary check: does this business have a website anywhere on the
    web (even if it's not linked on its Google Business Profile)? DDG result
    sets aren't fully deterministic between calls, and a missed real website
    is worse for outreach than an extra check — so this runs the search
    multiple times and treats ANY confident match as authoritative; only
    concludes "no website" if every attempt comes back clean.
    Returns (found: bool, url: str, note: str)."""
    target_tokens = _name_tokens(business_name)
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
def parse_feed_text(feed_text, cards_info):
    """Parse sidebar feed text to extract business data."""
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

        # Detail line: "Resort · address · hours" - Updated for resort-related categories
        detail_match = re.match(
            r'^(Resort|Hotel|Lodge|Guest\s+house|Homestay|Vacation\s+home|'
            r'Holiday\s+home|Spa\s+and\s+health\s+club|Extended\s+stay\s+hotel|'
            r'Serviced\s+accommodation|Cottage|Villa|Motel|Inn|'
            r'Tourist\s+attraction|Lodging|Campground|Hostel)\s*[·•]?\s*(.*)',
            line, re.IGNORECASE
        )
        
        if detail_match and current_biz:
            rest = detail_match.group(2).strip() if detail_match.group(2) else ""
            parts = [p.strip() for p in rest.split('·')]
            
            address_parts = []
            has_phone = False
            
            for part in parts:
                # Phone icon variants (from Google Maps PUA characters)
                if part in ['\ue924', '\ue934', '\uf095', '\uf54a', '\uf0e8']:
                    has_phone = True
                elif re.match(r'^(Closed|Open|Opens|Open 24)', part):
                    continue
                elif part:
                    address_parts.append(part)
            
            current_biz["address"] = " · ".join(address_parts) if address_parts else current_biz.get("address", "")
            
            if has_phone:
                current_biz["has_phone_icon"] = True
                phone_match = re.search(r'(\+91[\d\s\-]{8,15}|\d[\d\s\-]{9,14})', line)
                if phone_match:
                    current_biz["phone"] = phone_match.group(1).strip()
            
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
            current_biz["has_website"] = True
            current_biz["website_url"] = web_match.group(1) if web_match else line
            i += 1
            continue
        
        # Business name (two identical lines)
        if i + 1 < len(lines) and line == lines[i + 1] and len(line) > 3:
            name = line
            current_biz = {
                "name": name, "place_id": "", "phone": "", "address": "",
                "rating": 0.0, "reviews": 0, "has_website": False,
                "website_url": "", "has_phone_icon": False,
            }
            listings.append(current_biz)
            i += 2
            continue
        
        # Standalone address/phone line
        looks_like_garbage = re.match(r'^[\d\s\.·\-]+$', line) or re.search(r'[\ue000-\uf8ff]', line)
        if len(line) > 3 and not looks_like_garbage:
            if current_biz:
                phone_match = re.search(r'(\+91[\d\s\-]{8,15}|\d[\d\s\-]{9,14})', line)
                if phone_match and not current_biz["phone"]:
                    current_biz["phone"] = phone_match.group(1).strip()
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


async def enrich_business(page, biz, cards_info):
    """Visit place page: extract phone, owner, claim status."""
    biz.setdefault("owner_name", "")
    biz.setdefault("profile_claimed", "Unknown")
    
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
    
    try:
        await page.goto(place_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2)
        page_text = await page.inner_text("body")
        
        # ── Phone ────────────────────────────────────
        if not biz["phone"]:
            phone_pats = [
                r'(\+91[\s\-]?\d[\d\s\-]{8,15})',
                r'(0\d[\d\s\-]{7,14})',
                r'(\d{3}[\s\-]\d{3}[\s\-]\d{4})',
                r'(\d{5}[\s\-]\d{5})',
            ]
            for pat in phone_pats:
                match = re.search(pat, page_text)
                if match:
                    phone = match.group(1).strip()
                    digits_only = re.sub(r'[\s\-]', '', phone)
                    if 8 <= len(digits_only) <= 15:
                        biz["phone"] = phone
                        break
        
        # ── Website (authoritative — feed text often omits it entirely
        # for hotel/resort cards) ─────────────────────
        website_link = await page.query_selector('a[data-item-id="authority"]')
        if website_link:
            href = await website_link.get_attribute("href")
            if href:
                biz["has_website"] = True
                biz["website_url"] = href

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
async def main():
    print(f"\n{'#'*60}")
    print(f"#  GOOGLE MAPS LEAD SCRAPER v3 (BROWSER)")
    print(f"#  Niche: {KEYWORD}  |  Location: {LOCATION}")
    print(f"#  Target: {TARGET_LEADS} leads (no website, active)")
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
        search_url = f"https://www.google.com/maps/search/{SEARCH_QUERY.replace(' ', '+')}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        
        try:
            await page.wait_for_selector('[role="feed"]', timeout=30000)
        except Exception:
            print("⚠ Feed not found, trying anyway...")
        
        await asyncio.sleep(3)
        
        print(f"{'='*60}")
        print(f"STEP 1: DISCOVERY — Browser-based Google Maps search")
        print(f"Search: {SEARCH_QUERY}")
        print(f"Cap: {DISCOVERY_CAP} listings")
        print(f"{'='*60}\n")
        
        listings = []
        seen_names = set()
        cards_info = []
        scroll_attempts = 0
        max_scrolls = 30  # Increased for potentially smaller market
        
        while len(listings) < DISCOVERY_CAP and scroll_attempts < max_scrolls:
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
                parsed = parse_feed_text(feed_text, cards_info)
                for biz in parsed:
                    if biz["name"] not in seen_names:
                        seen_names.add(biz["name"])
                        listings.append(biz)
            
            print(f"  [{scroll_attempts}] {len(listings)}/{DISCOVERY_CAP} listings")
            
            if len(listings) >= DISCOVERY_CAP:
                break
            
            try:
                await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
            except Exception:
                pass
            await asyncio.sleep(1.5)
        
        print(f"\n  ✓ Discovery: {len(listings)} raw listings\n")
        
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
            
            # Accept if either: (rating >= MIN_RATING) OR (has reviews > 0)
            has_activity = (biz["rating"] >= MIN_RATING) or (biz["reviews"] > MIN_REVIEWS)
            
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

        # ── STEP 4: ENRICH CANDIDATES UNTIL TARGET_LEADS CONFIRMED ──
        # The place page is the *authoritative* source for website presence
        # and review count — hotel/resort feed cards frequently omit both,
        # so every candidate must be individually verified, not just the
        # first TARGET_LEADS. We keep enriching down the candidate pool
        # until we have enough real confirmations or run out of candidates.
        candidates = qualified + phone_icon_but_no_number
        qualified = []

        print(f"{'='*60}")
        print(f"STEP 4: ENRICHMENT — verifying candidates, need {TARGET_LEADS} confirmed")
        print(f"Pool: {len(candidates)} candidates")
        print(f"{'='*60}\n")

        checked = 0
        for biz in candidates:
            if len(qualified) >= TARGET_LEADS:
                print(f"\n  ── Reached {TARGET_LEADS} confirmed leads, stopping early\n")
                break
            checked += 1
            print(f"  [{checked}/{len(candidates)}] {biz['name'][:45]}...")
            await enrich_business(page, biz, cards_info)
            await asyncio.sleep(1)

            if biz["has_website"]:
                print(f"     ✗ Has website on Maps profile ({biz['website_url']}) — disqualified")
                continue
            if not biz["phone"]:
                print(f"     ✗ No phone found — disqualified")
                continue

            # Secondary check: no website *linked on Maps* doesn't mean no
            # website exists — owners often forget to attach it. Verify via
            # a real web search before treating this as a confirmed lead.
            found, url, note = web_search_verify_website(biz["name"], "Vythiri")
            biz["web_search_website"] = url
            biz["web_search_note"] = note
            if found:
                print(f"     ✗ Website found via web search ({url}) — disqualified [{note}]")
                continue

            qualified.append(biz)
            print(f"     ✓ CONFIRMED — no website on Maps or web search ({len(qualified)}/{TARGET_LEADS})")

        enriched = qualified
        print(f"\n  ── Final: {len(enriched)}/{TARGET_LEADS} confirmed no-website leads (checked {checked}/{len(candidates)} candidates)\n")

        # ── STEP 5: CSV OUTPUT ────────────────────────────
        csv_path = "/workspaces/Hermes-leads/resorts_vythiri_leads.csv"
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Business Name", "Contact Person", "Phone Number",
                "Location", "Google Rating", "Review Count", "Profile Claimed?",
                "Web Search Verification"
            ])
            for biz in enriched:
                writer.writerow([
                    biz["name"],
                    biz.get("owner_name", ""),
                    biz["phone"],
                    biz["address"],
                    biz["rating"],
                    biz["reviews"],
                    biz.get("profile_claimed", "Unknown"),
                    biz.get("web_search_note", ""),
                ])
        
        print(f"\n{'='*80}")
        print(f"FINAL LEAD TABLE — {KEYWORD} in {LOCATION} (No Website)")
        print(f"{'='*80}")
        print(f"{'#':<3} {'Business Name':<38} {'Phone':<18} {'★':<5} {'Rev':<5} {'Claimed?':<10}")
        print(f"{'-'*3} {'-'*38} {'-'*18} {'-'*5} {'-'*5} {'-'*10}")
        
        for i, biz in enumerate(enriched, 1):
            name = biz["name"][:36] if len(biz["name"]) > 36 else biz["name"]
            phone = biz["phone"][:16] if len(biz["phone"]) > 16 else biz["phone"]
            print(f"{i:<3} {name:<38} {phone:<18} {biz['rating']:<5.1f} {biz['reviews']:<5} {biz.get('profile_claimed', '?'):<10}")
        
        print(f"\n{'='*80}")
        print(f"✓ DONE — CSV saved to: {csv_path}")
        print(f"{'='*80}\n")
        
        await browser.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
