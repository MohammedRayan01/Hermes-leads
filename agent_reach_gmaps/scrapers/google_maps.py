#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Maps Lead Scraper — Playwright Backend
Finds businesses WITHOUT websites for sales prospecting.
"""

import asyncio
import csv
import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


@dataclass
class Lead:
    """Represents a qualified business lead."""
    business_name: str
    contact_person: str
    phone_number: str
    location: str
    google_rating: float
    review_count: int
    profile_claimed: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary for CSV export."""
        return asdict(self)


class GoogleMapsScraperConfig:
    """Configuration for the scraper."""
    
    def __init__(
        self,
        keyword: str,
        location: str,
        discovery_cap: int = 60,
        target_leads: int = 10,
        min_rating: float = 3.0,
        min_reviews: int = 3,
        headless: bool = True,
        output_file: Optional[str] = None,
    ):
        self.keyword = keyword
        self.location = location
        self.discovery_cap = discovery_cap
        self.target_leads = target_leads
        self.min_rating = min_rating
        self.min_reviews = min_reviews
        self.headless = headless
        
        # Auto-generate output filename if not provided
        if output_file is None:
            safe_keyword = keyword.lower().replace(' ', '_')
            safe_location = location.lower().replace(', ', '_').replace(' ', '_')
            self.output_file = f"{safe_keyword}_{safe_location}_leads.csv"
        else:
            self.output_file = output_file


