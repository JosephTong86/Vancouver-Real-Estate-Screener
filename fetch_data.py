#!/usr/bin/env python3
"""
Download the source data from the City of Vancouver Open Data portal into ./data.

    python fetch_data.py            # pulls everything (~120 MB download, 1-3 min)
    python fetch_data.py --year 2027

Datasets (all CC-BY 4.0, https://opendata.vancouver.ca):
  property-tax-report        BC Assessment values, zoning, address per legal parcel (fee-simple LAND only)
  property-parcel-polygons   parcel outlines -> site area (m2) + centroid
  rapid-transit-stations     SkyTrain station points (for Bill 47 TOA tiers)
  local-area-boundary        the 22 local planning areas (for neighbourhood pricing)
"""
import argparse, csv, io, json, math, os, sys
import requests

BASE = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
R = 6371000.0
LAT0 = math.radians(49.25)


def get(url, **kw):
    r = requests.get(url, timeout=600, **kw)
    r.raise_for_status()
    return r


def fetch_tax(year):
    sel = ("pid,land_coordinate,zoning_district,zoning_classification,from_civic_number,to_civic_number,"
           "street_name,property_postal_code,current_land_value,current_improvement_value,year_built,"
           "big_improvement_year,neighbourhood_code,legal_type")
    url = BASE + "property-tax-report/exports/csv"
    params = {"select": sel, "where": f"report_year={year} and legal_type='LAND'", "delimiter": ","}
    print("  property-tax-report ...", end="", flush=True)
    txt = get(url, params=params).text
    open(os.path.join(DATA, "tax_2026_land.csv"), "w", encoding="utf-8", newline="").write(txt)
    print(f" {txt.count(chr(10)):,} rows")
    params["select"] = "land_coordinate,tax_levy,neighbourhood_code"
    txt = get(url, params=params).text
    open(os.path.join(DATA, "tax_levy.csv"), "w", encoding="utf-8", newline="").write(txt)


def ring_area(ring):
    a = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % n]
        X1 = math.radians(x1) * R * math.cos(LAT0); Y1 = math.radians(y1) * R
        X2 = math.radians(x2) * R * math.cos(LAT0); Y2 = math.radians(y2) * R
        a += X1 * Y2 - X2 * Y1
    return abs(a) / 2


def poly_area(coords):
    a = ring_area(coords[0])
    for hole in coords[1:]:
        a -= ring_area(hole)
    return a


def fetch_parcels():
    print("  property-parcel-polygons (large geojson) ...", end="", flush=True)
    gj = get(BASE + "property-parcel-polygons/exports/geojson").json()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["tax_coord", "site_id", "civic_number", "streetname", "lat", "lon", "area_m2"])
    for f in gj["features"]:
        p, g = f["properties"], f.get("geometry")
        if not g:
            continue
        if g["type"] == "Polygon":
            a = poly_area(g["coordinates"])
        else:
            a = sum(poly_area(pg) for pg in g["coordinates"])
        c = p.get("geo_point_2d") or {}
        w.writerow([p.get("tax_coord") or "", p.get("site_id") or "", p.get("civic_number") or "",
                    (p.get("streetname") or "").replace(",", " "),
                    f"{c['lat']:.6f}" if c else "", f"{c['lon']:.6f}" if c else "", f"{a:.1f}"])
    open(os.path.join(DATA, "parcels.csv"), "w", encoding="utf-8", newline="").write(out.getvalue())
    print(f" {len(gj['features']):,} polygons")


def fetch_aux():
    print("  stations + local areas ...", end="", flush=True)
    st = get(BASE + "rapid-transit-stations/exports/json").json()
    la = get(BASE + "local-area-boundary/exports/geojson").json()
    aux = {
        "stations": [{"station": s["station"], "area": s.get("geo_local_area"),
                      "lat": (s.get("geo_point_2d") or {}).get("lat"), "lon": (s.get("geo_point_2d") or {}).get("lon")} for s in st],
        "areas": [{"name": f["properties"]["name"], "type": f["geometry"]["type"], "coords": f["geometry"]["coordinates"]}
                  for f in la["features"]],
    }
    json.dump(aux, open(os.path.join(DATA, "aux.json"), "w"))
    print(" ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="2026")
    args = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    print("Downloading City of Vancouver open data ->", DATA)
    fetch_tax(args.year)
    fetch_parcels()
    fetch_aux()
    print("Done. Now run: python score.py")
