#!/usr/bin/env python3
"""
Quick Test Script — Verify scraper setup and run a mini test
"""
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Verify all required packages are installed"""
    print("🔍 Checking dependencies...\n")
    
    checks = {
        "playwright": "import playwright; print('✓ Playwright:', playwright.__version__)",
        "asyncio": "import asyncio; print('✓ asyncio: built-in')",
        "csv": "import csv; print('✓ csv: built-in')",
        "re": "import re; print('✓ re: built-in')",
    }
    
    all_good = True
    for name, cmd in checks.items():
        result = subprocess.run(
            [sys.executable, "-c", cmd],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"  {result.stdout.strip()}")
        else:
            print(f"  ❌ {name}: NOT INSTALLED")
            all_good = False
    
    print()
    return all_good


def check_browsers():
    """Check if Playwright browsers are installed"""
    print("🌐 Checking Playwright browsers...\n")
    
    result = subprocess.run(
        [sys.executable, "-c", "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print('✓ Chromium:', 'installed' if p.chromium.executable_path else 'missing'); p.stop()"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode == 0:
        print(f"  {result.stdout.strip()}\n")
        return True
    else:
        print("  ❌ Browsers not installed\n")
        print("  Run: playwright install chromium\n")
        return False


def show_config():
    """Display current scraper configuration"""
    print("⚙️  Current Configuration:\n")
    
    scraper_path = Path("google_maps_scraper.py")
    if not scraper_path.exists():
        print("  ❌ google_maps_scraper.py not found!\n")
        return False
    
    with open(scraper_path, 'r') as f:
        lines = f.readlines()
    
    config_lines = {
        "KEYWORD": 16,
        "LOCATION": 17,
        "DISCOVERY_CAP": 19,
        "TARGET_LEADS": 20,
        "MIN_RATING": 21,
        "MIN_REVIEWS": 22,
    }
    
    for key, line_num in config_lines.items():
        if line_num < len(lines):
            line = lines[line_num].strip()
            print(f"  {line}")
    
    print()
    return True


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║        GOOGLE MAPS LEAD SCRAPER — SETUP VERIFICATION         ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Check dependencies
    deps_ok = check_dependencies()
    
    # Check browsers
    browsers_ok = check_browsers()
    
    # Show config
    config_ok = show_config()
    
    # Summary
    print("="*64)
    if deps_ok and browsers_ok and config_ok:
        print("✅ ALL CHECKS PASSED — Ready to scrape!")
        print("\nTo run the scraper:")
        print("  1. Edit run_scraper.py with your target keyword/location")
        print("  2. Run: python3 run_scraper.py")
        print("\nOr directly:")
        print("  python3 google_maps_scraper.py")
    else:
        print("⚠️  SETUP INCOMPLETE")
        if not deps_ok:
            print("\n  Install dependencies: pip install playwright")
        if not browsers_ok:
            print("  Install browsers: playwright install chromium")
        if not config_ok:
            print("  Ensure google_maps_scraper.py exists")
    
    print("="*64 + "\n")
    
    return 0 if (deps_ok and browsers_ok and config_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
