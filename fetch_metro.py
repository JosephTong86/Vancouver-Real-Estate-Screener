#!/usr/bin/env python3
"""
Download and assemble parcel tables for the Metro Vancouver municipalities outside the City of Vancouver.

    python fetch_metro.py                 # every city in CITIES
    python fetch_metro.py --city burnaby  # one city

Writes data/metro/<city>.csv with one row per fee-simple parcel:
    city, pid, address, zone, overlay, zcat, ocp, site_m2, frontage_m, lat, lon, parcel_class, owner_type, strata,
    year_built, existing_fsr, neighbourhood, landuse, heritage, ftn, flags, nearest_station, station_dist_m,
    station_kind, zoning_source
plus data/metro/stations.json and data/metro/boundaries.json.

Each city is a small config: a parcel BASE (ParcelMap BC by default, or the city's own parcel layer when it carries the
zoning code), a ZONING source (polygon layer joined by point-in-polygon, point-by-point queries for layers that withhold
geometry, or the MountainMath academic map for Richmond) and EXTRAS (attribute joins by PID / key, or spatial joins).
Sources and licences: docs/metro_sources.md.
"""
import argparse, csv, gzip, json, math, os, re, sys, time
import requests
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
from shapely import concave_hull
from shapely.ops import unary_union, transform

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from zoning_metro import TOA_KINDS   # noqa: E402
OUT = os.path.join(HERE, "data", "metro")
os.makedirs(OUT, exist_ok=True)
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (compatible; vancouver-site-screener/1.0; open-data research tool)"

PMBC = "https://openmaps.gov.bc.ca/geo/pub/ows"
PMBC_LAYER = "pub:WHSE_CADASTRE.PMBC_PARCEL_FABRIC_POLY_SVW"
SURREY = "https://gisservices.surrey.ca/arcgis/rest/services"
COQ = "https://geodata.coquitlam.ca/arcgis/rest/services/DynamicServices"
PMOODY = "https://services9.arcgis.com/XMHGoEc3tdJ8TphG/ArcGIS/rest/services"
DELTA = "https://services9.arcgis.com/w2mu7sRltY6PiQ7J/arcgis/rest/services"
DWV = "https://dwvmaps.westvancouver.ca/server/rest/services"
LCITY = "https://maps.langleycity.ca/server/rest/services/Maps/Open_Data/MapServer"
TOL = "https://mapsvr.tol.ca/arcgisext02/rest/services/GeoSource/DynamicServices/MapServer"
MRIDGE = "https://geoservices.mapleridge.ca/server/rest/services/DataCatalog"
ABBY = "https://services8.arcgis.com/ZYlQy38aWlfDG1Qh/arcgis/rest/services"
WHIS = "https://webmap.whistler.ca/server/rest/services"
CRD = "https://mapservices.crd.bc.ca/arcgis/rest/services/Properties/MapServer/2"
VIC = "https://maps.victoria.ca/server/rest/services/OpenData"
SAAN = "https://map.saanich.ca/server/rest/services/MAPS/SaanichMapService_External/MapServer"
ESQ = "https://gis.esquimalt.ca/arcgis/rest/services/Services"
LANG = "https://arcex.langford.ca/server/rest/services/Parcel_Info_Map/Parcel_Info_Webmap_EB/MapServer"
COLW = "https://services3.arcgis.com/MLf7r3NQY1Pb8feC/arcgis/rest/services"


def crd_base(jur_codes, label):
    """Capital Regional District regional lot fabric (PID, address, owner type) filtered to one BC Assessment jurisdiction."""
    codes = ",".join(f"'{c}'" for c in jur_codes)
    return dict(url=CRD, where=f"BCAJurisdiction IN ({codes}) AND ParcelClass='SUBDIVISION'", page=3000, skip_pmbc=True,
                fields=["PID", "FullAddress", "OwnerType", "ParcelClass", "BCAJurisdiction", "UnitNumber"],
                map=dict(pid="PID", address="FullAddress", owner_type_src="OwnerType", flags=[("UnitNumber", "strata_unit", "nonempty")]))

