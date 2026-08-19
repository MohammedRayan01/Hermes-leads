#!/usr/bin/env python3
"""
Example: Run the scraper with custom parameters
This demonstrates how to configure and run the lead scraper for different niches
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PRE-CONFIGURED EXAMPLES — Uncomment one to use
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Example 1: Plumbers in Austin, TX (DEFAULT)
KEYWORD = "Plumbers"
LOCATION = "Austin, TX"
DISCOVERY_CAP = 60
TARGET_LEADS = 10
MIN_RATING = 3.0
MIN_REVIEWS = 3

# Example 2: Dentists in Seattle, WA
# KEYWORD = "Dentists"
# LOCATION = "Seattle, WA"
# DISCOVERY_CAP = 80
# TARGET_LEADS = 15
# MIN_RATING = 4.0
# MIN_REVIEWS = 5

# Example 3: HVAC Services in Phoenix, AZ
# KEYWORD = "HVAC Services"
# LOCATION = "Phoenix, AZ"
# DISCOVERY_CAP = 100
# TARGET_LEADS = 20
# MIN_RATING = 3.5
# MIN_REVIEWS = 3

# Example 4: Restaurants in Portland, OR
# KEYWORD = "Restaurants"
# LOCATION = "Portland, OR"
# DISCOVERY_CAP = 120
# TARGET_LEADS = 25
# MIN_RATING = 3.0
# MIN_REVIEWS = 10

# Example 5: Auto Repair in Denver, CO
# KEYWORD = "Auto Repair"
# LOCATION = "Denver, CO"
# DISCOVERY_CAP = 60
# TARGET_LEADS = 10
# MIN_RATING = 3.5
# MIN_REVIEWS = 5

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import sys
import subprocess
import tempfile
from pathlib import Path

OUTPUT_FILE = f"{KEYWORD.lower().replace(' ', '_')}_{LOCATION.lower().replace(', ', '_').replace(' ', '_')}_leads.csv"

def main():
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          GOOGLE MAPS LEAD SCRAPER — CUSTOM RUN               ║
╚══════════════════════════════════════════════════════════════╝

  🎯 Target Niche:     {KEYWORD}
  📍 Target Location:  {LOCATION}
  🔍 Discovery Cap:    {DISCOVERY_CAP} listings
  📊 Target Leads:     {TARGET_LEADS} qualified businesses
  ⭐ Min Rating:       {MIN_RATING} stars
  💬 Min Reviews:      {MIN_REVIEWS} reviews
  
  📁 Output File:      {OUTPUT_FILE}

╔══════════════════════════════════════════════════════════════╗
║                  QUALIFICATION CRITERIA                      ║
╚══════════════════════════════════════════════════════════════╝

  ✓ NO active website detected
  ✓ Valid phone number listed
  ✓ Google rating ≥ {MIN_RATING} stars
  ✓ Review count ≥ {MIN_REVIEWS}
  ✓ Active Google Business Profile

╔══════════════════════════════════════════════════════════════╗
║                  STARTING SCRAPER...                         ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Read the scraper template
    scraper_path = Path("google_maps_scraper.py")
    if not scraper_path.exists():
        print("❌ Error: google_maps_scraper.py not found!")
        return 1
    
    with open(scraper_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace config values
    replacements = {
        'KEYWORD = "Dentists"': f'KEYWORD = "{KEYWORD}"',
        'LOCATION = "Bangalore India"': f'LOCATION = "{LOCATION}"',
        'DISCOVERY_CAP = 60': f'DISCOVERY_CAP = {DISCOVERY_CAP}',
        'TARGET_LEADS = 10': f'TARGET_LEADS = {TARGET_LEADS}',
        'MIN_RATING = 3.0': f'MIN_RATING = {MIN_RATING}',
        'MIN_REVIEWS = 3': f'MIN_REVIEWS = {MIN_REVIEWS}',
        'csv_path = "/workspaces/Hermes-leads/dentists_bangalore_leads.csv"': 
            f'csv_path = "/workspaces/Hermes-leads/{OUTPUT_FILE}"',
    }
    
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Run the scraper
        result = subprocess.run([sys.executable, tmp_path], cwd=Path.cwd())
        
        if result.returncode == 0:
            print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    ✅ SCRAPING COMPLETE                      ║
╚══════════════════════════════════════════════════════════════╝

  📊 Results saved to: {OUTPUT_FILE}
  
  Next steps:
    
    1. Review the CSV:
       cat {OUTPUT_FILE}
    
    2. Import to your CRM or spreadsheet
    
    3. Start your outreach campaign!
    
  💡 Tips for outreach:
    • Call during business hours (9am-5pm local time)
    • Mention their Google reviews in your pitch
    • Offer a free website audit or mockup
    • Focus on how a website improves local SEO
    
╚══════════════════════════════════════════════════════════════╝
""")
        else:
            print(f"\n❌ Scraper failed with exit code {result.returncode}\n")
    
    finally:
        # Cleanup
        Path(tmp_path).unlink(missing_ok=True)
    
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
