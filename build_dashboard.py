#!/usr/bin/env python3
"""Build the self-contained dashboard (output/dashboard.html) from output/all_scored.csv."""
import json, os, math
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(HERE, "assumptions.json")))
aux = json.load(open(os.path.join(HERE, "data", "aux.json")))
summary = json.load(open(os.path.join(HERE, "output", "summary.json")))
df = pd.read_csv(os.path.join(HERE, "output", "all_scored.csv"), low_memory=False)

# rows worth showing: any site with a non-negative modelled margin, plus every top-100 row
keep = df[(df["oz_margin"] >= 0) | (df["rank_profit"] <= 100)].copy()
keep = keep.sort_values("oz_profit", ascending=False)

GROUP = {"duplex": "G", "multiplex": "G", "townhouse": "G", "woodframe": "W", "midrise": "C", "tower": "C"}

def r(x, d=0):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), d)

rows = []
for t in keep.itertuples(index=False):
    rows.append([
        t.address, t.postal if isinstance(t.postal, str) else "", t.local_area, t.zone,
        r(t.area_m2, 0), r(t.assessed_total), r(t.land_value), r(t.improvement_value),
        int(t.year_built) if not pd.isna(t.year_built) else None,
        r(t.oz_fsr, 2), t.oz_typology, GROUP.get(t.oz_typology, "W"), t.oz_tenure, int(t.oz_storeys) if not pd.isna(t.oz_storeys) else None,
        r(t.oz_gfa_sf), r(t.oz_units), r(t.oz_price_psf), r(t.oz_revenue), r(t.oz_acquisition), r(t.oz_hard), r(t.oz_soft), r(t.oz_levies),
        r(t.oz_total_cost), r(t.oz_profit), r(t.oz_margin, 4), r(t.oz_land_per_buildable), r(t.oz_rlv_at_target),
        t.nearest_station, r(t.station_dist_m), t.toa_tier if isinstance(t.toa_tier, str) else None, r(t.toa_fsr, 2), r(t.toa_profit), r(t.toa_margin, 4),
        bool(t.listed), r(t.list_price), t.listing_url if isinstance(t.listing_url, str) else "", r(t.ask_profit), r(t.ask_margin, 4),
        r(t.lat, 5), r(t.lon, 5), t.oz_zoning_note if isinstance(t.oz_zoning_note, str) else "", str(t.pid).split(";")[0].strip(),
        bool(t.likely_existing_apartment), int(t.stacked_parcels) if not pd.isna(t.stacked_parcels) else 1,
    ])
COLS = ["address","postal","area","zone","site_m2","assessed","land","improvement","year_built","fsr","typology","group","tenure","storeys",
        "gfa","units","price_psf","revenue","acquisition","hard","soft","levies","cost","profit","margin","land_psf_buildable","rlv",
        "station","station_m","toa_tier","toa_fsr","toa_profit","toa_margin","listed","list_price","listing_url","ask_profit","ask_margin","lat","lon","note","pid","existing_apt","stacked"]

# local-area outlines, simplified
areas = []
for a in aux["areas"]:
    polys = [a["coords"]] if a["type"] == "Polygon" else a["coords"]
    rings = []
    for pg in polys:
        ring = pg[0]
        step = max(1, len(ring) // 120)
        rings.append([[round(p[0], 4), round(p[1], 4)] for p in ring[::step]])
    areas.append({"name": a["name"], "rings": rings})
stations = [{"n": s["station"], "lat": round(s["lat"], 5), "lon": round(s["lon"], 5)} for s in aux["stations"] if s.get("lat")]

payload = {"cols": COLS, "rows": rows, "areas": areas, "stations": stations, "summary": summary,
           "assumptions": {
               "market_over_assessed": A["acquisition"]["market_over_assessed"],
               "target_margin": A["target_margin_on_cost"], "soft_pct": A["soft_cost_pct_of_hard"],
               "typologies": {k: {"hard": v["hard"], "eff": v["eff"], "label": v["label"]} for k, v in A["typologies"].items() if not k.startswith("_")},
               "prices": {k: v for k, v in A["prices_per_sf_saleable"].items() if not k.startswith("_")},
               "dcl": A["levies"]["dcl_per_sf"], "acc": A["levies"]["acc_per_sf"],
               "filters": A["candidate_filter"],
           },
           "generated": pd.Timestamp.now(tz="America/Vancouver").strftime("%B %d, %Y")}

tpl = open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read()
html = tpl.replace("/*__DATA__*/", "const DATA=" + json.dumps(payload, separators=(",", ":")) + ";")
out = os.path.join(HERE, "output", "dashboard.html")
open(out, "w", encoding="utf-8").write(html)
print(f"wrote {out}: {len(rows):,} rows, {os.path.getsize(out)/1e6:.1f} MB")