# ------------------------------------------------------------------ city configs
# base: None -> ParcelMap BC (pmbc LIKE pattern). Otherwise an ArcGIS layer with a field map:
#   map keys: pid, address, zone, site_m2, frontage_m, year_built, ocp, neighbourhood, landuse, strata, flags(list of (field, flagname, truthy))
# zoning: kind arcgis (polygon pip join) / point / mountainmath / None (zone comes from the base layer)
# extras: list of joins run after the base:
#   kind pid_join: ArcGIS layer with a PID field -> map attributes onto parcels with the same PID
#   kind key_join: ArcGIS layer joined on a key already on the parcel row (e.g. Surrey MSLINK)
#   kind pip: polygon/point layer, parcel centroid within polygon -> map attributes (or point layer: points within parcel)
CITIES = {
    "burnaby": dict(label="Burnaby", pmbc="Burnaby%",
                    zoning=dict(kind="arcgis", url="https://gis.burnaby.ca/arcgis/rest/services/OpenData/OpenData1/MapServer/8",
                                fields=["ZONECODE", "OVERLAY_ZONE", "CD_ZONE"], map=dict(zone="ZONECODE", overlay="OVERLAY_ZONE", zcat="CD_ZONE")),
                    extras=[dict(kind="pid_join", url="https://gis.burnaby.ca/arcgis/rest/services/OpenData/OpenData4/MapServer/7",
                                 fields=["LTO_PID", "ADDRESS", "STRATA", "LOT_WIDTH"], pid_field="LTO_PID",
                                 map=dict(address="ADDRESS", strata="STRATA", frontage_m="LOT_WIDTH"))]),
    "richmond": dict(label="Richmond", pmbc="Richmond, City%",
                     zoning=dict(kind="mountainmath", url="https://s3.ca-central-1.amazonaws.com/mountainmath/cmhc/metro_van_zoning_aggregate.geojson.gz", muni="Richmond")),
    "newwest": dict(label="New Westminster", pmbc="New Westminster%",
                    base=dict(url="https://services3.arcgis.com/A7O8YnTNtzRPIn7T/arcgis/rest/services/Properties/FeatureServer/0",
                              where="FEATURETYPE='PARCEL' AND LEGAL_TYPE='LAND'",
                              fields=["PID", "ADDRESS", "ZONING", "ZONECAT", "OCP", "SITEAREA", "FRONTAGE", "FSR", "NGBRHOOD", "LANDUSE", "LANDUSECAT"],
                              map=dict(pid="PID", address="ADDRESS", zone="ZONING", zcat="ZONECAT", ocp="OCP", site_area="SITEAREA",
                                       frontage_m="FRONTAGE", existing_fsr="FSR", neighbourhood="NGBRHOOD", landuse="LANDUSECAT")),
                    extras=[dict(kind="pip_points", url="https://services3.arcgis.com/A7O8YnTNtzRPIn7T/arcgis/rest/services/Building_Footprints2/FeatureServer/0",
                                 fields=["BLDGAGE", "STRATA"], map=dict(year_built="BLDGAGE", strata="STRATA"))]),
    "cnv": dict(label="North Vancouver City", pmbc="North Vancouver%City%",
                zoning=dict(kind="arcgis", url="https://gisext2.cnv.org/arcgis/rest/services/BaseMapServices/query_layers/MapServer/16", fields=["ZONING"], map=dict(zone="ZONING")),
                extras=[dict(kind="pip", url="https://gisext2.cnv.org/arcgis/rest/services/BaseMapServices/CityMapPro/MapServer/27", fields=["OCP_LU_CODE"], map=dict(ocp="OCP_LU_CODE")),
                        dict(kind="pip", url="https://gisext2.cnv.org/arcgis/rest/services/BaseMapServices/query_layers/MapServer/2",
                             fields=["ADDRESS", "HRTG_DSGN"], map=dict(address="ADDRESS", heritage="HRTG_DSGN"))]),
    # DNV GeoWeb dynamic layers withhold geometry: queried point by point (8 workers, ~6 min for 26k parcels)
    "dnv": dict(label="North Vancouver District", pmbc="North Vancouver%District%",
                zoning=dict(kind="point", url="https://geoweb.dnv.org/arcgis/rest/services/Data_DynamicLayers_Zoning/MapServer/0", fields=["Zoning"], map=dict(zone="Zoning")),
                extras=[dict(kind="point", url="https://geoweb.dnv.org/arcgis/rest/services/Data_DynamicLayers_OCP/MapServer/0", fields=["OCPClass"], map=dict(ocp="OCPClass"))]),
    # ---- batch 2
    "surrey": dict(label="Surrey", pmbc="Surrey, City%",
                   zoning=dict(kind="arcgis", url=SURREY + "/OpenData/MapServer/239", fields=["ZONING_TEXT", "ZONING", "BY_LAW_01"],
                               map=dict(zone="ZONING_TEXT", zcat="ZONING")),
                   extras=[dict(kind="pid_join", url=SURREY + "/Lots/MapServer/7", fields=["PID", "MSLINK", "PLAN_YR"], pid_field="PID",
                                map=dict(mslink="MSLINK"), page=5000, geometry=False),
                           dict(kind="key_join", url=SURREY + "/OpenData/MapServer/138", fields=["LOT_LINK", "HOUSE_NO", "GCROADS", "BUILDING_PERMIT_DATE"],
                                key_field="LOT_LINK", on="mslink", map=dict(address=("HOUSE_NO", "GCROADS")), geometry=False),
                           dict(kind="key_join", url=SURREY + "/Public/Planning/MapServer/64", fields=["MSLINK", "ELIGIBILITY"], key_field="MSLINK", on="mslink",
                                map=dict(ftn=("ELIGIBILITY", "flag")), geometry=False),
                           dict(kind="pip", url=SURREY + "/Public/Planning/MapServer/61", fields=["TOA_NAME", "TIER", "TOA_APPLICABILITY"], map=dict(toa_note="TOA_APPLICABILITY"))]),
    "coquitlam": dict(label="Coquitlam", pmbc="Coquitlam, City%",
                      zoning=dict(kind="arcgis", url=COQ + "/Planning/MapServer/1", fields=["ZONING", "DESCRIPTION"], map=dict(zone="ZONING", zcat="DESCRIPTION"), where="OBJECTID>0", page=1000),
                      extras=[dict(kind="pid_join", url=COQ + "/Cadastral/MapServer/15", fields=["PID", "ADDRESS"], pid_field="PID", map=dict(address="ADDRESS"), where="OBJECTID>0", page=10000, geometry=False)]),
    "portmoody": dict(label="Port Moody", pmbc="Port Moody%",
                      zoning=dict(kind="arcgis", url=PMOODY + "/Zoning/FeatureServer/3", fields=["zoning"], map=dict(zone="zoning")),
                      extras=[dict(kind="pid_join", url=PMOODY + "/Parcel_Information/FeatureServer/0", fields=["pid", "address", "legal_type"], pid_field="pid",
                                   map=dict(address="address", strata=("legal_type", "STRATA")), geometry=False),
                              dict(kind="pip", url=PMOODY + "/Provincial_Housing_Statutes_Mapping/FeatureServer/7", fields=["Bill44", "Bill44_UnitNumber_Numeric"],
                                   map=dict(ftn=("Bill44_UnitNumber_Numeric", "ge6")))]),
    "delta": dict(label="Delta", pmbc="Delta, City%",
                  base=dict(url=DELTA + "/Property_Parcels/FeatureServer/0", where="1=1",
                            fields=["PID", "CIVIC_ADDRESS", "ZONING", "OCPDES", "GRND_AREA", "ALR", "FLOODPLN", "SCOTTSDALE", "SSMUHUNITAREA", "HERITAGE_REG_CODE", "UNITNUM"],
                            map=dict(pid="PID", address="CIVIC_ADDRESS", zone="ZONING", ocp="OCPDES", heritage="HERITAGE_REG_CODE",
                                     ftn=("SSMUHUNITAREA", "nonempty"), flags=[("ALR", "alr", "Y"), ("FLOODPLN", "floodplain", "Y"), ("SCOTTSDALE", "scottsdale", "Y"), ("UNITNUM", "strata_unit", "nonempty")]))),
    # DWV's parcel service sits behind a Cloudflare challenge (HTTP 403 to non-browser clients, 4 Nov 2026): zoning comes from the
    # MountainMath aggregate (West Vancouver's RS / RD / RM map has barely changed since 2020); the DWV join is attempted for addresses
    "westvan": dict(label="West Vancouver", pmbc="West Vancouver%",
                    zoning=dict(kind="mountainmath", url="https://s3.ca-central-1.amazonaws.com/mountainmath/cmhc/metro_van_zoning_aggregate.geojson.gz", muni="West Vancouver"),
                    extras=[dict(kind="pid_join", url=DWV + "/Cadastral/PublishedService_ParcelsExternal/MapServer/0",
                                 fields=["PID", "ADDRESS", "ZONING_DESIGNATION", "LAND_USE_DESIGNATION", "DATE_BUILT", "ACTUAL_USE_DESC", "NEIGHBOURHOOD_DESC"], pid_field="PID",
                                 map=dict(address="ADDRESS", zone="ZONING_DESIGNATION", ocp="LAND_USE_DESIGNATION", year_built="DATE_BUILT",
                                          landuse="ACTUAL_USE_DESC", neighbourhood="NEIGHBOURHOOD_DESC"), geometry=False)]),
    "langleycity": dict(label="Langley City", pmbc="Langley, City%",
                        zoning=dict(kind="arcgis", url=LCITY + "/90", fields=["ZONING", "CD_NMBR"], map=dict(zone="ZONING", zcat="CD_NMBR")),
                        extras=[dict(kind="pip_points", url=LCITY + "/182", fields=["FULL_ADD"], map=dict(address="FULL_ADD"))]),
    "langleytwp": dict(label="Langley Township", pmbc="Langley, The%",
                       base=dict(url=TOL + "/3", where="1=1", fields=["PID", "Address", "Zoning", "ZoningDescr", "LOT_SIZE", "StatisticalAreaDescr", "UNIT"],
                                 map=dict(pid="PID", address="Address", zone="Zoning", zcat="ZoningDescr", neighbourhood="StatisticalAreaDescr", flags=[("UNIT", "strata_unit", "nonempty")]))),
    "mapleridge": dict(label="Maple Ridge", pmbc="Maple Ridge%",
                       zoning=dict(kind="arcgis", url=MRIDGE + "/PlanningDevelopment/MapServer/6", fields=["ZoningCode", "Category"], map=dict(zone="ZoningCode", zcat="Category")),
                       extras=[dict(kind="pip", url=MRIDGE + "/Property/MapServer/3", fields=["Address", "StreetName"], map=dict(address=("Address", "StreetName"))),
                               dict(kind="pip", url=MRIDGE + "/PlanningDevelopment/MapServer/5", fields=["OBJECTID"], map=dict(flags=[("OBJECTID", "urban_area", "nonempty")]))]),
    # ---- batch 3: Fraser Valley, Sea-to-Sky, Capital Region
    # Abbotsford's parcel layer carries zoning, OCP and the BC Assessment land / improvement values (grade A land values)
    "abbotsford": dict(label="Abbotsford", pmbc="Abbotsford%",
                       base=dict(url=ABBY + "/Parcel_Layers_External_Feature/FeatureServer/0", where="1=1",
                                 fields=["PID", "PROP_ADDRESS", "ZONING", "OCP_LandUse", "UDA", "ALR", "FLOODPLN", "LAND_VALUE", "IMP_VALUE", "TTL_VALUE", "USE_DESC", "HAP", "LUC"],
                                 map=dict(pid="PID", address="PROP_ADDRESS", zone="ZONING", ocp="OCP_LandUse", landuse="USE_DESC", heritage="HAP",
                                          land_value="LAND_VALUE", improvement_value="IMP_VALUE",
                                          flags=[("UDA", "urban_area", "Y"), ("ALR", "alr", "Y"), ("FLOODPLN", "floodplain", "Y"), ("LUC", "luc", "nonempty")]))),
    # Whistler's parcel layer carries the zone; SSMUH dwelling-count polygons give the 3/4-unit eligibility
    "whistler": dict(label="Whistler", pmbc="Whistler%",
                     base=dict(url=WHIS + "/ExternalVS/Parcels/MapServer/0", where="LegalDescription NOT LIKE 'STRATA LOT%'",
                               fields=["PID", "FOLIOADRSS", "ZONING1", "ZONETYPE1", "LegalDescription"],
                               map=dict(pid="PID", address="FOLIOADRSS", zone="ZONING1", zcat="ZONETYPE1")),
                     extras=[dict(kind="pip", url=WHIS + "/ExternalVS/Land_Use/MapServer/4", fields=["Source"],
                                  map=dict(flags=[("Source", "ssmuh4", "4 Dwelling Units"), ("Source", "ssmuh3", "3 Dwelling Units")]))]),
    "victoria": dict(label="Victoria", pmbc="Victoria, City%",
                     base=crd_base(["234"], "Victoria"),
                     zoning=dict(kind="arcgis", url=VIC + "/OpenData_PlanningAndDevelopment/MapServer/12", fields=["Zoning", "ZoningBylaw"], map=dict(zone="Zoning", zcat="ZoningBylaw")),
                     extras=[dict(kind="pid_join", url="https://services.arcgis.com/EHSKalEvBxdO9ljW/arcgis/rest/services/Property_Assessment_Report_2026/FeatureServer/0",
                                  fields=["PID", "land_gross", "impr_gross", "LEGAL_TYPE", "assess_abbreviation"], pid_field="PID", where="LEGAL_TYPE='LAND'",
                                  map=dict(land_value="land_gross", improvement_value="impr_gross", landuse="assess_abbreviation"), geometry=False),
                             dict(kind="pip", url=VIC + "/OpenData_PlanningAndDevelopment/MapServer/10", fields=["OBJECTID"], map=dict(flags=[("OBJECTID", "heritage", "nonempty")]))]),
    "saanich": dict(label="Saanich", pmbc="Saanich, The%",
                    base=crd_base(["308", "309", "389"], "Saanich"),
                    zoning=dict(kind="arcgis", url=SAAN + "/28", fields=["ZONINGTYPE", "ZONINGCLASSIFICATION"], map=dict(zone="ZONINGTYPE", zcat="ZONINGCLASSIFICATION"), page=3000),
                    extras=[dict(kind="pip", url=SAAN + "/128", fields=["OBJECTID"], map=dict(ftn=("OBJECTID", "nonempty")), page=3000),
                            dict(kind="pip", url=SAAN + "/11", fields=["OBJECTID"], map=dict(flags=[("OBJECTID", "urban_area", "nonempty")]), page=3000),
                            dict(kind="pip", url=SAAN + "/10", fields=["OBJECTID"], map=dict(flags=[("OBJECTID", "alr", "nonempty")]), page=3000),
                            dict(kind="pip", url=SAAN + "/134", fields=["LANDUSE"], map=dict(ocp="LANDUSE"), page=3000)]),
    # Oak Bay publishes no zoning layer: private lots are treated as RS (single-family) — the whole district outside the
    # Oak Bay Avenue / Estevan villages is zoned RS-1..RS-5 (zoning grade D)
    "oakbay": dict(label="Oak Bay", pmbc="Oak Bay%", base=crd_base(["317"], "Oak Bay"), assume_zone="RS"),
    "esquimalt": dict(label="Esquimalt", pmbc="Esquimalt%",
                      base=crd_base(["307"], "Esquimalt"),
                      zoning=dict(kind="arcgis", url=ESQ + "/Zoning/MapServer/0", fields=["Zone", "Zone_Description"], map=dict(zone="Zone", zcat="Zone_Description"), page=1000),
                      extras=[dict(kind="pid_join", url=ESQ + "/RSM/MapServer/0", fields=["PID"], pid_field="PID", map=dict(flags=[("PID", "rsm1", "nonempty")]), geometry=False)]),
    # Langford's parcel layer carries zoning and the BC Assessment values
    "langford": dict(label="Langford", pmbc="Langford%",
                     base=dict(url=LANG + "/10", where="1=1", fields=["PID", "Full_Address", "ZONE_ABR", "ZONE_DESC", "LandValue", "ImprovementsValue", "Parcel_Feature"],
                               map=dict(pid="PID", address="Full_Address", zone="ZONE_ABR", zcat="ZONE_DESC", land_value="LandValue", improvement_value="ImprovementsValue", landuse="Parcel_Feature")),
                     extras=[dict(kind="pip", url=LANG + "/30", fields=["OCP_DES"], map=dict(ocp="OCP_DES"))]),
    "colwood": dict(label="Colwood", pmbc="Colwood%",
                    base=dict(url=COLW + "/mapParcel/FeatureServer/0", where="ParcelType='SUBDIVISION'",
                              fields=["PID", "Address", "OwnerType", "Category", "SubCategory", "Neighbourhood"],
                              map=dict(pid="PID", address="Address", owner_type_src="OwnerType", landuse="SubCategory", neighbourhood="Neighbourhood")),
                    zoning=dict(kind="arcgis", url=COLW + "/mapZoning/FeatureServer/1", fields=["ZoneCode", "ZoneName"], map=dict(zone="ZoneCode", zcat="ZoneName"))),
    # View Royal publishes only a PDF zoning map: private lots are treated as R1 (zoning grade D)
    "viewroyal": dict(label="View Royal", pmbc="View Royal%", base=crd_base(["401", "402"], "View Royal"), assume_zone="R1"),
}