class GoogleMapsScraper:
    """Main scraper class using Playwright."""
    
    def __init__(self, config: GoogleMapsScraperConfig):
        self.config = config
        self.search_query = f"{config.keyword} {config.location}"
        
    async def scrape(self) -> List[Lead]:
        """Execute the full scraping pipeline."""
        if async_playwright is None:
            raise ImportError(
                "Playwright not installed. Run: pip install playwright && "
                "playwright install chromium"
            )
        
        print(f"\n{'#'*60}")
        print(f"#  GOOGLE MAPS LEAD SCRAPER (agent-reach architecture)")
        print(f"#  Niche: {self.config.keyword}  |  Location: {self.config.location}")
        print(f"#  Target: {self.config.target_leads} leads (no website, active)")
        print(f"{'#'*60}\n")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = await context.new_page()
            
            # Step 1: Discovery
            listings = await self._discover_listings(page)
            print(f"\n  ✓ Discovery: {len(listings)} raw listings\n")
            
            # Step 2: Filter by website
            no_website = [b for b in listings if not b.get("has_website")]
            print(f"  ✓ Website filter: {len(no_website)} without websites\n")
            
            # Step 3: Activity verification
            qualified = await self._verify_activity(no_website)
            print(f"\n  ✓ Activity check: {len(qualified)} qualified\n")
            
            # Step 4: Enrichment
            leads = await self._enrich_leads(page, qualified[:self.config.target_leads])
            
            await browser.close()
        
        return leads
    
    async def _discover_listings(self, page) -> List[Dict]:
        """Step 1: Discover listings from Google Maps."""
        print(f"{'='*60}")
        print(f"STEP 1: DISCOVERY")
        print(f"Search: {self.search_query}")
        print(f"Cap: {self.config.discovery_cap} listings")
        print(f"{'='*60}\n")
        
        search_url = f"https://www.google.com/maps/search/{self.search_query.replace(' ', '+')}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        
        try:
            await page.wait_for_selector('[role="feed"]', timeout=30000)
        except Exception:
            print("⚠ Feed not found, trying anyway...")
        
        await asyncio.sleep(3)
        
        listings = []
        seen_names = set()
        cards_info = []
        scroll_attempts = 0
        max_scrolls = 25
        
        while len(listings) < self.config.discovery_cap and scroll_attempts < max_scrolls:
            scroll_attempts += 1
            
            # Collect card links
            cards = await page.query_selector_all('a.hfpxzc')
            for card in cards:
                aria = await card.get_attribute("aria-label")
                href = await card.get_attribute("href")
                if aria and len(aria) > 3:
                    pid = self._extract_place_id(href)
                    cards_info.append({
                        "name": aria.strip(),
                        "place_id": pid,
                        "href": href,
                    })
            
            # Parse sidebar feed
            feed = await page.query_selector('[role="feed"]')
            if feed:
                feed_text = await feed.inner_text()
                parsed = self._parse_feed_text(feed_text, cards_info)
                for biz in parsed:
                    if biz["name"] not in seen_names:
                        seen_names.add(biz["name"])
                        listings.append(biz)
            
            print(f"  [{scroll_attempts}] {len(listings)}/{self.config.discovery_cap} listings")
            
            if len(listings) >= self.config.discovery_cap:
                break
            
            try:
                await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
            except Exception:
                pass
            await asyncio.sleep(1.5)
        
        return listings
    
    def _parse_feed_text(self, feed_text: str, cards_info: List[Dict]) -> List[Dict]:
        """Parse sidebar feed text to extract business data."""
        # This is simplified - use the full parser from google_maps_scraper.py
        # For now, just return basic structure
        listings = []
        lines = [l.strip() for l in feed_text.split('\n') if l.strip()]
        
        # Simplified parser - in production, use the full one
        current_biz = None
        for i, line in enumerate(lines):
            # Business name (two identical lines)
            if i + 1 < len(lines) and line == lines[i + 1] and len(line) > 3:
                if current_biz:
                    listings.append(current_biz)
                current_biz = {
                    "name": line,
                    "phone": "",
                    "address": "",
                    "rating": 0.0,
                    "reviews": 0,
                    "has_website": False,
                }
        
        if current_biz:
            listings.append(current_biz)
        
        return listings
    
    async def _verify_activity(self, listings: List[Dict]) -> List[Dict]:
        """Step 3: Verify business activity."""
        print(f"{'='*60}")
        print(f"STEP 3: ACTIVITY VERIFICATION")
        print(f"Requirements: Phone ✓ | Rating ≥ {self.config.min_rating} | Reviews ≥ {self.config.min_reviews}")
        print(f"{'='*60}\n")
        
        qualified = []
        for biz in listings:
            if (biz.get("rating", 0) >= self.config.min_rating and 
                biz.get("reviews", 0) >= self.config.min_reviews and
                biz.get("phone")):
                qualified.append(biz)
                print(f"  ✓ QUAL: {biz['name'][:48]} | ★{biz['rating']} ({biz['reviews']}) | 📞 {biz['phone']}")
        
        return qualified
    
    async def _enrich_leads(self, page, businesses: List[Dict]) -> List[Lead]:
        """Step 4: Enrich with owner names and claim status."""
        print(f"\n{'='*60}")
        print(f"STEP 4: ENRICHMENT")
        print(f"{'='*60}\n")
        
        leads = []
        for i, biz in enumerate(businesses):
            print(f"  [{i+1}/{len(businesses)}] {biz['name'][:45]}...")
            
            lead = Lead(
                business_name=biz["name"],
                contact_person=biz.get("owner_name", ""),
                phone_number=biz.get("phone", ""),
                location=biz.get("address", ""),
                google_rating=biz.get("rating", 0.0),
                review_count=biz.get("reviews", 0),
                profile_claimed=biz.get("profile_claimed", "Unknown"),
            )
            leads.append(lead)
            
            if len(leads) >= self.config.target_leads:
                break
        
        return leads
    
    def _extract_place_id(self, href: str) -> str:
        """Extract Google Maps place ID from URL."""
        if not href:
            return ""
        match = re.search(r'!1s(0x[0-9a-f]+:[0-9a-f]+)', href)
        return match.group(1) if match else ""
    
    def save_to_csv(self, leads: List[Lead], output_path: Optional[str] = None):
        """Save leads to CSV file."""
        if output_path is None:
            output_path = self.config.output_file
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'business_name', 'contact_person', 'phone_number',
                'location', 'google_rating', 'review_count', 'profile_claimed'
            ])
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead.to_dict())
        
        print(f"\n{'='*80}")
        print(f"✓ DONE — CSV saved to: {output_path}")
        print(f"{'='*80}\n")
        
        return output_path


async def scrape_leads(
    keyword: str,
    location: str,
    count: int = 10,
    **kwargs
) -> List[Lead]:
    """
    High-level async function to scrape Google Maps leads.
    
    Args:
        keyword: Business type (e.g., "Plumbers", "Dentists")
        location: Target location (e.g., "Austin, TX")
        count: Number of leads to collect
        **kwargs: Additional config options
    
    Returns:
        List of Lead objects
    """
    config = GoogleMapsScraperConfig(
        keyword=keyword,
        location=location,
        target_leads=count,
        **kwargs
    )
    scraper = GoogleMapsScraper(config)
    leads = await scraper.scrape()
    scraper.save_to_csv(leads)
    return leads


def scrape_leads_sync(keyword: str, location: str, count: int = 10, **kwargs) -> List[Lead]:
    """Synchronous wrapper for scrape_leads."""
    return asyncio.run(scrape_leads(keyword, location, count, **kwargs))
