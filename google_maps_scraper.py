#!/usr/bin/env python3
"""
Google Maps Lead Scraper — Browser-based (Playwright) v3
Strategy: Sidebar feed text parse + place page enrichment
Niche: Dentists | Location: Bangalore, India
Target: Exactly 10 verified active businesses WITHOUT websites.
"""

import asyncio
import csv
import re
import sys
from playwright.async_api import async_playwright

# ── CONFIG ──────────────────────────────────────────────────
KEYWORD = "Dentists"
LOCATION = "Bangalore India"
SEARCH_QUERY = f"{KEYWORD} {LOCATION}"
DISCOVERY_CAP = 60
TARGET_LEADS = 10
MIN_RATING = 3.0
MIN_REVIEWS = 3

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
        
        # Detail line: "Dentist · address · hours"
        detail_match = re.match(
            r'^(Dentist|Dental\s+clinic|Dental\s+implants\s+periodontist|'
            r'Orthodontist|Prosthodontist|Endodontist|Oral\s+surgeon|'
            r'Periodontist|Cosmetic\s+dentist|Pediatric\s+dentist|'
            r'Dental\s+hygienist|Hospital|Clinic|Doctor|'
            r'Health\s+spa|Medical\s+clinic)\s*[·•]?\s*(.*)',
            line
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
        
        # Website URL line
        web_match = re.match(r'^(https?://[^\s]+)', line)
        if web_match and current_biz:
            current_biz["has_website"] = True
            current_biz["website_url"] = web_match.group(1)
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
                elif re.search(r'(?:Road|Street|Nagar|Layout|Main|Cross|Signal|near|opposite|above|Floor)', line):
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
        
        # ── Owner / Dr. name ────────────────────────
        owner = re.search(
            r'(?:Dr\.|Doctor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
            page_text
        )
        if owner:
            biz["owner_name"] = owner.group(0).strip()
        
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
        max_scrolls = 25
        
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
            
            if biz["rating"] >= MIN_RATING and biz["reviews"] >= MIN_REVIEWS:
                if has_phone_signal:
                    if biz["phone"]:
                        qualified.append(biz)
                        print(f"  ✓ QUAL: {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']}) | 📞 {biz['phone']}")
                    else:
                        phone_icon_but_no_number.append(biz)
                        print(f"  ➤ PHONE-ICON: {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']}) | need digits")
                else:
                    dumped += 1
                    print(f"  ✗ DUMP (no phone): {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']})")
            else:
                dumped += 1
                print(f"  ✗ DUMP (low activity): {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']})")
        
        print(f"\n  ── {len(qualified)} qualified + {len(phone_icon_but_no_number)} phone-icon-needs-enrich | {dumped} dumped\n")
        
        # ── STEP 3b: Fetch phones for phone-icon leads ──────
        for biz in phone_icon_but_no_number:
            if len(qualified) >= TARGET_LEADS:
                break
            print(f"  Fetching phone: {biz['name'][:45]}...")
            await enrich_business(page, biz, cards_info)
            if biz["phone"]:
                qualified.append(biz)
                if len(qualified) >= TARGET_LEADS:
                    break
            await asyncio.sleep(1)
        
        # Return to search for remaining enrichment
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        print(f"\n  ── After phone fetch: {len(qualified)} qualified leads\n")
        
        # ── STEP 4: FULL ENRICHMENT ────────────────────────
        print(f"{'='*60}")
        print(f"STEP 4: ENRICHMENT — Phones, Owners, Claim Status")
        print(f"Enriching up to {TARGET_LEADS} leads...")
        print(f"{'='*60}\n")
        
        enriched = qualified[:TARGET_LEADS]
        
        for i, biz in enumerate(enriched):
            print(f"  [{i+1}/{len(enriched)}] {biz['name'][:45]}...")
            await enrich_business(page, biz, cards_info)
            await asyncio.sleep(1)
        
        # ── STEP 5: CSV OUTPUT ────────────────────────────
        csv_path = "/workspaces/Hermes-leads/dentists_bangalore_leads.csv"
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Business Name", "Contact Person", "Phone Number",
                "Location", "Google Rating", "Review Count", "Profile Claimed?"
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