STATIONS_URL = "https://services3.arcgis.com/A7O8YnTNtzRPIn7T/arcgis/rest/services/Skytrain_Station_Pts/FeatureServer/0"
# Bus-exchange / commuter-rail TOAs (tiers 4-5, 400 m) and the Surrey-Langley SkyTrain stations (designated TOAs, opening 2029)
EXTRA_STATIONS = [
    {"station": "Lonsdale Quay Exchange", "lat": 49.310903, "lon": -123.082739, "kind": "bus"},
    {"station": "Phibbs Exchange", "lat": 49.305479, "lon": -123.028777, "kind": "bus"},
    {"station": "Capilano University Exchange", "lat": 49.319251, "lon": -123.018771, "kind": "bus"},
    {"station": "Scottsdale Exchange", "lat": 49.137542, "lon": -122.888144, "kind": "bus"},
    {"station": "Guildford Exchange", "lat": 49.1888, "lon": -122.8034, "kind": "bus"},
    {"station": "Newton Exchange", "lat": 49.1346, "lon": -122.8405, "kind": "bus"},
    {"station": "Langley Centre", "lat": 49.10639, "lon": -122.65444, "kind": "bus"},
    {"station": "Haney Place Exchange", "lat": 49.2195, "lon": -122.59709, "kind": "bus"},
    {"station": "Port Haney (WCE)", "lat": 49.21222, "lon": -122.605194, "kind": "bus"},
    {"station": "Maple Meadows (WCE)", "lat": 49.216528, "lon": -122.66611, "kind": "bus"},
    {"station": "Green Timbers (2029)", "lat": 49.1789, "lon": -122.8338, "kind": "skytrain"},
    {"station": "152 Street (2029)", "lat": 49.1668, "lon": -122.80245, "kind": "skytrain"},
    {"station": "Fleetwood (2029)", "lat": 49.1574, "lon": -122.7781, "kind": "skytrain"},
    {"station": "Bakerview-166 St (2029)", "lat": 49.15125, "lon": -122.7625, "kind": "skytrain"},
    {"station": "Hillcrest-184 St (2029)", "lat": 49.1296, "lon": -122.7138, "kind": "skytrain"},
    {"station": "Clayton (2029)", "lat": 49.122, "lon": -122.6969, "kind": "skytrain"},
    {"station": "Willowbrook (2029)", "lat": 49.11389, "lon": -122.67917, "kind": "skytrain"},
    {"station": "Langley City Centre (2029)", "lat": 49.10639, "lon": -122.65972, "kind": "skytrain"},
    # B.C. Reg. 263/2023 Schedule bus exchanges outside Metro Vancouver (Table 4-5 item 2: 3.5 / 2.5 FAR; Whistler item 3: 2.5 / 1.5)
    {"station": "Bourquin Exchange", "lat": 49.048239, "lon": -122.308918, "kind": "bus_bc"},
    {"station": "Gondola Exchange", "lat": 50.113152, "lon": -122.951658, "kind": "bus_whistler"},
    {"station": "Legislature Exchange", "lat": 48.418889, "lon": -123.368939, "kind": "bus_bc"},
    {"station": "Uptown Exchange", "lat": 48.455942, "lon": -123.377227, "kind": "bus_bc"},
    {"station": "Royal Oak Exchange", "lat": 48.499054, "lon": -123.388041, "kind": "bus_bc"},
    {"station": "UVic Exchange", "lat": 48.466114, "lon": -123.308532, "kind": "bus_bc"},
    {"station": "Colwood Exchange", "lat": 48.445168, "lon": -123.466447, "kind": "bus_bc"},
    {"station": "Langford Exchange", "lat": 48.445454, "lon": -123.505016, "kind": "bus_bc"},
    {"station": "VGH Exchange", "lat": 48.466224, "lon": -123.435007, "kind": "bus_bc"},
]
STATIONS_FALLBACK = [
    ("Patterson", 49.22967, -123.012376), ("Metrotown", 49.225463, -123.003182), ("Royal Oak", 49.220004, -122.988381),
    ("Edmonds", 49.212054, -122.959226), ("Gilmore", 49.26489, -123.01351), ("Brentwood Town Centre", 49.26633, -123.00163),
    ("Holdom", 49.26469, -122.98222), ("Sperling-Burnaby Lake", 49.25914, -122.96391), ("Lake City Way", 49.25458, -122.93903),
    ("Production Way-University", 49.25337, -122.91815), ("Lougheed Town Centre", 49.24846, -122.89702),
    ("Rupert", 49.2609, -123.0329), ("Joyce-Collingwood", 49.2383, -123.0318), ("22nd Street", 49.199955, -122.948975),
    ("New Westminster", 49.201347, -122.912009), ("Columbia", 49.204489, -122.905916), ("Sapperton", 49.225301, -122.889654),
    ("Braid", 49.231547, -122.8829), ("Scott Road", 49.204422, -122.874153), ("Gateway", 49.19891, -122.8506),
    ("Surrey Central", 49.1895, -122.84787), ("King George", 49.18273, -122.84458), ("Burquitlam", 49.26142, -122.889853),
    ("Moody Centre", 49.277954, -122.845593), ("Inlet Centre", 49.277293, -122.828164), ("Coquitlam Central", 49.274823, -122.800582),
    ("Lincoln", 49.28041, -122.793805), ("Lafarge Lake-Douglas", 49.285742, -122.791623),
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


def esri_to_geojson(geom):
    """Convert an Esri JSON geometry (rings / paths / x,y) to GeoJSON."""
    if not geom:
        return None
    if "rings" in geom:
        return {"type": "MultiPolygon", "coordinates": [[r] for r in geom["rings"]]}
    if "x" in geom:
        return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
    if "paths" in geom:
        return {"type": "MultiLineString", "coordinates": geom["paths"]}
    return None


def arcgis_pages(url, fields, where="1=1", geometry=True, page=2000):
    """Yield GeoJSON features from an ArcGIS REST layer with resultOffset paging (falls back to Esri JSON when the
    server does not serve GeoJSON geometry)."""
    try:
        info = get(url, params={"f": "pjson"}, timeout=120).json()
        page = min(page, int(info.get("maxRecordCount", page)) or page)
    except Exception:
        pass
    off, fmt, order, bad = 0, "geojson", None, 0
    while True:
        p = {"where": where, "outFields": ",".join(fields), "f": fmt, "outSR": 4326,
             "returnGeometry": "true" if geometry else "false", "resultOffset": off, "resultRecordCount": page}
        if order:
            p["orderByFields"] = order
        r = get(url + "/query", params=p)
        try:
            js = r.json()
        except Exception:
            js = {"error": f"non-JSON response: {r.text[:120]!r}"}
        if "error" in js:
            # old ArcGIS Servers (e.g. Esquimalt 10.9) fail offset paging in GeoJSON without an order; some sites answer a
            # maintenance page intermittently (Langley City): retry as Esri JSON ordered by OBJECTID, then back off
            bad += 1
            if bad == 1 and (fmt != "json" or not order):
                fmt, order = "json", "OBJECTID"
                continue
            if bad <= 4:
                time.sleep(10 * bad)
                continue
            raise RuntimeError(f"ArcGIS error from {url}: {js['error']}")
        bad = 0
        feats = js.get("features", [])
        if fmt == "geojson" and geometry and off == 0 and feats and all(f.get("geometry") is None for f in feats[:50]):
            fmt = "json"   # retry this page as Esri JSON
            continue
        if fmt == "json":
            feats = [{"type": "Feature", "properties": f.get("attributes", {}), "geometry": esri_to_geojson(f.get("geometry"))} for f in feats]
        yield from feats
        if len(feats) < page or off > 400 * page:
            break
        off += len(feats)


def pmbc_pages(muni_like, count=5000):
    """ParcelMap BC polygons (Subdivision class) for one municipality, as GeoJSON features."""
    start = 0
    cql = f"MUNICIPALITY LIKE '{muni_like}' AND PARCEL_CLASS='Subdivision'"
    while True:
        p = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": PMBC_LAYER, "outputFormat": "json",
             "srsName": "EPSG:4326", "count": count, "startIndex": start, "sortBy": "PARCEL_FABRIC_POLY_ID", "CQL_FILTER": cql}
        js = get(PMBC, params=p).json()
        feats = js.get("features", [])
        yield from feats
        if len(feats) < count:
            break
        start += count


