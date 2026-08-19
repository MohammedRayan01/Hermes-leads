#!/usr/bin/env python3
"""
Multi-area lead orchestrator — runs the verified resorts_wayanad_scraper
pipeline across a list of sub-areas, accumulating confirmed no-website
leads into one deduplicated master list until TARGET_LEADS is hit or the
area list is exhausted. Also accumulates a second master list of
has-website leads found along the way (different pitch, e.g. WhatsApp
automation) — no target cap on that one, it's a byproduct of the same runs.

Why this exists: within a single area, once every discovered candidate has
been checked (see "checked N/N candidates" in scrape_area's log), that IS
the area's ceiling — there's nothing left to find there. The only way to
get more leads is to check more areas. This script automates that.

Dedup key: Google Maps URL (a stable per-business identifier), so the same
business turning up in overlapping area searches doesn't get double-counted.
"""

import asyncio
import sys

from resorts_wayanad_scraper import scrape_area, write_leads_csv

KEYWORD = "Resorts"
TARGET_LEADS = 10
DISCOVERY_CAP = 100

# Biggest-to-smaller Wayanad towns, roughly. Add/reorder as needed —
# order only affects which areas get skipped once the target is hit.
AREAS = [
    "Vythiri, Wayanad India",
    "Kalpetta, Wayanad India",
    "Meppadi, Wayanad India",
    "Sulthan Bathery, Wayanad India",
    "Mananthavady, Wayanad India",
    "Pulpally, Wayanad India",
]

NO_WEBSITE_CSV_PATH = "/workspaces/Hermes-leads/resorts_wayanad_multi_area_leads.csv"
HAS_WEBSITE_CSV_PATH = "/workspaces/Hermes-leads/resorts_wayanad_multi_area_has_website_leads.csv"


async def run(areas=AREAS, target_leads=TARGET_LEADS):
    no_website_master = []
    has_website_master = []
    seen_no_website_urls = set()
    seen_has_website_urls = set()
    per_area_counts = {}

    for area in areas:
        remaining = target_leads - len(no_website_master)
        if remaining <= 0:
            print(f"\n✓ Target of {target_leads} already reached — skipping remaining areas: "
                  f"{areas[areas.index(area):]}\n")
            break

        print(f"\n{'#'*70}")
        print(f"# AREA: {area}  (need {remaining} more no-website leads to hit target)")
        print(f"{'#'*70}")

        no_website_leads, has_website_leads = await scrape_area(
            area, KEYWORD, target_leads=remaining, discovery_cap=DISCOVERY_CAP
        )

        new_no_website = 0
        for biz in no_website_leads:
            key = biz.get("maps_url") or biz["name"]
            if key in seen_no_website_urls:
                continue
            seen_no_website_urls.add(key)
            no_website_master.append(biz)
            new_no_website += 1

        new_has_website = 0
        for biz in has_website_leads:
            key = biz.get("maps_url") or biz["name"]
            if key in seen_has_website_urls:
                continue
            seen_has_website_urls.add(key)
            has_website_master.append(biz)
            new_has_website += 1

        per_area_counts[area] = (new_no_website, new_has_website)
        print(f"\n  ── Area '{area}' contributed {new_no_website} new no-website leads, "
              f"{new_has_website} new has-website leads "
              f"(running total: {len(no_website_master)}/{target_leads} no-website, "
              f"{len(has_website_master)} has-website)\n")

    write_leads_csv(no_website_master, NO_WEBSITE_CSV_PATH, has_website=False)
    write_leads_csv(has_website_master, HAS_WEBSITE_CSV_PATH, has_website=True)

    print(f"\n{'='*80}")
    print(f"MULTI-AREA SUMMARY")
    print(f"{'='*80}")
    for area, (nw, hw) in per_area_counts.items():
        print(f"  {area:<35} {nw} no-website | {hw} has-website")
    print(f"{'-'*80}")
    print(f"  TOTAL: {len(no_website_master)}/{target_leads} confirmed unique no-website leads")
    print(f"  TOTAL: {len(has_website_master)} confirmed unique has-website leads (bonus list)")
    if len(no_website_master) < target_leads:
        checked_all = list(per_area_counts.keys()) == list(areas)
        if checked_all:
            print(f"\n  ⚠ No-website target not reached after checking ALL {len(areas)} configured areas.")
            print(f"  This means {len(no_website_master)} is the real ceiling for this list of areas —")
            print(f"  add more areas to AREAS to search further, or accept this as the honest total.")
        else:
            print(f"\n  Target not reached but area list wasn't fully exhausted (stopped early).")
    else:
        print(f"\n  ✓ No-website target reached.")
    print(f"{'='*80}")
    print(f"\n✓ No-website CSV: {NO_WEBSITE_CSV_PATH}")
    print(f"✓ Has-website CSV: {HAS_WEBSITE_CSV_PATH}\n")

    return no_website_master, has_website_master


if __name__ == "__main__":
    asyncio.run(run())
