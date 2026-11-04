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
    # ---------------------------------------------------------------- batch 2 (research 4 Nov 2026)
    "surrey": {
        "label": "Surrey", "metro": "fraser", "hard_factor": 0.87,
        # FVREB MLS HPI Oct 2026 detached (B)
        "hpi_detached": {"North Surrey": 1254500, "Surrey Central": 1288000, "Cloverdale": 1326400, "South Surrey": 1606500, "Surrey City Centre": 1254500},
        "prices": {"Surrey City Centre": [620, 680, 800], "North Surrey": [600, 650, 750], "Surrey Central": [600, 650, 750],
                   "Cloverdale": [620, 660, 750], "South Surrey": [700, 750, 850]},   # (C) presale $650-850 condo, $550-700 TH
        "land_bsf": {"woodframe": 90, "midrise": 60, "tower": 50},   # (P) Guildford 104 Ave comp $90/bsf at 2.5 FAR
        # (A) DCC Bylaw 2026 (CR R098): SSMUH $51,633/lot + $17.21/sf additional building area; TH $27.15/sf; apt $30.72/sf (CC $24.31); high-rise $30.30 (CC $21.88)
        # (A) ACC (Jun 2026): SSMUH ~$11,669/lot + ~$11,000 per added unit; TH $6.83/sf; apt $10.58/sf. SSAC SD36 per unit.
        "fees": {"duplex": 51633 / 2 + 11669 / 2 + 12290 + 900, "multiplex": 51633 / 4 + 11669 / 4 + 10990 + 800, "townhouse": 800, "woodframe": 700, "midrise": 600, "tower": 600},
        "fees_per_sf": {"duplex": 17.21, "multiplex": 17.21, "townhouse": 27.15 + 6.83, "woodframe": 30.72 + 10.58, "midrise": 30.30 + 10.58, "tower": 30.30 + 10.58},
        "fees_per_sf_area": {"Surrey City Centre": {"woodframe": 24.31 + 10.58, "midrise": 21.88 + 10.58, "tower": 21.88 + 10.58}},
        "inclusionary_toa": 0.0,     # inclusionary zoning in TOAs phases in from July 2028 (5% of floor area)
        "grade_land": "C", "grade_zoning": "B",
    },
    "coquitlam": {
        "label": "Coquitlam", "metro": "fraser", "hard_factor": 0.95,
        # GVR HPI Oct 2026 detached $1,571,400 citywide; sub-areas (P/E)
        "hpi_detached": {"Coquitlam West": 1800000, "Central Coquitlam": 1614800, "Coquitlam East": 1500000, "Westwood Plateau": 1850000, "Burke Mountain": 1867100},
        "prices": {"Coquitlam West": [720, 950, 1000], "Central Coquitlam": [700, 900, 950], "Coquitlam East": [680, 850, 900],
                   "Westwood Plateau": [720, 850, 900], "Burke Mountain": [720, 850, 900]},   # (C)
        "land_bsf": {"woodframe": 140, "midrise": 90, "tower": 70},   # (E)
        # (A) DCC Bylaw 5411 per unit: SFD 64,396; duplex-multiplex 43,483; TH 38,537; apt 24,435. ACC: low-rise/SSMUH/TH $21,205/unit; apt <=12 fl $21.31/sf, >12 fl $38.53/sf. SSAC SD43.
        "fees": {"duplex": 43483 + 21205 + 900, "multiplex": 43483 + 21205 + 800, "townhouse": 38537 + 21205 + 800, "woodframe": 24435 + 700, "midrise": 24435 + 600, "tower": 24435 + 600},
        "fees_per_sf": {"woodframe": 21.31, "midrise": 21.31, "tower": 38.53},
        "inclusionary_toa": 0.0,     # density above base must be rental (modelled as strata at base density)
        "grade_land": "C", "grade_zoning": "A",
    },
    "portmoody": {
        "label": "Port Moody", "metro": "fraser", "hard_factor": 0.95,
        "hpi_detached": {"Port Moody": 1903500},   # GVR HPI Sep 2026 (B)
        "prices": {"Port Moody": [750, 900, 950], "Moody Centre": [780, 950, 1000]},   # (E)
        "land_bsf": {"woodframe": 140, "midrise": 80, "tower": 60},   # (E; city memo ~$95/bsf at 2.3 FAR)
        # (A) DCC Bylaw 3054/3478: SFD-duplex $34,893/unit; TH $149.98/m2; apt <=6 st $122.88/m2; >6 st $138.10/m2. ACC Bylaw 3551 (Jul 2026): low $15,633/lot, medium $11,218/unit, high $7,159/unit. SSAC SD43.
        "fees": {"duplex": 34893 + 11218 + 900, "multiplex": 34893 / 2 + 11218 + 800, "townhouse": 11218 + 800, "woodframe": 11218 + 700, "midrise": 7159 + 600, "tower": 7159 + 600},
        "fees_per_m2": {"townhouse": 149.98, "woodframe": 122.88, "midrise": 138.10, "tower": 138.10},
        "inclusionary_toa": 0.15,    # 2022 policy: >2.0 FAR -> 15% of residential floor area below-market rental (via rezoning)
        "grade_land": "C", "grade_zoning": "B",
    },
    "delta": {
        "label": "Delta", "metro": "fraser", "hard_factor": 0.90,
        "hpi_detached": {"North Delta": 1159600, "Ladner": 1284100, "Tsawwassen": 1508500},   # FVREB / GVR HPI Sep 2026 (B)
        "prices": {"North Delta": [600, 800, 850], "Ladner": [700, 850, 950], "Tsawwassen": [700, 850, 950]},   # (E)
        "land_bsf": {"woodframe": 100, "midrise": 70, "tower": 50},   # (E)
        # (P) DCC 2026 (+2.6%): SF $19,845; TH $13,524; apt $9,923 per unit. No ACC (PRCAC $1,000/unit on rezonings only). No SD37 SSAC found.
        "fees": {"duplex": 19845, "multiplex": 19845 / 2, "townhouse": 13524, "woodframe": 9923, "midrise": 9923, "tower": 9923},
        "inclusionary_toa": 0.0,
        "grade_land": "C", "grade_zoning": "B",
    },
    "westvan": {
        "label": "West Vancouver", "metro": "nshore", "hard_factor": 1.0,
        "hpi_detached": {"West Vancouver": 2822900},   # GVR HPI Sep 2026 (B)
        "prices": {"West Vancouver": [1200, 1350, 1500], "Ambleside": [1250, 1400, 1600]},   # (C) new condo asks $1,300-1,700/sf
        "land_bsf": {"woodframe": 400, "midrise": 300, "tower": 250},   # (E; 1802 Marine ~$450/bsf at 1.75 FAR)
        # (A) DWV DCC Bylaw 3801 "Other" area $9,197/unit; no ACC; no SD45 SSAC found
        "fees": {"duplex": 9197, "multiplex": 9197, "townhouse": 9197, "woodframe": 9197, "midrise": 9197, "tower": 9197},
        "inclusionary_toa": 0.0,
        "grade_land": "C", "grade_zoning": "A",
    },
    "langleycity": {
        "label": "Langley City", "metro": "fraser", "hard_factor": 0.87,
        "hpi_detached": {"Langley City": 1448100},   # FVREB HPI Oct 2026, Langley combined (B)
        "prices": {"Langley City": [600, 700, 780]},   # (E) Kamilia presale $660-800/sf
        "land_bsf": {"woodframe": 110, "midrise": 80, "tower": 60},   # (P) 53 Ave assembly $110/bsf at 2.1 FSR
        # (A) DCC Bylaw 3256 (2026) per unit: SF 45,563; TH/duplex 32,683; apt 21,246. Amenity policy CO-80 applies to rezonings only. SSAC SD35.
        "fees": {"duplex": 32683 + 900, "multiplex": 32683 + 800, "townhouse": 32683 + 800, "woodframe": 21246 + 700, "midrise": 21246 + 600, "tower": 21246 + 600},
        "inclusionary_toa": 0.025,   # TOA rezonings: 2.5% of net residential FAR below-market rental
        "grade_land": "C", "grade_zoning": "A",
    },
    "langleytwp": {
        "label": "Langley Township", "metro": "fraser", "hard_factor": 0.87,
        "hpi_detached": {"Langley Township": 1448100, "Willoughby": 1448100, "Brookswood": 1800000},   # FVREB combined (B); Brookswood large lots (E)
        "prices": {"Langley Township": [600, 650, 720], "Willoughby": [600, 660, 720], "Brookswood": [650, 650, 720]},   # (E)
        "land_bsf": {"woodframe": 100, "midrise": 70, "tower": 50},   # (E)
        # (A) DCC Bylaw 5897/6024: SF 86,787; ground-oriented MF 55,268; apt 38,482. (P) ACC: SF 19,571; GOMF 13,584; apt 8,634. SSAC SD35.
        "fees": {"duplex": 86787 + 19571 + 900, "multiplex": 55268 + 13584 + 800, "townhouse": 55268 + 13584 + 800, "woodframe": 38482 + 8634 + 700, "midrise": 38482 + 8634 + 600, "tower": 38482 + 8634 + 600},
        "inclusionary_toa": 0.10,    # Willoughby corridor bonus density: 10% of units at 20% below CMHC rent
        "grade_land": "C", "grade_zoning": "C",
    },
    "mapleridge": {
        "label": "Maple Ridge", "metro": "fraser", "hard_factor": 0.87,
        "hpi_detached": {"West Central": 978000, "East Central": 1067700, "Silver Valley": 1360200, "Albion": 1119100, "Cottonwood": 1215300, "Maple Ridge": 1138500},   # GVR HPI Sep/Oct 2026 (P)
        "prices": {"West Central": [525, 625, 650], "East Central": [525, 625, 650], "Silver Valley": [560, 625, 650], "Albion": [550, 625, 650], "Cottonwood": [550, 625, 650], "Maple Ridge": [525, 625, 650]},   # (E) presale median $567/sf
        "land_bsf": {"woodframe": 80, "midrise": 60, "tower": 50},   # (E)
        # (A) DCC Bylaw 7863-2022: SFD/duplex $41,011/unit; TH $241.37/m2; apt $235.96/m2 (>=6 st $191.81). CAC policy applies to rezonings; ACC from 2027. SSAC SD42.
        "fees": {"duplex": 41011 + 900, "multiplex": 41011 / 2 + 800, "townhouse": 800, "woodframe": 700, "midrise": 600, "tower": 600},
        "fees_per_m2": {"townhouse": 241.37, "woodframe": 235.96, "midrise": 191.81, "tower": 191.81},
        "inclusionary_toa": 0.0,
        "grade_land": "C", "grade_zoning": "C",
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
    if city == "dnv":
        return "North Vancouver"
    if city == "surrey":
        # City Centre within ~1.2 km of Gateway / Surrey Central / King George
        for la, lo in ((49.19891, -122.8506), (49.1895, -122.84787), (49.18273, -122.84458)):
            if abs(lat - la) < 0.011 and abs(lon - lo) < 0.017:
                return "Surrey City Centre"
        if lat < 49.07:
            return "South Surrey"
        if lon > -122.76 and lat < 49.15:
            return "Cloverdale"
        if lat > 49.16 and lon < -122.80:
            return "North Surrey"
        return "Surrey Central"
    if city == "coquitlam":
        if lon < -122.86:
            return "Coquitlam West"
        if lat > 49.30 and lon > -122.80:
            return "Burke Mountain"
        if lat > 49.29 and lon < -122.80:
            return "Westwood Plateau"
        if lon > -122.78:
            return "Coquitlam East"
        return "Central Coquitlam"
    if city == "portmoody":
        return "Moody Centre" if (station_dist_m is not None and station_dist_m <= 800) else "Port Moody"
    if city == "delta":
        if lat > 49.10:
            return "North Delta"
        return "Tsawwassen" if (lat < 49.04 and lon < -123.05) else "Ladner"
    if city == "westvan":
        return "Ambleside" if (lon > -123.17 and lat < 49.335) else "West Vancouver"
    if city == "langleycity":
        return "Langley City"
    if city == "langleytwp":
        n = (neighbourhood or "").lower()
        if "brookswood" in n or "fernridge" in n:
            return "Brookswood"
        if "willoughby" in n or (49.10 < lat < 49.17 and -122.70 < lon < -122.62):
            return "Willoughby"
        return "Langley Township"
    if city == "mapleridge":
        if lat > 49.245:
            return "Silver Valley"
        if lon > -122.54:
            return "Albion"
        if lon > -122.58:
            return "Cottonwood"
        return "East Central" if lon > -122.62 else "West Central"
    return next(iter(CITIES[city]["hpi_detached"]))


def burnaby_quadrant(lat, lon):
    ns = "N" if lat > 49.245 else "S"
    ew = "W" if lon < -122.97 else "E"
    return ns + ew