def point_lookup(url, fields, points, workers=8):
    """One spatial query per point for layers that withhold geometry. Returns attribute dicts (or None) in order."""
    from concurrent.futures import ThreadPoolExecutor
    sess = requests.Session(); sess.headers.update(S.headers)

    def one(pt):
        lon, lat = pt
        p = {"geometry": f"{lon:.6f},{lat:.6f}", "geometryType": "esriGeometryPoint", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
             "returnGeometry": "false", "outFields": ",".join(fields), "f": "json"}
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


# ------------------------------------------------------------------ helpers
def build_tree(polys):
    geoms = [shape(g) for g in polys if g]
    return STRtree(geoms), geoms


def pip_lookup(tree, geoms, attrs):
    def f(lon, lat):
        for i in tree.query(Point(lon, lat), predicate="within"):
            return attrs[int(i)]
        return None
    return f


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def geom_area_m2(geom):
    c = geom.centroid
    k = math.cos(math.radians(c.y))
    g2 = transform(lambda x, y, z=None: ((x - c.x) * 111320.0 * k, (y - c.y) * 110540.0), geom)
    return float(g2.area)


def norm_pid(p):
    s = re.sub(r"[^0-9]", "", str(p or ""))
    return s.zfill(9) if s else ""


def truthy(v, mode):
    s = str(v if v is not None else "").strip()
    if mode == "nonempty":
        return s not in ("", "None", "null", "0")
    if mode == "flag":
        return s.upper() in ("Y", "YES", "TRUE", "1", "ELIGIBLE")
    if mode == "ge6":
        try:
            return float(s) >= 6
        except Exception:
            return False
    return s.upper() == str(mode).upper()


