#!/usr/bin/env python3
"""Quick debug: what does the feed text actually look like around phone icons?"""
import asyncio, re
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1920, "height": 1080}, locale="en-IN")
        await page.goto("https://www.google.com/maps/search/Dentists+Bangalore+India", timeout=60000)
        await page.wait_for_selector('[role="feed"]', timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Scroll a few times to load more results
        feed = await page.query_selector('[role="feed"]')
        for _ in range(5):
            await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
            await asyncio.sleep(1.5)
        
        feed_text = await feed.inner_text()
        
        # Find lines with phone icon marker
        lines = feed_text.split('\n')
        for i, line in enumerate(lines):
            # Look for the dot character · which separates fields
            if '·' in line and len(line) > 20:
                # Show context around it
                start = max(0, i-2)
                end = min(len(lines), i+3)
                print(f"\n--- Line {i} (has ·) ---")
                for j in range(start, end):
                    marker = ">>>" if j == i else "   "
                    # Show raw repr for unicode chars
                    print(f"{marker} [{j}] {lines[j].strip()[:120]}")
                    if j == i:
                        print(f"    REPR: {repr(lines[j].strip()[:120])}")
        
        # Also grab a few specific detail lines
        print("\n\n=== ALL LINES WITH 'Dentist' or 'Dental clinic' ===")
        for i, line in enumerate(lines):
            if re.match(r'^(Dentist|Dental\s+clinic|Dental\s+implants)', line.strip()):
                print(f"[{i}] REPR: {repr(line.strip()[:150])}")
                print(f"[{i}] TEXT: {line.strip()[:150]}")
        
        await browser.close()

asyncio.run(main())