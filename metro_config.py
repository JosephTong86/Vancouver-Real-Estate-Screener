"""
Per-municipality economics for the inner-ring screener (2026). Money in CAD.

Every number carries a grade (A bylaw/stat text, B secondary source, C derived/approximate, D placeholder).
Sources are listed in docs/metro_sources.md; research date 3 Nov 2026.

Land values are MODELLED, not assessed (BC Assessment values are only open data for the City of Vancouver):
    value = HPI_detached(sub-area) x (site_m2 / ref_m2) ^ 0.55
The 0.55 elasticity is fitted on Vancouver's 2026 assessment roll (R1-1 lots, within-neighbourhood regression,
n = 61,000; range 0.39-0.90 by neighbourhood). The September 2026 GVR MLS HPI benchmark detached price is used as
the value of a reference lot (the municipality's median detached lot). Multi-family / commercial zoned sites use
max(HPI model, land $/buildable sf x outright buildable area) because pre-zoned apartment land trades per buildable foot.
"""

# Metro Vancouver regional DCCs per unit after the 24 Jul 2026 rollback (sewer + water + parkland) + TransLink 2026
METRO_DCC = {
    "van":    {"townhouse": 19874, "apartment": 13392},
    "fraser": {"townhouse": 20296, "apartment": 14396},
    "nshore": {"townhouse": 19277, "apartment": 13099},
    "lulu":   {"townhouse": 15208, "apartment": 10610},
}
TRANSLINK = {"townhouse": 2837, "apartment": 1774}
PERMITS_MISC_PER_UNIT = 6000
LAND_ELASTICITY = 0.55