def apply_map(row, attrs, mp):
    """Copy mapped attributes from a source record onto a parcel row."""
    for k, spec in mp.items():
        if k == "flags":
            for field, flag, mode in spec:
                if truthy(attrs.get(field), mode):
                    row.setdefault("flags", set()).add(flag)
            continue
        if isinstance(spec, tuple):
            if k == "address":
                v = " ".join(str(attrs.get(f) or "").strip() for f in spec).strip()
                if v:
                    row["address"] = v.title()
            elif k in ("ftn", "strata"):
                row[k] = truthy(attrs.get(spec[0]), spec[1]) or bool(row.get(k))
            continue
        v = attrs.get(spec)
        if v is None or str(v).strip() in ("", "None"):
            continue
        if k == "address":
            row["address"] = str(v).title()
        elif k == "heritage":
            if str(v).strip().upper() not in ("N", "NO", "0", "FALSE", "NONE"):
                row["heritage"] = str(v).strip()
        elif k in ("land_value", "improvement_value"):
            try:
                row[k] = float(v)
            except Exception:
                pass
        elif k == "strata":
            row["strata"] = str(v).strip().upper() in ("Y", "YES", "1", "TRUE", "STRATA")
        elif k == "year_built":
            try:
                y = int(float(str(v)[:4]))
                if 1850 < y < 2100:
                    row["year_built"] = y if row.get("year_built") is None else min(row["year_built"], y)
            except Exception:
                pass
        elif k == "frontage_m":
            try:
                w = float(v)
                row["frontage_m"] = w * 0.3048 if w > 60 else (w if w > 0 else None)
            except Exception:
                pass
        elif k in ("site_area", "existing_fsr"):
            try:
                row[k] = float(v)
            except Exception:
                pass
        else:
            row[k] = str(v).strip()


