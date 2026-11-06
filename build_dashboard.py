#!/usr/bin/env python3
"""Build the self-contained dashboard (output/dashboard.html) from output/all_scored.csv (Vancouver) and,
when present, output/metro/all_scored.csv (the other 22 municipalities scored by score_metro.py)."""
import json, os, math, re
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(HERE, "assumptions.json")))
aux = json.load(open(os.path.join(HERE, "data", "aux.json")))
summary = json.load(open(os.path.join(HERE, "output", "summary.json")))
df = pd.read_csv(os.path.join(HERE, "output", "all_scored.csv"), low_memory=False)

GROUP = {"duplex": "G", "multiplex": "G", "townhouse": "G", "woodframe": "W", "midrise": "C", "tower": "C"}
MAX_ROWS_PER_CITY = 1500


def r(x, d=0):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), d)


def s(x):
    return x if isinstance(x, str) else ""


def fam(city, zone):
    """Generic zoning family for the chip filter, across municipalities."""
    z = str(zone).upper()
    if city == "vancouver":
        if z.startswith("R1-"): return "R1"
        if z.startswith("RT"): return "RT"
        if z.startswith("RM"): return "RM"
        if re.match(r"^R[345]-", z): return "R345"
        if z.startswith("C-"): return "C"
        if z.startswith("RR"): return "RR"
        return "other"
    if city == "burnaby":
        if z == "R1" or re.match(r"^R[1-5]$|^R1[0-2]$", z): return "R1"
        if z in ("R2", "R2R", "RM1", "RM2"): return "RT"
        if z.startswith("C") or z.startswith("E1"): return "C"
        if z.endswith("R"): return "RR"
        return "RM"
    if city == "richmond":
        if z.startswith("RSM") or z.startswith("RS"): return "R1"
        if z.startswith(("RD", "RT", "RI", "RCD")): return "RT"
        if z.startswith(("CDT", "CS", "RCL", "CN")): return "C"
        return "RM"
    if city == "newwest":
        if z.startswith("RGO"): return "R1"
        if z.startswith("RT"): return "RT"
        if z.startswith("C-"): return "C"
        return "RM"
    if city == "cnv":
        if z == "GO": return "R1"
        if z.startswith("RG"): return "RT"
        if z.startswith(("C-", "LL")): return "C"
        return "RM"
    if city == "dnv":
        if z == "R2" or z.startswith("RS"): return "R1"
        if z.startswith("C"): return "C"
        return "RM"
    if city == "surrey":
        if re.match(r"^R[1-7]|^RA$|^R2O|^R5S", z): return "R1"
        if z in ("MR1", "MR2", "MR3", "MR4", "MR5", "RM70"): return "RT"
        if z.startswith("C") or z.endswith("C") or z == "MR10CBD": return "C"
        return "RM"
    if city == "coquitlam":
        if z.startswith(("R-1", "R-2", "R-3", "R-4", "RT-", "RS-")): return "R1" if z.startswith(("R-", "RS-")) else "RT"
        if z.startswith(("MU-", "C-")): return "C"
        if z == "RM-1": return "RT"
        return "RM"
    if city == "portmoody":
        if z.startswith("RS") or z == "RT": return "R1"
        if z in ("RM1", "RM2", "RM3", "RM4"): return "RT"
        if z.startswith(("C", "TC")): return "C"
        return "RM"
    if city == "delta":
        if z.startswith("RS") or z.startswith("RD"): return "R1"
        if z.startswith(("RT", "TH")): return "RT"
        if z.startswith(("MU", "C")): return "C"
        return "RM"
    if city == "westvan":
        if z.startswith("RD"): return "R1"
        if z.startswith("RG"): return "RT"
        if z.startswith(("AC", "C")): return "C"
        return "RM"
    if city == "langleycity":
        if z == "R1": return "R1"
        if z == "R2": return "RT"
        if z.startswith("C"): return "C"
        return "RM"
    if city == "langleytwp":
        if z.startswith(("SR-", "R-")): return "R1"
        if z in ("RM-1", "RM-2"): return "RT"
        if z.startswith("C"): return "C"
        return "RM"
    if city == "mapleridge":
        if z.startswith(("RS", "RUR", "SRS", "R-")): return "R1"
        if z.startswith(("RT", "RST")) or z in ("RM-1", "RM-4"): return "RT"
        if z.startswith(("C", "CRM")): return "C"
        return "RM"
    if city == "abbotsford":
        if z.startswith(("SSMUH", "RS", "SR", "RR")): return "R1"
        if z.startswith(("TH", "RMG", "RMR", "RMF", "RM1", "RM3", "RM4", "RM6")): return "RT"
        if z.startswith("C"): return "C"
        return "RM"
    if city == "whistler":
        if z.startswith(("RS", "RI", "RT")): return "R1"
        if z.startswith(("CC", "LC", "TA")): return "C"
        return "RM"
    if city in ("victoria", "saanich", "oakbay", "esquimalt", "langford", "colwood", "viewroyal"):
        if z.startswith(("R1", "R-2", "R2", "RS", "RD", "RSM", "R-K", "R-J", "R-N", "A-")): return "R1"
        if z.startswith(("RT", "GRD", "R3", "R4", "R5", "R6")) and city != "victoria": return "RT"
        if z.startswith(("GRD", "RT")): return "RT"
        if z.startswith(("C", "MU", "CC", "CA")): return "C"
        return "RM"
    return "other"