CITIES = {
    "burnaby": {
        "label": "Burnaby", "metro": "van", "hard_factor": 0.95,
        "hpi_detached": {"Burnaby North": 1808500, "Burnaby South": 1894600, "Burnaby East": 1694900},   # GVR HPI Sep 2026 (B)
        "prices": {  # achievable 2026 strata $/sf [ground-oriented, wood-frame apt, concrete] (C: resale $904/sf median; presale est.)
            "Burnaby North": [980, 1000, 1080], "Burnaby South": [1000, 1020, 1100], "Burnaby East": [900, 950, 1000]},
        "land_bsf": {"woodframe": 180, "midrise": 110, "tower": 70},     # (D) $/buildable sf for pre-zoned apartment land
        "fees": {  # (A) DCC Bylaw 14645 + ACC Bylaw 14646, per unit; SSAC SD41 per unit
            "duplex": 54870 + 26963 + 900, "multiplex": 37423 + 18874 + 800, "townhouse": 37423 + 18874 + 800,
            "woodframe": 25360 + 13481 + 700, "midrise": 25360 + 13481 + 600, "tower": 25360 + 13481 + 600},
        "inclusionary_toa": 0.10,     # R5-R8 / rezonings: 10% NW & SW, 5% NE & SE below-market rental units
        "grade_land": "C", "grade_zoning": "B",
    },
    "richmond": {
        "label": "Richmond", "metro": "lulu", "hard_factor": 0.95,
        "hpi_detached": {"Richmond": 1871100, "Richmond City Centre": 1871100},   # GVR HPI Sep 2026 (B)
        "prices": {"Richmond": [950, 780, 950], "Richmond City Centre": [1000, 850, 1080]},   # (C)
        "land_bsf": {"woodframe": 170, "midrise": 120, "tower": 90},   # (D)
        # (A) DCC Bylaw 9499 as amended: TH $33.79/sf, apt $35.79/sf, SSMUH $33.65/sf (Bylaw 10732, adoption pending), SF $63,767/lot;
        # ACC: none in force (proposal defeated Mar 2026). SSAC SD38 per unit.
        "fees_per_sf": {"duplex": 33.65, "multiplex": 33.65, "townhouse": 33.79, "woodframe": 35.79, "midrise": 35.79, "tower": 35.79},
        "fees": {"duplex": 900, "multiplex": 800, "townhouse": 800, "woodframe": 700, "midrise": 600, "tower": 600},
        "inclusionary_toa": 0.15,     # LEMR 15% of floor area in City Centre rezonings >60 units (10% elsewhere)
        "grade_land": "C", "grade_zoning": "C",   # zoning polygons are c.2020 (MountainMath) remapped to the 2024 RSM pre-zoning
    },
    "newwest": {
        "label": "New Westminster", "metro": "fraser", "hard_factor": 0.95,
        "hpi_detached": {"New Westminster": 1356900, "Queensborough": 1250000},   # GVR HPI Sep 2026 (B); Queensborough (C)
        "prices": {"New Westminster": [760, 800, 900], "Downtown": [780, 850, 950], "Queensborough": [700, 750, 850]},   # (C)
        "land_bsf": {"woodframe": 130, "midrise": 90, "tower": 60},   # (D; one 2026 comp at ~$154/bsf)
        # (A) DCC Bylaw 8327/8539 per m2 GFA: TH $105.04, apt $142.72 (Queensborough 137.49 / 156.32); ACC Bylaw 8540 per m2 GFA: TH $240.56, apt $330.32
        "fees_per_m2": {"duplex": 105.04 + 240.56, "multiplex": 105.04 + 240.56, "townhouse": 105.04 + 240.56,
                        "woodframe": 142.72 + 330.32, "midrise": 142.72 + 330.32, "tower": 142.72 + 330.32},
        "fees_per_m2_queensborough": {"duplex": 137.49 + 240.56, "multiplex": 137.49 + 240.56, "townhouse": 137.49 + 240.56,
                                      "woodframe": 156.32 + 330.32, "midrise": 156.32 + 330.32, "tower": 156.32 + 330.32},
        "fees": {"duplex": 896, "multiplex": 800, "townhouse": 800, "woodframe": 700, "midrise": 560, "tower": 560},   # SSAC SD40
        "inclusionary_toa": 0.10,     # Inclusionary Housing Policy (Dec 2025): 10% of units below-market on rezonings
        "grade_land": "C", "grade_zoning": "A",
    },
    "cnv": {
        "label": "North Vancouver City", "metro": "nshore", "hard_factor": 0.95,
        "hpi_detached": {"North Vancouver": 2042000},   # GVR HPI Sep 2026, City + District combined (B)
        "prices": {"North Vancouver": [1000, 1060, 1280], "Lonsdale": [1050, 1150, 1350]},   # (C)
        "land_bsf": {"woodframe": 200, "midrise": 150, "tower": 120},   # (D; 705 W 3rd 2024 at $237/bsf)
        # (A) DCC Bylaw 8471 as amended Nov 2025 per unit: TH/duplex $14,884, apt $12,593, apt 5+ st $10,304; no ACC; no SD44 SSAC found
        "fees": {"duplex": 14884, "multiplex": 14884, "townhouse": 14884, "woodframe": 12593, "midrise": 10304, "tower": 10304},
        "inclusionary_toa": 0.10,
        "grade_land": "C", "grade_zoning": "A",
    },
    "dnv": {
        "label": "North Vancouver District", "metro": "nshore", "hard_factor": 0.95,
        "hpi_detached": {"North Vancouver": 2042000},   # (B) combined HPI
        "prices": {"North Vancouver": [1050, 1030, 1000]},   # (C) new house + coach product ~$1,000-1,100/sf
        "land_bsf": {"woodframe": 180, "midrise": 120, "tower": 90},   # (D)
        # (B) DCC (Dec 2024) + ACC (Feb 2025) per unit: SF 43,533 + 41,358; TH 27,644 + 37,221; apt 19,625 + 26,193; coach house DCC 75% of apt, ACC exempt
        "fees": {"duplex": 43533 + 41358 + 14719, "multiplex": 27644 + 37221, "townhouse": 27644 + 37221,
                 "woodframe": 19625 + 26193, "midrise": 19625 + 26193, "tower": 19625 + 26193},
        "inclusionary_toa": 0.0,
        "grade_land": "C", "grade_zoning": "A",
    },
}


def sub_area(city, lat, lon, neighbourhood="", station_dist_m=None, zone=""):
    """Pricing / HPI sub-area for a parcel (coarse, documented approximations)."""
    if city == "burnaby":
        if lon > -122.925:
            return "Burnaby East"
        return "Burnaby North" if lat > 49.245 else "Burnaby South"
    if city == "richmond":
        return "Richmond City Centre" if (station_dist_m is not None and station_dist_m <= 1200) else "Richmond"
    if city == "newwest":
        n = (neighbourhood or "").lower()
        if "queensborough" in n or lat < 49.19:
            return "Queensborough"
        if "downtown" in n or str(zone).upper().startswith(("C-3", "C-4", "C-5", "C-6", "C-8")):
            return "Downtown"
        return "New Westminster"
    if city == "cnv":
        return "Lonsdale" if abs(lon + 123.073) < 0.006 else "North Vancouver"
    return "North Vancouver"


def burnaby_quadrant(lat, lon):
    ns = "N" if lat > 49.245 else "S"
    ew = "W" if lon < -122.97 else "E"
    return ns + ew
