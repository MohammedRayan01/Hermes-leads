#!/usr/bin/env bash
# Quick Start Guide — Google Maps Lead Scraper

cat << 'EOF'

╔══════════════════════════════════════════════════════════════╗
║           GOOGLE MAPS LEAD SCRAPER — QUICK START             ║
╚══════════════════════════════════════════════════════════════╝

📋 WHAT THIS DOES:
   Finds local businesses WITHOUT websites on Google Maps
   → Perfect for web dev agencies looking for new clients!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 OPTION 1: EASY MODE (Recommended)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Edit run_scraper.py:
   
   KEYWORD = "Plumbers"      # Your target niche
   LOCATION = "Austin, TX"   # Your target city
   TARGET_LEADS = 10         # How many leads you need

2. Run it:
   
   python3 run_scraper.py

3. Check output:
   
   cat plumbers_austin_tx_leads.csv

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 OPTION 2: DIRECT SCRAPER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Edit google_maps_scraper.py (lines 16-22):
   
   KEYWORD = "Dentists"
   LOCATION = "Bangalore India"
   DISCOVERY_CAP = 60
   TARGET_LEADS = 10
   MIN_RATING = 3.0
   MIN_REVIEWS = 3

2. Run it:
   
   python3 google_maps_scraper.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 EXAMPLE NICHES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Plumbers             →  High-value, often outdated sites
   HVAC Services        →  Seasonal demand, good prospects
   Dentists             →  Premium pricing, professional market
   Landscaping          →  Local-focused, website gaps
   Auto Repair          →  Technical services, web-shy
   Electricians         →  Licensed pros, older demographics
   Restaurants          →  Menu updates, online ordering needs
   Hair Salons          →  Booking systems, visual portfolios
   Pet Grooming         →  Local search dependent
   Locksmiths           →  Emergency services, simple sites

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Business Name      →  Full legal name
   Contact Person     →  Owner/Manager (if found)
   Phone Number       →  Verified contact
   Location           →  Full address
   Google Rating      →  Star rating (1.0-5.0)
   Review Count       →  Total reviews
   Profile Claimed?   →  Yes/No/Unknown

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ PERFORMANCE TIPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   • First run? Start with DISCOVERY_CAP = 30 (faster test)
   • Want more leads? Increase TARGET_LEADS to 25-50
   • High-quality only? Set MIN_RATING = 4.5, MIN_REVIEWS = 20
   • More volume? Lower MIN_RATING = 2.5, MIN_REVIEWS = 1
   
   Typical runtime: 2-5 minutes for 10 leads

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🛠️ TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Problem: "playwright not installed"
   Fix: pip install playwright && playwright install chromium
   
   Problem: Empty CSV output
   Fix: Try different keyword or lower MIN_RATING to 2.5
   
   Problem: No phone numbers found
   Fix: Many businesses hide phones; increase DISCOVERY_CAP
   
   Problem: "Feed not found" warning
   Fix: Check internet connection or increase timeout

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📚 MORE INFO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Full documentation: cat README.md
   Test setup: python3 test_setup.py
   View example output: cat dentists_bangalore_leads.csv

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF
