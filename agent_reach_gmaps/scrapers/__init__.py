"""Scrapers module — platform-specific scraping implementations."""

from .google_maps import (
    GoogleMapsScraper,
    GoogleMapsScraperConfig,
    Lead,
    scrape_leads,
    scrape_leads_sync,
)

__all__ = [
    "GoogleMapsScraper",
    "GoogleMapsScraperConfig",
    "Lead",
    "scrape_leads",
    "scrape_leads_sync",
]
