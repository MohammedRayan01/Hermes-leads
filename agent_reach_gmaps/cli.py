#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Maps Lead Scraper — CLI Interface (agent-reach style)
"""

import sys
import argparse
from pathlib import Path

try:
    from .scrapers.google_maps import scrape_leads_sync, GoogleMapsScraperConfig
    from .channels.google_maps import GoogleMapsChannel
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agent_reach_gmaps.scrapers.google_maps import scrape_leads_sync, GoogleMapsScraperConfig
    from agent_reach_gmaps.channels.google_maps import GoogleMapsChannel


def cmd_scrape(args):
    """Run the lead scraper."""
    leads = scrape_leads_sync(
        keyword=args.keyword,
        location=args.location,
        count=args.leads,
        discovery_cap=args.discovery_cap,
        min_rating=args.min_rating,
        min_reviews=args.min_reviews,
        headless=not args.headed,
        output_file=args.output,
    )
    
    print(f"\n✅ Collected {len(leads)} qualified leads")
    print(f"   Saved to: {args.output or 'auto-generated filename'}")
    
    return 0


def cmd_doctor(args):
    """Check if Google Maps scraper is ready to use."""
    channel = GoogleMapsChannel()
    status, message = channel.check()
    
    print(f"\n{'='*60}")
    print(f"GOOGLE MAPS SCRAPER — HEALTH CHECK")
    print(f"{'='*60}\n")
    
    status_icon = {
        "ok": "✅",
        "warn": "⚠️",
        "error": "❌",
        "off": "⭕",
    }.get(status, "❓")
    
    print(f"{status_icon} Status: {status.upper()}")
    print(f"\n{message}\n")
    
    if channel.active_backend:
        print(f"Active backend: {channel.active_backend}")
    
    print(f"\n{'='*60}")
    
    # Return 0 for ok/warn, 1 for error/off
    return 0 if status in ("ok", "warn") else 1


def cmd_config(args):
    """Show configuration instructions."""
    channel = GoogleMapsChannel()
    print(channel.get_config_instructions())
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Google Maps Lead Scraper — Find businesses without websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s scrape --keyword "Plumbers" --location "Austin, TX" --leads 10
  %(prog)s doctor
  %(prog)s config
  
For more info: https://github.com/yourusername/agent-reach-gmaps
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Scrape command
    scrape_parser = subparsers.add_parser('scrape', help='Scrape Google Maps for leads')
    scrape_parser.add_argument('--keyword', '-k', required=True,
                              help='Business type (e.g., "Plumbers", "Dentists")')
    scrape_parser.add_argument('--location', '-l', required=True,
                              help='Target location (e.g., "Austin, TX")')
    scrape_parser.add_argument('--leads', '-n', type=int, default=10,
                              help='Number of qualified leads to collect (default: 10)')
    scrape_parser.add_argument('--discovery-cap', type=int, default=60,
                              help='Max listings to scan (default: 60)')
    scrape_parser.add_argument('--min-rating', type=float, default=3.0,
                              help='Minimum Google rating (default: 3.0)')
    scrape_parser.add_argument('--min-reviews', type=int, default=3,
                              help='Minimum review count (default: 3)')
    scrape_parser.add_argument('--headed', action='store_true',
                              help='Run browser in headed mode (show UI)')
    scrape_parser.add_argument('--output', '-o',
                              help='Output CSV file (default: auto-generated)')
    scrape_parser.set_defaults(func=cmd_scrape)
    
    # Doctor command
    doctor_parser = subparsers.add_parser('doctor', help='Check scraper health')
    doctor_parser.set_defaults(func=cmd_doctor)
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Show configuration instructions')
    config_parser.set_defaults(func=cmd_config)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
