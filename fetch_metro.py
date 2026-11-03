#!/usr/bin/env python3
"""
Download and assemble parcel tables for the inner-ring Metro Vancouver municipalities.

    python fetch_metro.py                 # all five cities
    python fetch_metro.py --city burnaby  # one city

Writes data/metro/<city>.csv with one row per fee-simple private parcel:
    city, pid, address, zone, overlay, zcat, ocp, site_m2, frontage_m, lat, lon,
    parcel_class, owner_type, strata, year_built, existing_fsr, neighbourhood, nearest_station,
    station_dist_m, station_kind, zoning_source
and data/metro/stations.json, data/metro/boundaries.json.

Sources (all open licences unless noted; see docs/metro_sources.md):
  ParcelMap BC parcel fabric (BC Data Catalogue WFS, OGL-BC)         -> geometry, PID, parcel class, owner type, area
  Burnaby Open Data: Legal Parcels (OpenData4/7), Zoning (OpenData1/8) -> address, strata flag, zone + overlay
  New Westminster Open Data: Properties, Zoning_, Building_Footprints2, Skytrain_Station_Pts
  City of North Vancouver ArcGIS (gisext2.cnv.org): Legal_Parcels (query_layers/2), zoning (query_layers/16), OCP (CityMapPro/27)
  District of North Vancouver GeoWeb: Zoning (Data_DynamicLayers_Zoning/0), OCP (Data_DynamicLayers_OCP/0)
  Richmond: no open zoning layer -> MountainMath / UBC Metro Vancouver Zoning Project aggregate (c. 2020), remapped to 2024-26 rules
"""
import argparse, csv, gzip, io, json, math, os, re, sys, time
import requests
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
from shapely import concave_hull
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "metro")
os.makedirs(OUT, exist_ok=True)
S = requests.Session()
S.headers["User-Agent"] = "vancouver-site-screener/1.0 (open-data research tool)"

PMBC = "https://openmaps.gov.bc.ca/geo/pub/ows"
PMBC_LAYER = "pub:WHSE_CADASTRE.PMBC_PARCEL_FABRIC_POLY_SVW"

CITIES = {
    "burnaby": dict(label="Burnaby", pmbc="Burnaby%",
                    zoning=dict(kind="arcgis", url="https://gis.burnaby.ca/arcgis/rest/services/OpenData/OpenData1/MapServer/8",
                                fields=["ZONECODE", "OVERLAY_ZONE", "CD_ZONE"]),
                    parcels_extra=dict(kind="arcgis", url="https://gis.burnaby.ca/arcgis/rest/services/OpenData/OpenData4/MapServer/7",
                                       fields=["LTO_PID", "ADDRESS", "STRATA", "AIR_SPACE", "LOT_AREA", "LOT_WIDTH"], geometry=False)),
    "richmond": dict(label="Richmond", pmbc="Richmond, City%",
                     zoning=dict(kind="mountainmath", url="https://s3.ca-central-1.amazonaws.com/mountainmath/cmhc/metro_van_zoning_aggregate.geojson.gz",
                                 muni="Richmond")),
    "newwest": dict(label="New Westminster", pmbc="New Westminster%",
                    base=dict(kind="arcgis", url="https://services3.arcgis.com/A7O8YnTNtzRPIn7T/arcgis/rest/services/Properties/FeatureServer/0",
                              where="FEATURETYPE='PARCEL' AND LEGAL_TYPE='LAND'",
                              fields=["PID", "ADDRESS", "ZONING", "ZONECAT", "OCP", "SITEAREA", "FRONTAGE", "FSR", "FLRSPCE", "NGBRHOOD", "LANDUSE", "LANDUSECAT", "GISLINK"]),
                    footprints=dict(kind="arcgis", url="https://services3.arcgis.com/A7O8YnTNtzRPIn7T/arcgis/rest/services/Building_Footprints2/FeatureServer/0",
                                    fields=["BLDGAGE", "NUM_RES", "STRATA"])),
    "cnv": dict(label="North Vancouver City", pmbc="North Vancouver%City%",
                zoning=dict(kind="arcgis", url="https://gisext2.cnv.org/arcgis/rest/services/BaseMapServices/query_layers/MapServer/16", fields=["ZONING"]),
                ocp=dict(kind="arcgis", url="https://gisext2.cnv.org/arcgis/rest/services/BaseMapServices/CityMapPro/MapServer/27", fields=["OCP_LU_CODE"]),
                parcels_extra=dict(kind="arcgis", url="https://gisext2.cnv.org/arcgis/rest/services/BaseMapServices/query_layers/MapServer/2",
                                   fields=["ADDRESS", "PRC_ROLL_NO", "AREA_M", "HRTG_DSGN", "PRCLTYPE"], geometry=True)),
    # DNV's GeoWeb dynamic layers answer attribute queries but withhold geometry, so they are read point-by-point
    # (one spatial query per parcel centroid, 8 in parallel, ~6 min for 26k parcels).
    "dnv": dict(label="North Vancouver District", pmbc="North Vancouver%District%",
                zoning=dict(kind="point", url="https://geoweb.dnv.org/arcgis/rest/services/Data_DynamicLayers_Zoning/MapServer/0", fields=["Zoning"]),
                ocp=dict(kind="point", url="https://geoweb.dnv.org/arcgis/rest/services/Data_DynamicLayers_OCP/MapServer/0", fields=["OCPClass"])),
}

