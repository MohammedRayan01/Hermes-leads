#!/usr/bin/env python3
"""
Lead Scraper Configuration & Runner
Quick wrapper to run google_maps_scraper.py with custom parameters
"""
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION — Edit these values to customize your search
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KEYWORD = "Plumbers"           # Business type/niche
LOCATION = "Austin, TX"         # City/region
DISCOVERY_CAP = 60              # Max listings to scan
TARGET_LEADS = 10               # Number of qualified leads to collect
MIN_RATING = 3.0                # Minimum Google rating
MIN_REVIEWS = 3                 # Minimum review count

OUTPUT_FILE = f"{KEYWORD.lower().replace(' ', '_')}_{LOCATION.lower().replace(', ', '_').replace(' ', '_')}_leads.csv"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def update_scraper_config():
    """Dynamically update the scraper's config values"""
    scraper_path = Path("google_maps_scraper.py")
    
    if not scraper_path.exists():
        print("❌ Error: google_maps_scraper.py not found!")
        sys.exit(1)
    
    # Read the original scraper
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
    
    return tmp_path


def main():
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          GOOGLE MAPS LEAD SCRAPER — CONFIGURATION            ║
╚══════════════════════════════════════════════════════════════╝

  Target Keyword:    {KEYWORD}
  Target Location:   {LOCATION}
  Discovery Cap:     {DISCOVERY_CAP} listings
  Target Leads:      {TARGET_LEADS} qualified leads
  Min Rating:        {MIN_RATING}
  Min Reviews:       {MIN_REVIEWS}
  Output File:       {OUTPUT_FILE}

  Filtering Criteria:
    ✓ No active website
    ✓ Has phone number
    ✓ Rating ≥ {MIN_RATING} stars
    ✓ Reviews ≥ {MIN_REVIEWS}

╔══════════════════════════════════════════════════════════════╗
║                    STARTING SCRAPER...                       ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Create temporary configured scraper
    tmp_scraper = update_scraper_config()
    
    try:
        # Run the scraper
        result = subprocess.run(
            [sys.executable, tmp_scraper],
            cwd=Path.cwd(),
        )
        
        if result.returncode == 0:
            print(f"""
╔══════════════════════════════════════════════════════════════╗
║                      ✓ SUCCESS                               ║
╚══════════════════════════════════════════════════════════════╝

  Leads saved to: {OUTPUT_FILE}
  
  Next steps:
    • Review the CSV file for data quality
    • Verify phone numbers are valid
    • Begin outreach campaign
    
""")
        else:
            print(f"\n❌ Scraper exited with code {result.returncode}\n")
            
    finally:
        # Cleanup temp file
        Path(tmp_scraper).unlink(missing_ok=True)
    
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
