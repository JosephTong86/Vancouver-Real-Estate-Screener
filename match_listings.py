#!/usr/bin/env python3
"""
Turn a raw public-listings pull (data/listings_raw.csv) into data/listings.csv for score.py.

Matching strategy, in order:
  1. exact normalised address (civic number + street)  -> confidence "address"
  2. same civic number and street within 60 m of the parcel centroid (handles St/Ave/Blvd quirks) -> "address+geo"
Strata units (addresses starting with a unit number, "#", or containing " - ") are dropped: only fee-simple
parcels can be redeveloped by their buyer.

Input columns expected: type,address,postal,locality,price,floor_sf,lat,lon,url
"""
import os, re, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import norm_addr, haversine_m

raw_path = os.path.join(HERE, "data", "listings_raw.csv")
ls = pd.read_csv(raw_path, dtype=str).fillna("")
ls["price"] = pd.to_numeric(ls["price"], errors="coerce")
ls["lat"] = pd.to_numeric(ls["lat"], errors="coerce"); ls["lon"] = pd.to_numeric(ls["lon"], errors="coerce")

# drop strata / unit addresses
unit = ls["address"].str.match(r"^\s*(#|\d+\s*-\s*\d|unit|suite|th\s|ph\s)", case=False) | ls["address"].str.contains(r"\d\s*-\s*\d{2,}", regex=True)
ls = ls[~unit].copy()
ls["key"] = ls["address"].map(norm_addr)
ls["civic"] = ls["address"].str.extract(r"^\s*(\d+)")[0]

sc = pd.read_csv(os.path.join(HERE, "output", "all_scored.csv"), low_memory=False)
sc["key"] = sc["address"].map(norm_addr)
sc["civic"] = sc["address"].str.extract(r"^\s*(\d+)")[0]

# 1) exact key
m1 = ls.merge(sc[["key", "land_coordinate", "address", "lat", "lon"]], on="key", how="inner", suffixes=("", "_p"))
m1["confidence"] = "address"
# 2) civic + proximity
rest = ls[~ls["url"].isin(m1["url"])]
cand = rest.merge(sc[["civic", "land_coordinate", "address", "lat", "lon"]], on="civic", how="inner", suffixes=("", "_p"))
cand["d"] = haversine_m(cand["lat"], cand["lon"], cand["lat_p"], cand["lon_p"])
m2 = cand[cand["d"] <= 60].sort_values("d").drop_duplicates("url")
m2["confidence"] = "address+geo"
m = pd.concat([m1, m2], ignore_index=True)

out = m[["address_p", "price", "url", "type", "confidence", "land_coordinate"]].rename(columns={"address_p": "address", "price": "list_price"})
out = out.drop_duplicates("address")
out.to_csv(os.path.join(HERE, "data", "listings.csv"), index=False)
print(f"raw listings {len(pd.read_csv(raw_path)):,} -> fee-simple {len(ls):,} -> matched to parcels {len(out):,} "
      f"({(out.confidence=='address').sum()} exact, {(out.confidence=='address+geo').sum()} civic+geo)")
print(out["type"].value_counts().to_dict())