# ------------------------------------------------------------------ stations
def load_stations():
    st = []
    try:
        for f in arcgis_pages(STATIONS_URL, ["PL_NAME", "CITY"]):
            g = f.get("geometry")
            if g and g.get("type") == "Point":
                st.append({"station": f["properties"]["PL_NAME"], "lat": g["coordinates"][1], "lon": g["coordinates"][0], "kind": "skytrain"})
        print(f"  stations: {len(st)} SkyTrain points from New Westminster open data")
    except Exception as e:
        print("  stations: regional layer unavailable, using fallback list:", e)
        st = [{"station": n, "lat": la, "lon": lo, "kind": "skytrain"} for n, la, lo in STATIONS_FALLBACK]
    seen = {(round(s["lat"], 3), round(s["lon"], 3)) for s in st}
    for s in EXTRA_STATIONS:
        if (round(s["lat"], 3), round(s["lon"], 3)) not in seen:
            st.append(dict(s))
    json.dump(st, open(os.path.join(OUT, "stations.json"), "w"), indent=1)
    return st


def nearest_station(st, lat, lon, kinds=("skytrain", "bus")):
    best = None
    for s in st:
        if s["kind"] not in kinds:
            continue
        d = haversine(lat, lon, s["lat"], s["lon"])
        if best is None or d < best[1]:
            best = (s, d)
    return best


# ------------------------------------------------------------------ parcel bases
def new_row(city):
    return dict(city=city, pid="", address="", zone="", overlay="", zcat="", ocp="", site_m2=0.0, frontage_m=None, lat=None, lon=None,
                parcel_class="Subdivision", owner_type="Unknown", strata=False, year_built=None, existing_fsr=None, neighbourhood="",
                landuse="", heritage="", ftn=False, flags=set(), mslink=None, land_value=None, improvement_value=None)


OWNER_NORM = {"PRIVATE": "Private", "MUNICIPAL": "Local Government", "LOCAL GOVERNMENT": "Local Government", "CROWN PROVINCIAL": "Crown Provincial",
              "CROWN FEDERAL": "Crown Federal", "CROWN AGENCY": "Crown Agency", "FIRST NATION": "First Nation", "MIXED OWNERSHIP": "Mixed Ownership"}