# SkyTrain stations for the whole region come from New Westminster's open layer (52 points).
STATIONS_URL = "https://services3.arcgis.com/A7O8YnTNtzRPIn7T/arcgis/rest/services/Skytrain_Station_Pts/FeatureServer/0"
# Bus-exchange TOAs (B.C. Reg. 263/2023 schedule coordinates; 400 m radius, tiers 4/5)
BUS_TOAS = [
    {"station": "Lonsdale Quay Exchange", "lat": 49.310903, "lon": -123.082739, "kind": "bus", "city": "cnv"},
    {"station": "Phibbs Exchange", "lat": 49.305479, "lon": -123.028777, "kind": "bus", "city": "dnv"},
    {"station": "Capilano University Exchange", "lat": 49.319251, "lon": -123.018771, "kind": "bus", "city": "dnv"},
]
# Fallback SkyTrain list (Wikipedia geotags) used only if the New Westminster layer is unreachable.
STATIONS_FALLBACK = [
    ("Patterson", 49.22967, -123.012376), ("Metrotown", 49.225463, -123.003182), ("Royal Oak", 49.220004, -122.988381),
    ("Edmonds", 49.212054, -122.959226), ("Gilmore", 49.26489, -123.01351), ("Brentwood Town Centre", 49.26633, -123.00163),
    ("Holdom", 49.26469, -122.98222), ("Sperling-Burnaby Lake", 49.25914, -122.96391), ("Lake City Way", 49.25458, -122.93903),
    ("Production Way-University", 49.25337, -122.91815), ("Lougheed Town Centre", 49.24846, -122.89702),
    ("Rupert", 49.2609, -123.0329), ("Joyce-Collingwood", 49.2383, -123.0318), ("22nd Street", 49.199955, -122.948975),
    ("New Westminster", 49.201347, -122.912009), ("Columbia", 49.204489, -122.905916), ("Sapperton", 49.225301, -122.889654),
    ("Braid", 49.231547, -122.8829), ("Scott Road", 49.202912, -122.874946), ("Burquitlam", 49.2614, -122.89),
    ("Bridgeport", 49.19556, -123.12611), ("Capstan", 49.189254, -123.131677), ("Aberdeen", 49.18389, -123.13639),
    ("Lansdowne", 49.17472, -123.13639), ("Richmond-Brighouse", 49.16806, -123.13639), ("Marine Drive", 49.2096, -123.1168),
]


# ------------------------------------------------------------------ http helpers
def get(url, params=None, tries=4, timeout=600):
    last = None
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:  # noqa
            last = repr(e)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"GET failed {url}: {last}")


def arcgis_pages(url, fields, where="1=1", geometry=True, page=2000):
    """Yield GeoJSON features from an ArcGIS REST layer with resultOffset paging."""
    # honour the layer's own maxRecordCount
    try:
        info = get(url, params={"f": "pjson"}, timeout=120).json()
        page = min(page, int(info.get("maxRecordCount", page)) or page)
    except Exception:
        pass
    off = 0
    while True:
        p = {"where": where, "outFields": ",".join(fields), "f": "geojson", "outSR": 4326,
             "returnGeometry": "true" if geometry else "false", "resultOffset": off, "resultRecordCount": page}
        r = get(url + "/query", params=p)
        try:
            js = r.json()
        except Exception:
            raise RuntimeError(f"non-JSON from {url}: {r.text[:300]}")
        if "error" in js:
            raise RuntimeError(f"ArcGIS error from {url}: {js['error']}")
        feats = js.get("features", [])
        yield from feats
        if len(feats) < page or off > 400 * page:
            break
        off += len(feats)


