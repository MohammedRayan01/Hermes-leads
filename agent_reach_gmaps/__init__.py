"""
Agent Reach Google Maps — Lead Scraper Extension

Find businesses without websites on Google Maps for sales prospecting.
Built on agent-reach architecture for modularity and maintainability.
"""

__version__ = "0.1.0"

from .scrapers.google_maps import (
    scrape_leads,
    scrape_leads_sync,
    GoogleMapsScraper,
    GoogleMapsScraperConfig,
    Lead,
)

from .channels.google_maps import GoogleMapsChannel

__all__ = [
    "scrape_leads",
    "scrape_leads_sync",
    "GoogleMapsScraper",
    "GoogleMapsScraperConfig",
    "Lead",
    "GoogleMapsChannel",
]