def fetch_pmbc(city, cfg):
    rows, n = [], 0
    for f in pmbc_pages(cfg["pmbc"]):
        n += 1
        g = f.get("geometry")
        if not g:
            continue
        pr = f.get("properties", {})
        geom = shape(g); c = geom.representative_point()
        r = new_row(city)
        r.update(pid=norm_pid(pr.get("PID")), parcel_class=pr.get("PARCEL_CLASS"), owner_type=pr.get("OWNER_TYPE"),
                 site_m2=float(pr.get("FEATURE_AREA_SQM") or 0), lon=c.x, lat=c.y, _geom=geom)
        rows.append(r)
    print(f"  PMBC {cfg['label']}: {n:,} subdivision parcels")
    return rows


def fetch_base(city, cfg):
    """City parcel layer as the base (carries zoning etc.); ParcelMap BC joined on PID for parcel class / owner type."""
    b = cfg["base"]
    pm = {}
    if not b.get("skip_pmbc"):
        try:
            pm = {r["pid"]: r for r in fetch_pmbc(city, cfg)}
        except Exception as e:
            print("  PMBC join unavailable:", e)
    rows = []
    for f in arcgis_pages(b["url"], b["fields"], where=b.get("where", "1=1"), page=b.get("page", 2000)):
        g = f.get("geometry")
        if not g:
            continue
        geom = shape(g); c = geom.representative_point()
        r = new_row(city)
        apply_map(r, f.get("properties", {}), b["map"])
        r["pid"] = norm_pid(r.get("pid"))
        area = geom_area_m2(geom)
        site_area = r.pop("site_area", 0) or 0
        same_site = site_area > 0 and abs(site_area - area) / max(area, 1) < 0.15
        if not same_site:
            r["frontage_m"] = None; r["existing_fsr"] = None
        p = pm.get(r["pid"], {})
        src_owner = str(r.pop("owner_type_src", "") or "").strip().upper()
        owner = p.get("owner_type") or OWNER_NORM.get(src_owner, src_owner.title() if src_owner else "Unknown")
        r.update(site_m2=area, lat=c.y, lon=c.x, parcel_class=p.get("parcel_class", "Subdivision"), owner_type=owner, _geom=geom)
        if "strata_unit" in r["flags"]:
            r["strata"] = True
        rows.append(r)
    # one row per polygon: drop duplicate footprints (strata lots drawn on the same parcel)
    seen, uniq = set(), []
    for r in rows:
        k = (round(r["lat"], 6), round(r["lon"], 6), round(r["site_m2"], 1))
        if k in seen:
            continue
        seen.add(k); uniq.append(r)
    print(f"  {cfg['label']} parcel layer: {len(rows):,} polygons, {len(uniq):,} unique sites; PMBC matched {sum(1 for r in uniq if r['pid'] in pm):,}")
    return uniq


# ------------------------------------------------------------------ zoning + extras
def join_zoning(city, cfg, rows):
    z = cfg.get("zoning")
    if not z:
        return cfg["base"]["url"] + " (zoning attribute on parcel)"
    attrs, polys = [], []
    if z["kind"] == "point":
        print(f"  zoning by point query ({len(rows):,} parcels, 8 workers) ...", flush=True)
        res = point_lookup(z["url"], z["fields"], [(r["lon"], r["lat"]) for r in rows])
        hit = 0
        for r, a in zip(rows, res):
            if a:
                apply_map(r, a, z["map"]); hit += 1
        print(f"  zoning point join: {hit:,} matched")
        return z["url"]
    if z["kind"] == "arcgis":
        for f in arcgis_pages(z["url"], z["fields"], where=z.get("where", "1=1"), page=z.get("page", 2000)):
            if f.get("geometry"):
                attrs.append(f.get("properties", {})); polys.append(f["geometry"])
        src = z["url"]
    elif z["kind"] == "mountainmath":
        r = get(z["url"], timeout=900)
        raw = gzip.decompress(r.content) if r.content[:2] == b"\x1f\x8b" else r.content
        feats = json.loads(raw).get("features", [])
        keys = list((feats[0].get("properties") or {}).keys()) if feats else []
        mkey = next((k for k in keys if any(z["muni"].lower() in str((f.get("properties") or {}).get(k, "")).lower() for f in feats)), None)
        zkey = next((k for k in keys if k.lower() in ("zone", "zoning", "z", "zone_code")), None) or next((k for k in keys if "zon" in k.lower()), None)
        print(f"  MountainMath zoning: {len(feats):,} features, keys {keys}, municipality key={mkey}, zone key={zkey}")
        for f in feats:
            pr = f.get("properties") or {}
            if mkey and z["muni"].lower() not in str(pr.get(mkey, "")).lower():
                continue
            if f.get("geometry"):
                attrs.append({"zone": pr.get(zkey)}); polys.append(f["geometry"])
        z = dict(z, map=dict(zone="zone"))
        src = "MountainMath/UBC Metro Vancouver Zoning Project (c.2020) " + z["url"]
    tree, geoms = build_tree(polys)
    lk = pip_lookup(tree, geoms, attrs)
    hit = 0
    for r in rows:
        a = lk(r["lon"], r["lat"])
        if a:
            apply_map(r, a, z["map"]); hit += 1
    print(f"  zoning polygons: {len(geoms):,}; join matched {hit:,} of {len(rows):,}")
    return src


