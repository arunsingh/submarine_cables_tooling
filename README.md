# submarine_cables_tooling

`
# 1. List all continents present in the feed
python cablemap.py | head -n 5          # prints all landing sites

# 2. All landing sites in Europe
python cablemap.py --continent Europe

# 3. Landing sites in India
python cablemap.py --country India

# 4. All Mumbai landing points, export to CSV
python cablemap.py --city Mumbai --csv mumbai_sites.csv

`