def row_from(t, city):
    """One dashboard row from a scored record (works for the Vancouver and metro tables)."""
    g = lambda k, d=None: getattr(t, k, d)
    assessed = g("assessed_total"); land = g("land_value"); imp = g("improvement_value")
    return [
        g("address"), s(g("postal", "")), g("local_area"), g("zone"),
        r(g("area_m2") if city == "vancouver" else g("site_m2"), 0), r(assessed), r(land), r(imp),
        int(g("year_built")) if not pd.isna(g("year_built", np.nan)) else None,
        r(g("oz_fsr"), 2), g("oz_typology"), GROUP.get(g("oz_typology"), "W"), g("oz_tenure"), int(g("oz_storeys")) if not pd.isna(g("oz_storeys", np.nan)) else None,
        r(g("oz_gfa_sf")), r(g("oz_units")), r(g("oz_price_psf")), r(g("oz_revenue")), r(g("oz_acquisition")), r(g("oz_hard")), r(g("oz_soft")), r(g("oz_levies")),
        r(g("oz_total_cost")), r(g("oz_profit")), r(g("oz_margin"), 4), r(g("oz_land_per_buildable")), r(g("oz_rlv_at_target")),
        g("nearest_station"), r(g("station_dist_m")), s(g("toa_tier")) or None, r(g("toa_fsr"), 2), r(g("toa_profit")), r(g("toa_margin"), 4),
        bool(g("listed", False)), r(g("list_price")), s(g("listing_url", "")), r(g("ask_profit")), r(g("ask_margin"), 4),
        r(g("lat"), 5), r(g("lon"), 5), s(g("oz_zoning_note", "")), str(g("pid")).split(";")[0].strip(),
        bool(g("likely_existing_apartment", False)), int(g("stacked_parcels")) if not pd.isna(g("stacked_parcels", np.nan)) else 1,
        city, s(g("oz_grade", "A")) or "A", s(g("oz_land_grade", "A")) or "A", fam(city, g("zone")),
    ]


COLS = ["address","postal","area","zone","site_m2","assessed","land","improvement","year_built","fsr","typology","group","tenure","storeys",
        "gfa","units","price_psf","revenue","acquisition","hard","soft","levies","cost","profit","margin","land_psf_buildable","rlv",
        "station","station_m","toa_tier","toa_fsr","toa_profit","toa_margin","listed","list_price","listing_url","ask_profit","ask_margin","lat","lon","note","pid","existing_apt","stacked",
        "city","grade","land_grade","fam"]

# ---- Vancouver rows: any site with a non-negative modelled margin, plus every top-100 row
keep = df[(df["oz_margin"] >= 0) | (df["rank_profit"] <= 100)].copy().sort_values("oz_profit", ascending=False)
rows = [row_from(t, "vancouver") for t in keep.itertuples(index=False)]
cities = [{"code": "vancouver", "label": "Vancouver", "parcels": int(summary["parcels_total"]), "scored": int(summary["parcels_scored"]),
           "clearing": int(summary["clearing_target"]), "rows": len(rows), "grade_land": "A", "grade_zoning": "A",
           "value_basis": "BC Assessment 2026 roll"}]