def pmbc_pages(muni_like, count=5000):
    """Yield ParcelMap BC polygons (private, subdivision class) for one municipality as GeoJSON features."""
    start = 0
    cql = f"MUNICIPALITY LIKE '{muni_like}' AND PARCEL_CLASS='Subdivision'"
    while True:
        p = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": PMBC_LAYER,
             "outputFormat": "json", "srsName": "EPSG:4326", "count": count, "startIndex": start,
             "sortBy": "PARCEL_FABRIC_POLY_ID", "CQL_FILTER": cql}
        r = get(PMBC, params=p)
        js = r.json()
        feats = js.get("features", [])
        yield from feats
        if len(feats) < count:
            break
        start += count


def point_lookup(url, fields, points, workers=8):
    """Attribute lookup by point-in-polygon spatial query, one request per point (for layers that withhold geometry).
    points: list of (lon, lat). Returns list of attribute dicts (or None) in the same order."""
    from concurrent.futures import ThreadPoolExecutor
    sess = requests.Session()
    sess.headers.update(S.headers)

    def one(pt):
        lon, lat = pt
        p = {"geometry": f"{lon:.6f},{lat:.6f}", "geometryType": "esriGeometryPoint", "inSR": 4326,
             "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "false", "outFields": ",".join(fields), "f": "json"}
        for i in range(3):
            try:
                r = sess.get(url + "/query", params=p, timeout=60)
                if r.status_code == 200:
                    js = r.json()
                    if "error" in js:
                        return None
                    f = js.get("features") or []
                    return f[0].get("attributes") if f else {}
            except Exception:
                pass
            time.sleep(1 + i)
        return None

    out = [None] * len(points)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, res in enumerate(ex.map(one, points, chunksize=50)):
            out[i] = res
            if i and i % 5000 == 0:
                print(f"    point lookups: {i:,}/{len(points):,}", flush=True)
    return out


def feature_rows(feats, fields):
    for f in feats:
        pr = f.get("properties", {}) or {}
        yield {k: pr.get(k) for k in fields}, f.get("geometry")


# ------------------------------------------------------------------ spatial helpers
def build_tree(polys):
    geoms = [shape(g) for g in polys if g]
    return STRtree(geoms), geoms


def pip_lookup(tree, geoms, attrs):
    """Return function(lon, lat) -> attrs of the polygon containing the point (or None)."""
    def f(lon, lat):
        pt = Point(lon, lat)
        for i in tree.query(pt, predicate="within"):
            return attrs[int(i)]
        return None
    return f


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def geom_area_m2(geom):
    """Planar area of a lon/lat geometry via a local equirectangular projection (good to <0.1% at parcel scale)."""
    c = geom.centroid
    k = math.cos(math.radians(c.y))
    from shapely.ops import transform
    g2 = transform(lambda x, y, z=None: ((x - c.x) * 111320.0 * k, (y - c.y) * 110540.0), geom)
    return float(g2.area)


def norm_pid(p):
    s = re.sub(r"[^0-9]", "", str(p or ""))
    return s.zfill(9) if s else ""


# ------------------------------------------------------------------ stations
def load_stations():
    path = os.path.join(OUT, "stations.json")
    st = []
    try:
        for pr, g in feature_rows(arcgis_pages(STATIONS_URL, ["PL_NAME", "CITY"]), ["PL_NAME", "CITY"]):
            if g and g.get("type") == "Point":
                st.append({"station": pr["PL_NAME"], "lat": g["coordinates"][1], "lon": g["coordinates"][0], "kind": "skytrain"})
        print(f"  stations: {len(st)} SkyTrain points from New Westminster open data")
    except Exception as e:
        print("  stations: regional layer unavailable, using fallback list:", e)
        st = [{"station": n, "lat": la, "lon": lo, "kind": "skytrain"} for n, la, lo in STATIONS_FALLBACK]
    st += BUS_TOAS
    json.dump(st, open(path, "w"), indent=1)
    return st


def nearest_station(st, lat, lon):
    best = None
    for s in st:
        d = haversine(lat, lon, s["lat"], s["lon"])
        if best is None or d < best[1]:
            best = (s, d)
    return best


# ------------------------------------------------------------------ per-city assembly
def fetch_pmbc(city):
    cfg = CITIES[city]
    rows = []
    n = 0
    for pr, g in feature_rows(pmbc_pages(cfg["pmbc"]), ["PID", "PID_FORMATTED", "PARCEL_CLASS", "OWNER_TYPE", "FEATURE_AREA_SQM", "MUNICIPALITY", "PARCEL_NAME"]):
        n += 1
        if not g:
            continue
        geom = shape(g)
        c = geom.representative_point()
        rows.append(dict(pid=norm_pid(pr["PID"]), parcel_class=pr["PARCEL_CLASS"], owner_type=pr["OWNER_TYPE"],
                         site_m2=float(pr["FEATURE_AREA_SQM"] or 0), lon=c.x, lat=c.y, municipality=pr["MUNICIPALITY"],
                         frontage_m=None, _geom=geom))
    munis = sorted({r["municipality"] for r in rows})
    print(f"  PMBC {cfg['label']}: {n:,} subdivision parcels, municipality strings {munis}")
    return rows


def zoning_lookup(city):
    cfg = CITIES[city]
    z = cfg.get("zoning")
    if not z:
        return None, "none"
    if z["kind"] == "point":
        return "point", z["url"]
    attrs, polys = [], []
    if z["kind"] == "arcgis":
        for pr, g in feature_rows(arcgis_pages(z["url"], z["fields"]), z["fields"]):
            if g:
                attrs.append(pr); polys.append(g)
        src = z["url"]
    elif z["kind"] == "mountainmath":
        r = get(z["url"], timeout=900)
        raw = gzip.decompress(r.content) if r.content[:2] == b"\x1f\x8b" else r.content
        js = json.loads(raw)
        feats = js.get("features", [])
        keys = list((feats[0].get("properties") or {}).keys()) if feats else []
        print(f"  MountainMath zoning: {len(feats):,} features, keys {keys}")
        mkey = next((k for k in keys if any(z['muni'].lower() in str((f.get('properties') or {}).get(k, '')).lower() for f in feats)), None)
        zkey = next((k for k in keys if k.lower() in ("zone", "zoning", "z", "zone_code", "zoning_code", "zc_code")), None)
        if zkey is None:
            zkey = next((k for k in keys if "zon" in k.lower()), None)
        print(f"  MountainMath zoning: municipality key={mkey} zone key={zkey}")
        for f in feats:
            pr = f.get("properties") or {}
            if mkey and z["muni"].lower() not in str(pr.get(mkey, "")).lower():
                continue
            if f.get("geometry"):
                attrs.append({"ZONING": pr.get(zkey), "_all": {k: pr.get(k) for k in keys if k != "geometry"}}); polys.append(f["geometry"])
        src = "MountainMath/UBC Metro Vancouver Zoning Project (c.2020) " + z["url"]
    tree, geoms = build_tree(polys)
    print(f"  zoning polygons for {cfg['label']}: {len(geoms):,}")
    return pip_lookup(tree, geoms, attrs), src


def ocp_lookup(city):
    cfg = CITIES[city]
    o = cfg.get("ocp")
    if not o:
        return None
    if o["kind"] == "point":
        return "point"
    attrs, polys = [], []
    for pr, g in feature_rows(arcgis_pages(o["url"], o["fields"]), o["fields"]):
        if g:
            attrs.append(pr); polys.append(g)
    tree, geoms = build_tree(polys)
    print(f"  OCP polygons for {cfg['label']}: {len(geoms):,}")
    return pip_lookup(tree, geoms, attrs)


def assemble_city(city, stations):
    cfg = CITIES[city]
    print(f"== {cfg['label']}")
    rows = []
    if city == "newwest":
        base = cfg["base"]
        pm = {r["pid"]: r for r in fetch_pmbc(city)}
        fp_attrs, fp_polys = [], []
        try:
            for pr, g in feature_rows(arcgis_pages(cfg["footprints"]["url"], cfg["footprints"]["fields"]), cfg["footprints"]["fields"]):
                if g:
                    fp_attrs.append(pr); fp_polys.append(shape(g).representative_point())
        except Exception as e:
            print("  footprints unavailable:", e)
        parcels = []
        for pr, g in feature_rows(arcgis_pages(base["url"], base["fields"], where=base["where"]), base["fields"]):
            if not g:
                continue
            geom = shape(g); c = geom.representative_point()
            pid = norm_pid(pr["PID"])
            p = pm.get(pid, {})
            area = geom_area_m2(geom)
            site_area = float(pr["SITEAREA"] or 0)
            # SITEAREA/FRONTAGE/FSR are development-site level (several parcels can share one site); keep them only
            # when the site is this single parcel
            same_site = site_area > 0 and abs(site_area - area) / max(area, 1) < 0.15
            parcels.append(dict(city=city, pid=pid, address=(pr["ADDRESS"] or "").title(), zone=pr["ZONING"], overlay="", zcat=pr["ZONECAT"],
                                ocp=pr["OCP"], site_m2=area, frontage_m=(float(pr["FRONTAGE"] or 0) or None) if same_site else None,
                                lat=c.y, lon=c.x, parcel_class=p.get("parcel_class", "Subdivision"), owner_type=p.get("owner_type", "Unknown"),
                                strata=False, year_built=None, existing_fsr=(float(pr["FSR"] or 0) or None) if same_site else None, neighbourhood=(pr["NGBRHOOD"] or "").title(),
                                landuse=pr["LANDUSECAT"] or pr["LANDUSE"] or "", _geom=geom))
        # year built: oldest building footprint whose centroid falls in the parcel
        if fp_polys:
            tree = STRtree([pp["_geom"] for pp in parcels])
            for a, pt in zip(fp_attrs, fp_polys):
                for i in tree.query(pt, predicate="within"):
                    pp = parcels[int(i)]
                    y = a.get("BLDGAGE")
                    try:
                        y = int(float(y))
                    except Exception:
                        y = None
                    if y and 1850 < y < 2100:
                        pp["year_built"] = y if pp["year_built"] is None else min(pp["year_built"], y)
                    if str(a.get("STRATA", "")).upper().startswith("Y"):
                        pp["strata"] = True
        rows = parcels
        zsrc = "City of New Westminster Open Data: Properties layer (zoning attribute on parcel)"
    else:
        rows = fetch_pmbc(city)
        for r in rows:
            r.update(city=city, address="", zone=None, overlay="", zcat="", ocp="", strata=False, year_built=None,
                     existing_fsr=None, neighbourhood="", landuse="")
        zl, zsrc = zoning_lookup(city)
        if zl == "point":
            z = cfg["zoning"]
            print(f"  zoning by point query ({len(rows):,} parcels, 8 workers) ...", flush=True)
            res = point_lookup(z["url"], z["fields"], [(r["lon"], r["lat"]) for r in rows])
            zl = (lambda cache: (lambda lon, lat: cache.get((lon, lat))))({(r["lon"], r["lat"]): a for r, a in zip(rows, res) if a})
        if zl:
            miss = 0
            for r in rows:
                a = zl(r["lon"], r["lat"])
                if a is None:
                    miss += 1; continue
                if city == "burnaby":
                    r["zone"] = a.get("ZONECODE"); r["overlay"] = a.get("OVERLAY_ZONE") or ""; r["zcat"] = a.get("CD_ZONE") or ""
                elif city == "richmond":
                    r["zone"] = a.get("ZONING")
                    r["zcat"] = json.dumps(a.get("_all"))[:200]
                elif city == "cnv":
                    r["zone"] = a.get("ZONING")
                elif city == "dnv":
                    r["zone"] = a.get("Zoning")
            print(f"  zoning join: {len(rows) - miss:,} matched, {miss:,} unmatched")
        ol = ocp_lookup(city)
        if ol == "point":
            o = cfg["ocp"]
            print(f"  OCP by point query ({len(rows):,} parcels) ...", flush=True)
            res = point_lookup(o["url"], o["fields"], [(r["lon"], r["lat"]) for r in rows])
            cache = {(r["lon"], r["lat"]): a for r, a in zip(rows, res) if a}
            ol = lambda lon, lat: cache.get((lon, lat))
        if ol:
            for r in rows:
                a = ol(r["lon"], r["lat"])
                if a:
                    r["ocp"] = a.get("OCP_LU_CODE") or a.get("OCPClass") or ""
        ex = cfg.get("parcels_extra")
        if ex:
            try:
                if city == "burnaby":
                    bypid = {}
                    for pr, g in feature_rows(arcgis_pages(ex["url"], ex["fields"], geometry=False), ex["fields"]):
                        pid = norm_pid(pr["LTO_PID"])
                        if pid:
                            bypid[pid] = pr
                    hit = 0
                    for r in rows:
                        pr = bypid.get(r["pid"])
                        if pr:
                            hit += 1
                            r["address"] = (pr["ADDRESS"] or "").title()
                            r["strata"] = str(pr.get("STRATA") or "").strip().upper() in ("Y", "YES", "1", "TRUE")
                            try:
                                w = float(pr.get("LOT_WIDTH") or 0)
                                r["frontage_m"] = w * 0.3048 if w > 60 else (w if w > 0 else None)   # feet vs metres heuristic
                            except Exception:
                                pass
                    print(f"  Burnaby legal-parcel join: {hit:,} of {len(rows):,} matched on PID; strata flags {sum(r['strata'] for r in rows):,}")
                elif city == "cnv":
                    attrs, polys = [], []
                    for pr, g in feature_rows(arcgis_pages(ex["url"], ex["fields"]), ex["fields"]):
                        if g:
                            attrs.append(pr); polys.append(g)
                    tree, geoms = build_tree(polys)
                    lk = pip_lookup(tree, geoms, attrs)
                    hit = 0
                    for r in rows:
                        a = lk(r["lon"], r["lat"])
                        if a:
                            hit += 1
                            r["address"] = (a.get("ADDRESS") or "").title()
                            r["heritage"] = a.get("HRTG_DSGN") or ""
                    print(f"  CNV legal-parcel join: {hit:,} of {len(rows):,}")
            except Exception as e:
                print(f"  extra parcel attributes unavailable for {city}: {e}")
    # stations
    for r in rows:
        s, d = nearest_station(stations, r["lat"], r["lon"])
        r["nearest_station"] = s["station"]; r["station_dist_m"] = round(d); r["station_kind"] = s["kind"]
        r["zoning_source"] = zsrc
        if not r.get("frontage_m"):
            r["frontage_m"] = None
    # boundary for the dashboard map
    boundary = None
    if len(rows) >= 50:
        try:
            pts = [Point(r["lon"], r["lat"]) for r in rows]
            hull = concave_hull(unary_union(pts), ratio=0.08)
            b = hull.simplify(0.0008)
            if b.geom_type in ("Polygon", "MultiPolygon") and not b.is_empty:
                boundary = json.loads(json.dumps(b.__geo_interface__))
        except Exception as e:
            print("  boundary hull failed:", e)
    cols = ["city", "pid", "address", "zone", "overlay", "zcat", "ocp", "site_m2", "frontage_m", "lat", "lon", "parcel_class", "owner_type",
            "strata", "year_built", "existing_fsr", "neighbourhood", "landuse", "heritage", "nearest_station", "station_dist_m", "station_kind", "zoning_source"]
    path = os.path.join(OUT, f"{city}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r2 = {k: r.get(k) for k in cols}
            r2["lat"] = round(r["lat"], 6); r2["lon"] = round(r["lon"], 6); r2["site_m2"] = round(r["site_m2"], 1)
            w.writerow(r2)
    zones = {}
    for r in rows:
        zones[r["zone"]] = zones.get(r["zone"], 0) + 1
    top = sorted(zones.items(), key=lambda x: -x[1])[:25]
    print(f"  wrote {path}: {len(rows):,} parcels; top zones: {top}")
    return boundary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", action="append", choices=list(CITIES))
    a = ap.parse_args()
    cities = a.city or list(CITIES)
    stations = load_stations()
    bpath = os.path.join(OUT, "boundaries.json")
    bounds = json.load(open(bpath)) if os.path.exists(bpath) else {}
    failures = []
    for c in cities:
        try:
            b = assemble_city(c, stations)
            if b:
                bounds[c] = {"name": CITIES[c]["label"], "geometry": b}
        except Exception as e:
            import traceback; traceback.print_exc()
            failures.append((c, repr(e)))
            print(f"!! {c} failed: {e}")
    json.dump(bounds, open(bpath, "w"))
    if failures:
        print("FAILED:", failures)
    print("done")


if __name__ == "__main__":
    main()
