#!/usr/bin/env python3
"""
CableMap · Parse TeleGeography's public submarine‑cable JSON feed
and expose landing‑site metadata continent / country / city‑wise.

Copyright © 2025  Arun Singh. arunsingh.in@gmail.com
cablemap.py  ·  v1.1  (patched for TeleGeography v3 API)
Licence: MIT

"""

import json
import os
import sys
import time
import argparse
from pathlib import Path
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from typing import Dict, List, Tuple, Optional

CACHE_FILE = Path.home() / ".cache" / "cablemap.json"
CACHE_TTL  = 24 * 60 * 60                # 24 hrs

API_BASE          = "https://www.submarinecablemap.com/api/v3"
CABLE_GEO_URL     = f"{API_BASE}/cable/cable-geo.json"
LANDING_GEO_URL   = f"{API_BASE}/landing-point/landing-point-geo.json"

# ────────────────────────────────────────────────────────────────────────────────
# Helpers , patching helpers bug
# ────────────────────────────────────────────────────────────────────────────────

'''
Patching bug: Why the script broke
json.decoder.JSONDecodeError at line 1 means the file we just 
downloaded isn’t JSON at all (most often it’s an HTML “403/404/301” 
page or a blank response).
TeleGeography no longer serves the one‑file feed

TeleGeography no longer serves the one‑file feed
https://www.submarinecablemap.com/files/submarine‑cable‑map‑2024.json.
Instead the public site now exposes two separate v3 API endpoints

| what | URL |
|------|-----|
| Cable geometries | `https://www.submarinecablemap.com/api/v3/cable/cable-geo.json` |
| Landing‑point geometries | `https://www.submarinecablemap.com/api/v3/landing-point/landing-point-geo.json` |
'''
def _download_json(url:str)->Dict:
    req = Request(url, headers={"User-Agent":"CableMap/1.1"})
    with urlopen(req, timeout=30) as r:
        body = r.read()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"{url} did not return JSON") from None




def fetch_feed(force: bool = False) -> Dict:
    """
    Download & cache the *two* v3‑API geojson files,
    then combine them under one key so the rest of the
    script remains unchanged.
    Patch 3: 
    Load cached merged feed or download fresh copies of both geo‑json
    endpoints.  If the cache is missing OR older than CACHE_TTL OR
    unreadable, we fetch again.

    What I did:
    If the cache can’t be decoded, we log a warning, delete/overwrite it, 
    and continue. No more JSONDecodeError bubbling up to the CLI.
    """
    cache_ok = (
        CACHE_FILE.exists()
        and time.time() - CACHE_FILE.stat().st_mtime < CACHE_TTL
        and not force
    )
    if cache_ok:
        try:
            with CACHE_FILE.open("r") as fh:
                return json.load(fh)
        except (JSONDecodeError, OSError) as bad_cache:
            print("[WARN] cache unreadable – re‑downloading …")
            # fall through to fresh download

    # --- fresh download section ---
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading TeleGeography v3 geojson …")
    cable   = _download_json(CABLE_GEO_URL)
    landing = _download_json(LANDING_GEO_URL)
    merged  = {"objects": {"cables": cable, "landing_points": landing}}

    with CACHE_FILE.open("w") as fh:
        json.dump(merged, fh)

    return merged


def normalise(feed: Dict) -> Tuple[List[Dict], Dict[str, Dict]]:
    """
    Split feed into
        * cables   list[dict]
        * stations dict[name] -> {lat,lon,country,continent}
    """
    cables   = feed["objects"]["cables"]["features"]
    stations = feed["objects"]["landing_points"]["features"]
    station_map={}

    # TeleGeography provides landing points with 'name', 'id', 'coordinates'
    
    for f in stations:
        props=f["properties"]
        lon,lat=f["geometry"]["coordinates"]
        name   =props["name"]
        station_map[name]={
            "latitude":lat,
            "longitude":lon,
            "id":props["id"],
            "country":props.get("country_name","Unknown"),
            "continent":props.get("continent","Unknown"),
        }
    return cables, station_map


def build_index(cables: List[Dict], stations: Dict[str, Dict]) -> Dict[str, Dict]:
    """Return nested dict: continent → country → city → list[station‑info]"""
    idx=defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for name,info in stations.items():
        cont=info["continent"]; ctry=info["country"]; city=name.split(",")[0]
        idx[cont][ctry][city].append(info|{"name":name})
    return idx

# ────────────────────────────────────────────────────────────────────────────────
# Public façade
# ────────────────────────────────────────────────────────────────────────────────

class CableMap:
    """Library‑style API."""

    def __init__(self, force_refresh: bool = False):
        feed              = fetch_feed(force=force_refresh)
        self._cables, self._stations = normalise(feed)
        self._index       = build_index(self._cables, self._stations)

    # ‒‒‒query helpers‒‒‒
    def list_continents(self) -> List[str]:
        return sorted(self._index.keys())

    def list_countries(self, continent: Optional[str] = None) -> List[str]:
        if continent:
            return sorted(self._index.get(continent, {}).keys())
        countries = {c for cont in self._index.values() for c in cont.keys()}
        return sorted(countries)

    def list_cities(self, country: str) -> List[str]:
        for cont in self._index.values():
            if country in cont:
                return sorted(cont[country].keys())
        return []

    def landing_sites(self,
                      continent: Optional[str] = None,
                      country:   Optional[str] = None,
                      city:      Optional[str] = None
                     ) -> List[Dict]:
        """Return landing‑site dicts filtered by optional geography."""
        result: List[Dict] = []
        for cont_name, cont in self._index.items():
            if continent and continent != cont_name:
                continue
            for ctry_name, ctry in cont.items():
                if country and country != ctry_name:
                    continue
                for city_name, sites in ctry.items():
                    if city and city != city_name:
                        continue
                    result.extend(sites)
        return result

    # ‒‒‒pretty print‒‒‒
    def summary(self, continent=None, country=None, city=None):
        sites = self.landing_sites(continent, country, city)
        for s in sites:
            print(f"{s['name']:40}  "
                  f"{s['latitude']:>8.3f}, {s['longitude']:>8.3f}  "
                  f"{s['country']} / {s['continent']}")

# ────────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────────

def cli():
    parser = argparse.ArgumentParser(
        description="Query submarine‑cable landing sites by geography"
    )
    parser.add_argument("-c", "--continent", help="Filter by continent")
    parser.add_argument("-C", "--country",   help="Filter by country")
    parser.add_argument("-t", "--city",      help="Filter by city")
    parser.add_argument("--refresh", action="store_true",
                        help="Force‑download latest feed, bypass cache")
    parser.add_argument("--csv", metavar="FILE",
                        help="Write output as CSV instead of printing")
    args = parser.parse_args()

    cm = CableMap(force_refresh=args.refresh)
    sites = cm.landing_sites(args.continent, args.country, args.city)

    if args.csv:
        try:
            import csv
            with open(args.csv, "w", newline="", encoding="utf‑8") as fh:
                fieldnames = ["name", "latitude", "longitude", "country", "continent"]
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                for row in sites:
                    writer.writerow({k: row[k] for k in fieldnames})
            print(f"Wrote {len(sites)} rows to {args.csv}")
        except Exception as exc:
            print(f"Could not write CSV: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        if not sites:
            print("No landing sites found.")
        else:
            cm.summary(args.continent, args.country, args.city)

if __name__ == "__main__":
    cli()
