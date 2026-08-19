#!/usr/bin/env python3
"""
Test script for Google Maps scraper (agent-reach architecture)
Runs a small test to verify everything works.
"""

from agent_reach_gmaps import scrape_leads_sync

def main():
    print("\n" + "="*60)
    print("TESTING GOOGLE MAPS SCRAPER (agent-reach architecture)")
    print("="*60 + "\n")
    
    print("Running test scrape: Plumbers in Austin, TX (5 leads max)\n")
    
    try:
        leads = scrape_leads_sync(
            keyword="Plumbers",
            location="Austin, TX",
            count=5,  # Small test
            discovery_cap=30,  # Quick scan
            min_rating=3.0,
            min_reviews=3,
        )
        
        print(f"\n{'='*60}")
        print(f"✅ TEST PASSED — Found {len(leads)} leads")
        print(f"{'='*60}\n")
        
        if leads:
            print("Sample lead:")
            lead = leads[0]
            print(f"  Business: {lead.business_name}")
            print(f"  Phone: {lead.phone_number}")
            print(f"  Rating: {lead.google_rating} ⭐ ({lead.review_count} reviews)")
            print(f"  Location: {lead.location}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
