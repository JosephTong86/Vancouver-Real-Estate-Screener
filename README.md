# Vancouver Redevelopment Screener

Finds the most profitable *pre-zoned* redevelopment sites in the City of Vancouver — parcels whose
current zoning already permits more floor area than what stands on them — and ranks them by a
residual-land-value pro forma. Produces a top-100 list (CSV/JSON) and a self-contained HTML dashboard.

## Quick start (Windows, miniconda / any Python 3.10+)

```bat
pip install pandas numpy requests
python fetch_data.py        # ~120 MB from opendata.vancouver.ca, 1-3 min
python score.py             # scores ~89,000 parcels in ~15 s
python build_dashboard.py   # writes output/dashboard.html (open in a browser)
```

Outputs land in `output/`:

| file | what |
|---|---|
| `top100.csv` / `top100.json` | the ranked list with the full pro forma per site |
| `all_scored.csv` | every scored parcel (~75k rows) — filter it however you like |
| `summary.json` | counts and top-100 composition |
| `dashboard.html` | interactive map + table + per-site pro forma |

## How a site is scored

1. **Zoning option** (`zoning_rules.py`): the densest for-sale building the district schedule permits
   outright/conditionally — R1-1 multiplex 1.0 FSR, RT, RM densities, C-2 family mixed-use 2.5–3.0,
   C-3A 3.0, and the Oct-2025 Broadway/Cambie R3 (2.0), R4 (4.0), R5 (5.0–6.0 with 20% social) districts.
   Minimum-site and frontage thresholds are applied (frontage estimated as area ÷ 37.2 m).
2. **Revenue** = site sf × FSR × efficiency × achievable 2026 $/sf by local area and building type.
3. **Costs** = acquisition (assessed × `market_over_assessed` + PTT + closing + demolition + carry) +
   hard + soft + City DCL + Amenity Cost Charge + Metro/TransLink DCCs + inclusionary obligations.
4. **Profit / margin on cost**, plus **max land price** (`oz_rlv_at_target`): the purchase price that
   still yields the target margin — the number to negotiate against.
5. **Ranking**: by profit among sites clearing `target_margin_on_cost`; `rank_margin` is also given.
6. **TOA upside** (`toa_*` columns): Bill 47 transit-oriented-area density (5.5 / 4.0 / 3.0 FSR by
   distance tier) as a separate, rezoning-required rental scenario.

Screened out: strata lots, tax-exempt parcels (parks/schools/churches/government), implausibly low
assessments (leasehold, co-op, partial interests), recent valuable buildings, likely existing apartment
buildings (rental replacement), and districts with no outright residential formula (CD-1, DD, industrial, HA).

## Tuning

Everything is in `assumptions.json`: prices per local area, hard costs per typology, soft %, levies,
acquisition premium, target margin and the candidate filters. Change a value, re-run `score.py` and
`build_dashboard.py`.

## Listings (REW.ca link-up)

```bat
pip install beautifulsoup4
python fetch_rew.py          # pulls active Vancouver houses / duplex / land / multi-family from REW's public search (~10 min)
python match_listings.py     # links them to parcels -> data/listings.csv
python score.py && python build_dashboard.py
```

Listed sites get a "Listed" tag, the asking price, the REW URL, and a second pro forma run at the asking
price (`ask_profit`, `ask_margin`). In the dashboard, the "Listed for sale only (priced at asking)" chip
switches the table and ranking to those numbers. REW throttles fast crawlers (HTTP 429, then a bot check);
the script paces itself and caches progress so a rerun resumes where it stopped.

The true MLS feed (Paragon / RESO Web API) is only available to licensed REALTORS and their vendors. If you
have that access, export a CSV instead and skip `fetch_rew.py`:

```
address,list_price,url
2518 W Broadway,16800000,https://...
```

Addresses are normalised (W/West, Ave/Avenue, etc.) and matched to the tax roll. Matched sites get
`listed=True`, `list_price` and the URL, and the dashboard's "Listed only" chip becomes useful.
`match_listings.py` expects the raw columns `type,address,postal,locality,price,floor_sf,lot_ft,lat,lon,url`; map an MLS export onto those (lat/lon optional) and save it as `data/listings_raw.csv`.

## Data sources

City of Vancouver Open Data (CC-BY 4.0): `property-tax-report` (2026 roll), `property-parcel-polygons`,
`rapid-transit-stations`, `local-area-boundary`. Zoning schedules, DCL/ACC/DCC rates and market inputs
current to September 2026 — see the dashboard's notes section for the specific numbers.

This is a screening tool, not an appraisal: assessments lag the market, frontage is estimated,
and heritage, view cones, soils, tenant relocation and financing structure are not modelled.

## Inner-ring municipalities (Burnaby, Richmond, New Westminster, North Vancouver City & District)

```
pip install shapely
python fetch_metro.py      # ParcelMap BC + each city's open zoning / parcel layers -> data/metro/<city>.csv
python score_metro.py      # same pro forma, city fee schedules, modelled land values -> output/metro/
python build_dashboard.py  # dashboard gains a View selector: region or one city
```

Outside Vancouver no assessed values are open data, so acquisition prices are **modelled** from the GVR HPI
benchmark and lot size (grade C) and every row carries a zoning-rule grade (A–D). Sources, rules and known gaps:
`docs/metro_sources.md`. Richmond has no open zoning layer; a c.2020 academic zoning map is remapped to the 2024 RSM
pre-zoning, so treat Richmond results as indicative.
