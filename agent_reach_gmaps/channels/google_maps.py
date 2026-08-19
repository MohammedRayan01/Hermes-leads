# -*- coding: utf-8 -*-
"""Google Maps — Lead scraping for businesses without websites."""

import shutil
from pathlib import Path
from typing import Optional

# Note: base.Channel not needed for standalone version
# from .base import Channel


class Channel:
    """Minimal Channel base class for standalone operation."""
    name: str = ""
    description: str = ""
    backends: list = []
    tier: int = 0
    active_backend: Optional[str] = None
    
    def ordered_backends(self, config=None):
        """Return backends in order (with optional user override)."""
        return self.backends


class GoogleMapsChannel(Channel):
    """Google Maps lead generation scraper.
    
    Finds businesses without websites on Google Maps for sales prospecting.
    Ideal for web dev agencies, digital marketing, and lead generation.
    """
    
    name = "google_maps"
    description = "Google Maps lead scraper (businesses without websites)"
    backends = ["playwright", "serpapi"]  # playwright is preferred, serpapi is fallback
    tier = 0  # zero-config (playwright only needs pip install)
    
    def can_handle(self, url: str) -> bool:
        """Check if this is a Google Maps search URL or query."""
        from urllib.parse import urlparse
        
        d = urlparse(url).netloc.lower()
        # Handle both direct URLs and search queries
        if "google.com/maps" in url.lower():
            return True
        if "maps.google.com" in d:
            return True
        # Also handle search-like queries that would go to Maps
        # (e.g., "Plumbers Austin TX")
        return False  # Explicit URLs only for can_handle
    
    def check(self, config=None):
        """Check if scraper backend is available and ready."""
        from ..probe import probe_command
        
        # Check ordered backends (user override respected)
        for backend in self.ordered_backends(config):
            if backend == "playwright":
                # Check if playwright is installed
                probe = probe_command("python3", ["-c", "import playwright"], 
                                    timeout=5, package="playwright")
                
                if probe.status == "missing":
                    continue  # Try next backend
                    
                if probe.status == "broken":
                    continue  # Try next backend
                    
                if not probe.ok:
                    continue  # Try next backend
                
                # Playwright installed, check for browsers
                browser_probe = probe_command(
                    "python3", 
                    ["-c", "from playwright.sync_api import sync_playwright; "
                     "p = sync_playwright().start(); "
                     "print('ok' if p.chromium.executable_path else 'missing'); "
                     "p.stop()"],
                    timeout=10
                )
                
                if browser_probe.ok and "ok" in browser_probe.output:
                    self.active_backend = "playwright"
                    return "ok", "Playwright + Chromium 已安装，可抓取 Google Maps"
                else:
                    self.active_backend = None
                    return "warn", (
                        "Playwright 已安装但缺少浏览器。运行：\n"
                        "  playwright install chromium"
                    )
            
            elif backend == "serpapi":
                # SerpApi requires API key
                if config and config.get("serpapi_key"):
                    self.active_backend = "serpapi"
                    return "ok", "SerpApi 已配置（需付费）"
                else:
                    continue  # No key, skip
        
        # No backend available
        self.active_backend = None
        return "off", (
            "Google Maps scraper 未安装。安装：\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )
    
    def get_config_instructions(self) -> str:
        """Return configuration instructions for users."""
        return """
Google Maps Lead Scraper Configuration:

ZERO-CONFIG (Recommended):
  pip install playwright
  playwright install chromium

ALTERNATIVE (Paid):
  Set SERPAPI_KEY environment variable for SerpApi backend
  (Costs $50/month for 5000 searches)

USAGE:
  gmaps-scraper --keyword "Plumbers" --location "Austin, TX" --leads 10
  
  Or from Python:
  from agent_reach_gmaps.scrapers.google_maps import scrape_leads
  leads = scrape_leads(keyword="Dentists", location="Seattle, WA", count=10)
"""
