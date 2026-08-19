#!/usr/bin/env python3
"""
DEBUG: Inspect Google Maps result card DOM structure
to find correct selectors for phone, rating, reviews, website.
"""

import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        
        await page.goto("https://www.google.com/maps/search/Dentists+Bangalore+India", timeout=60000)
        await page.wait_for_selector('[role="feed"]', timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Grab the first 3 result cards
        cards = await page.query_selector_all('[role="feed"] > div > div > a, [role="feed"] a[href*="/place/"]')
        print(f"Found {len(cards)} cards\n")
        
        for i, card in enumerate(cards[:5]):
            print(f"\n{'='*60}")
            print(f"CARD {i+1}")
            print(f"{'='*60}")
            
            # Full HTML of card
            html = await card.evaluate("el => el.outerHTML")
            print(f"HTML (first 1500 chars):\n{html[:1500]}\n")
            
            # Inner text
            text = await card.inner_text()
            print(f"INNER TEXT:\n{text[:500]}\n")
            
            # aria-label
            aria = await card.get_attribute("aria-label")
            print(f"ARIA-LABEL: {aria}\n")
            
            # href
            href = await card.get_attribute("href")
            print(f"HREF: {href}\n")
        
        # Also grab the sidebar panel text structure
        print(f"\n{'='*60}")
        print("SIDEBAR FULL TEXT (first 2000 chars)")
        print(f"{'='*60}")
        
        feed = await page.query_selector('[role="feed"]')
        if feed:
            feed_text = await feed.inner_text()
            print(feed_text[:2000])
        
        await browser.close()

asyncio.run(main())