def run_extra(city, cfg, rows, ex):
    kind = ex["kind"]
    if kind == "point":
        print(f"  {kind} lookup {ex['url'].split('/services/')[-1]} ({len(rows):,} parcels) ...", flush=True)
        res = point_lookup(ex["url"], ex["fields"], [(r["lon"], r["lat"]) for r in rows])
        hit = 0
        for r, a in zip(rows, res):
            if a:
                apply_map(r, a, ex["map"]); hit += 1
        print(f"    matched {hit:,}")
        return
    feats = list(arcgis_pages(ex["url"], ex["fields"], where=ex.get("where", "1=1"), geometry=ex.get("geometry", True), page=ex.get("page", 2000)))
    if kind == "pid_join":
        bypid = {}
        for f in feats:
            pr = f.get("properties", {})
            pid = norm_pid(pr.get(ex["pid_field"]))
            if pid and pid not in bypid:
                bypid[pid] = pr
        hit = 0
        for r in rows:
            pr = bypid.get(r["pid"])
            if pr:
                apply_map(r, pr, ex["map"]); hit += 1
        print(f"  pid join {ex['url'].split('/services/')[-1]}: {len(bypid):,} records, matched {hit:,} of {len(rows):,}")
    elif kind == "key_join":
        bykey = {}
        for f in feats:
            pr = f.get("properties", {})
            k = str(pr.get(ex["key_field"]) or "").strip()
            if k and k not in bykey:
                bykey[k] = pr
        hit = 0
        for r in rows:
            k = str(r.get(ex["on"]) or "").strip()
            pr = bykey.get(k) if k else None
            if pr:
                apply_map(r, pr, ex["map"]); hit += 1
        print(f"  key join {ex['url'].split('/services/')[-1]} on {ex['on']}: {len(bykey):,} records, matched {hit:,}")
    elif kind == "pip":
        attrs, polys = [], []
        for f in feats:
            if f.get("geometry"):
                attrs.append(f.get("properties", {})); polys.append(f["geometry"])
        tree, geoms = build_tree(polys)
        lk = pip_lookup(tree, geoms, attrs)
        hit = 0
        for r in rows:
            a = lk(r["lon"], r["lat"])
            if a:
                apply_map(r, a, ex["map"]); hit += 1
        print(f"  spatial join {ex['url'].split('/services/')[-1]}: {len(geoms):,} polygons, matched {hit:,}")
    elif kind == "pip_points":
        # points (addresses, building footprints as centroids) assigned to the parcel polygon containing them
        tree = STRtree([r["_geom"] for r in rows])
        hit = 0
        for f in feats:
            g = f.get("geometry")
            if not g:
                continue
            pt = shape(g)
            pt = pt if pt.geom_type == "Point" else pt.representative_point()
            for i in tree.query(pt, predicate="within"):
                apply_map(rows[int(i)], f.get("properties", {}), ex["map"]); hit += 1
                break
        print(f"  point-in-parcel join {ex['url'].split('/services/')[-1]}: {len(feats):,} points, {hit:,} assigned")


# ------------------------------------------------------------------ assembly
def assemble_city(city, stations):
    cfg = CITIES[city]
    print(f"== {cfg['label']}")
    if cfg.get("base"):
        try:
            rows = fetch_base(city, cfg)
        except Exception as e:
            if cfg["base"].get("optional"):
                print(f"  city parcel layer unavailable ({e}); falling back to ParcelMap BC without zoning")
                rows = fetch_pmbc(city, cfg)
            else:
                raise
    else:
        rows = fetch_pmbc(city, cfg)
    zsrc = "none"
    if rows:
        try:
            zsrc = join_zoning(city, cfg, rows)
        except Exception as e:
            print(f"  zoning join failed for {city}: {e}")
        if cfg.get("assume_zone"):
            n = 0
            for r in rows:
                if not r.get("zone") and r.get("owner_type") in ("Private", "Unknown") and 200 <= r["site_m2"] <= 4050:
                    r["zone"] = cfg["assume_zone"]; n += 1
            zsrc = f"assumed {cfg['assume_zone']} (no open zoning layer)"
            print(f"  zone assumed {cfg['assume_zone']} on {n:,} private lots")
        for ex in cfg.get("extras", []):
            try:
                run_extra(city, cfg, rows, ex)
            except Exception as e:
                print(f"  extra join failed ({ex['url']}): {e}")
    kinds = TOA_KINDS.get(city, ("skytrain", "bus"))
    for r in rows:
        best = nearest_station(stations, r["lat"], r["lon"], kinds) if kinds else None
        no_toa = best is None
        if no_toa:
            best = nearest_station(stations, r["lat"], r["lon"], kinds=tuple({s["kind"] for s in stations}))
        s, d = best
        r["nearest_station"] = s["station"]; r["station_dist_m"] = round(d); r["station_kind"] = "none" if no_toa else s["kind"]
        r["zoning_source"] = zsrc
        r["flags"] = ";".join(sorted(r["flags"])) if isinstance(r["flags"], set) else (r["flags"] or "")
    boundary = None
    if len(rows) >= 50:
        try:
            hull = concave_hull(unary_union([Point(r["lon"], r["lat"]) for r in rows]), ratio=0.08).simplify(0.0008)
            if hull.geom_type in ("Polygon", "MultiPolygon") and not hull.is_empty:
                boundary = json.loads(json.dumps(hull.__geo_interface__))
        except Exception as e:
            print("  boundary hull failed:", e)
    cols = ["city", "pid", "address", "zone", "overlay", "zcat", "ocp", "site_m2", "frontage_m", "lat", "lon", "parcel_class", "owner_type",
            "strata", "year_built", "existing_fsr", "neighbourhood", "landuse", "heritage", "ftn", "flags", "nearest_station", "station_dist_m",
            "station_kind", "zoning_source", "land_value", "improvement_value"]
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
    print(f"  wrote {path}: {len(rows):,} parcels; ftn {sum(1 for r in rows if r['ftn']):,}; top zones: {sorted(zones.items(), key=lambda x: -x[1])[:20]}")
    return boundary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", action="append", choices=list(CITIES))
    a = ap.parse_args()
    stations = load_stations()
    bpath = os.path.join(OUT, "boundaries.json")
    bounds = json.load(open(bpath)) if os.path.exists(bpath) else {}
    failures = []
    for c in (a.city or list(CITIES)):
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