# ---- other municipalities
metro_path = os.path.join(HERE, "output", "metro", "all_scored.csv")
msum_path = os.path.join(HERE, "output", "metro_summary.json")
if os.path.exists(metro_path) and os.path.exists(msum_path):
    m = pd.read_csv(metro_path, low_memory=False, dtype={"pid": str})
    msum = json.load(open(msum_path))
    for code, cs in msum.items():
        sub = m[m["city"] == code].sort_values("oz_profit", ascending=False)
        sub = sub[(sub["oz_margin"] >= 0) | (sub["rank_profit"] <= 100)].head(MAX_ROWS_PER_CITY)
        n0 = len(rows)
        rows += [row_from(t, code) for t in sub.itertuples(index=False)]
        assessed = cs.get("parcels_assessed", 0) > cs["parcels_total"] * 0.5
        cities.append({"code": code, "label": cs["city"], "parcels": cs["parcels_total"], "scored": cs["parcels_scored"],
                       "clearing": cs["clearing_target"], "rows": len(rows) - n0, "grade_land": cs["grade_land"], "grade_zoning": cs["grade_zoning"],
                       "value_basis": "BC Assessment 2026 roll (city open data)" if assessed else "modelled from MLS HPI benchmark x lot size"})

# ---- outlines: Vancouver local areas + municipal hulls
areas = []
for a in aux["areas"]:
    polys = [a["coords"]] if a["type"] == "Polygon" else a["coords"]
    rings = []
    for pg in polys:
        ring = pg[0]
        step = max(1, len(ring) // 120)
        rings.append([[round(p[0], 4), round(p[1], 4)] for p in ring[::step]])
    areas.append({"name": a["name"], "rings": rings, "city": "vancouver"})
bpath = os.path.join(HERE, "data", "metro", "boundaries.json")
if os.path.exists(bpath):
    for code, b in json.load(open(bpath)).items():
        gm = b.get("geometry") or {}
        if gm.get("type") not in ("Polygon", "MultiPolygon") or not gm.get("coordinates"):
            continue
        polys = [gm["coordinates"]] if gm["type"] == "Polygon" else gm["coordinates"]
        rings = [[[round(p[0], 4), round(p[1], 4)] for p in pg[0]] for pg in polys if pg and len(pg[0]) >= 4]
        if rings:
            areas.append({"name": b["name"], "rings": rings, "city": code})

stations = [{"n": st["station"], "lat": round(st["lat"], 5), "lon": round(st["lon"], 5)} for st in aux["stations"] if st.get("lat")]
spath = os.path.join(HERE, "data", "metro", "stations.json")
if os.path.exists(spath):
    seen = {(round(x["lat"], 3), round(x["lon"], 3)) for x in stations}
    for st in json.load(open(spath)):
        k = (round(st["lat"], 3), round(st["lon"], 3))
        if k not in seen:
            stations.append({"n": st["station"], "lat": round(st["lat"], 5), "lon": round(st["lon"], 5), "kind": st.get("kind", "skytrain")}); seen.add(k)

payload = {"cols": COLS, "rows": rows, "areas": areas, "stations": stations, "summary": summary, "cities": cities,
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
# Leaflet: inline the vendored copy (vendor/leaflet.{js,css}, fetched in CI) so the page has no runtime CDN dependency;
# the CDN tags stay as the fallback when the vendored files are absent
vjs, vcss = os.path.join(HERE, "vendor", "leaflet.js"), os.path.join(HERE, "vendor", "leaflet.css")
if os.path.exists(vjs) and os.path.exists(vcss):
    css = open(vcss, encoding="utf-8").read()
    js = open(vjs, encoding="utf-8").read().replace("</script", "<\\/script")
    html = html.replace('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" crossorigin="">', "<style>" + css + "</style>")
    html = html.replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js" crossorigin=""></script>', "<script>" + js + "</script>")
    print("  leaflet inlined from vendor/")
out = os.path.join(HERE, "output", "dashboard.html")
open(out, "w", encoding="utf-8").write(html)
print(f"wrote {out}: {len(rows):,} rows across {len(cities)} municipalities, {os.path.getsize(out)/1e6:.1f} MB")
