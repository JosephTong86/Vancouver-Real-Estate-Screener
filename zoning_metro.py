"""
Outright (no-rezoning) residential redevelopment rules for the inner-ring Metro Vancouver municipalities.

rule_for(city, zone, site_m2, frontage_m, ctx) -> dict(fsr, typology, storeys, tenure, note, incl, grade, units) or None

ctx keys: overlay (Burnaby R overlay on a C base), ocp (CNV OCP_LU_CODE / DNV OCPClass), ftn (within 400 m of a
15-minute bus stop, when known), toa_tier (1..5 or None), quadrant (Burnaby NW/NE/SW/SE), zcat (New West ZONECAT).

Grades say how well the number is pinned down: A = read from the consolidated bylaw text, B = bylaw or city
bulletin via secondary summary, C = derived (e.g. Burnaby's height-based districts have no FSR, so floor area is
built up storey by storey from coverage / floorplate caps), D = placeholder flagged for verification.

Sources: see docs/metro_sources.md (research compiled 3 Nov 2026). Everything site-specific (CD / Z-zones)
returns None: those lots have already been rezoned for a specific project and are not a "pre-zoned" opportunity.
"""
import re

SQFT = 10.7639


def _o(fsr, typology, storeys, note="", tenure="strata", incl=None, grade="B", units=None):
    return {"fsr": round(fsr, 3), "typology": typology, "storeys": storeys, "tenure": tenure, "note": note,
            "incl": incl, "grade": grade, "units": units}


def _ssmuh_units(site_m2, ftn):
    if site_m2 <= 280:
        return 3
    return 6 if ftn else 4


# ------------------------------------------------------------------ Burnaby (Zoning Bylaw 2026, No. 14815; in force 1 Jul 2026)
# Height-based districts: no FAR. Floor area is derived storey by storey:
#   storeys 1-6: 55% of site (setbacks 3.0 m front/rear, 1.2 m side on a typical lot), capped at 1,400 m2 plate
#   storeys 7-12: 45% (3.0 m step-back above the 6th storey), capped at 1,400 m2
#   storeys 13+: capped at 900 m2 residential floorplate (Part 4 s.3.3.2)
# Tower separation (25 m face-to-face above 12 storeys) makes towers implausible below ~1,800 m2; mid-rise below ~1,100 m2.
BBY_BASE = {"R2": 4, "R3": 4, "R4": 6, "R5": 12, "R6": 20, "R7": 30, "R8": 40}


def _burnaby_gfa(site_m2, storeys):
    gfa = 0.0
    for s in range(1, storeys + 1):
        if s <= 6:
            gfa += min(site_m2 * 0.55, 1400)
        elif s <= 12:
            gfa += min(site_m2 * 0.45, 1400)
        else:
            gfa += min(site_m2 * 0.35, 900)   # point tower above a podium: ~35% coverage, 900 m2 plate cap
    return min(gfa, site_m2 * 10.0)          # cap at FSR 10 (Metrotown/Brentwood towers run ~8-12)


def _burnaby(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    overlay = (ctx.get("overlay") or "").upper().replace(" ", "")
    rental = z.endswith("R") and z[:-1] in BBY_BASE
    base = z[:-1] if rental else z
    if base in ("C1", "C2", "E1") and overlay[:2] in BBY_BASE:
        # commercial base with residential overlay: height follows the overlay district, ground floor commercial
        o = _burnaby(overlay, site_m2, frontage_m, dict(ctx, overlay=""))
        if o:
            o["note"] = f"{z} base + {overlay} residential overlay: " + o["note"] + "; >=60% of ground floor commercial"
            o["mixed_use"] = True
            if base == "E1":
                o["tenure"] = "rental"
        return o
    if base == "R1":
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        # Oct 2025 amendments: 3 storeys / 10 m, coverage 40% (<=567 m2) else 30% for 1-2 units, 45% for 5-6 units.
        cov = 0.45 if n >= 5 else 0.40
        fsr = min(3 * cov * 0.85, 1.05)   # three storeys at coverage, upper floors ~85% of the ground floor
        if site_m2 < 281 and n > 3:
            n = 3
        return _o(fsr, "multiplex", 3, f"R1 SSMUH {n} units; no FAR, coverage {int(cov*100)}% x 3 storeys (Oct 2025 cut)", grade="C", units=n)
    if base == "R2":
        # 4-storey townhouse district: ~45% coverage x 4 storeys less stacking/garage losses
        return _o(1.3, "townhouse", 4, "R2 townhouse/rowhouse up to 4 storeys outright; no FAR (derived 1.3)", tenure="rental" if rental else "strata", grade="C")
    if base in BBY_BASE:
        st = BBY_BASE[base]
        if base == "R4" and ctx.get("toa_tier"):
            st = 8
        # plausibility by site size for tall forms (building separation rules)
        if st > 12 and site_m2 < 1800:
            st = 12
        if st > 6 and site_m2 < 1100:
            st = 6
        gfa = _burnaby_gfa(site_m2, st)
        fsr = gfa / site_m2
        typ = "woodframe" if st <= 6 else ("midrise" if st <= 12 else "tower")
        incl = None
        if base in ("R5", "R6", "R7", "R8"):
            share = 0.10 if ctx.get("quadrant") in ("NW", "SW") else 0.05
            incl = f"share_belowmarket:{share}"
        note = f"{z}: {st} storeys outright (base {BBY_BASE[base]}); floor area from coverage/floorplate caps"
        if st != BBY_BASE[base]:
            note += " (site too small for full height)"
        return _o(fsr, typ, st, note, tenure="rental" if rental else "strata", incl=incl, grade="C")
    # legacy 1965-bylaw codes, in case the open-data layer still carries them
    if re.match(r"^R[1-5]$|^R1[0-2]$", z):
        return _burnaby("R1", site_m2, frontage_m, ctx)
    if z in ("RM1", "RM2"):
        return _burnaby("R2", site_m2, frontage_m, ctx)
    if z == "RM3":
        return _burnaby("R3", site_m2, frontage_m, ctx)
    if z in ("RM4", "RM5"):
        return _burnaby("R5", site_m2, frontage_m, ctx)
    if z.startswith("RM6"):
        return _burnaby("R6", site_m2, frontage_m, ctx)
    return None


# ------------------------------------------------------------------ Richmond (Zoning Bylaw 8500; RSM pre-zoning June 2024)
def _rsm_fsr(site_m2):
    first = min(site_m2, 464.5)
    return (0.60 * first + 0.30 * max(0.0, site_m2 - 464.5) + 50.0) / site_m2


def _richmond(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    toa = bool(ctx.get("toa_tier"))
    if z.startswith("RSM") or re.match(r"^RS[12]/?[A-K]?$", z) or z.startswith("RS1") or z.startswith("RS2"):
        if toa and not z.startswith("RSM"):
            return None   # lots inside the 800 m TOA rings kept their RS zoning: single-detached only
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        fsr = _rsm_fsr(site_m2)
        # RSM units may not be stratified (s.8.19.9) and added units are rental by covenant -> rental tenure
        return _o(fsr, "multiplex", 2.5, f"RSM {n} units; FSR 0.6 to 464.5 m2 + 0.3 balance + 50 m2; units cannot be stratified", tenure="rental", grade="B", units=n)
    if z.startswith("RD") or z == "RCD":
        fsr = (0.55 * min(site_m2, 929) + 0.30 * max(0, site_m2 - 929)) / site_m2
        return _o(fsr, "duplex", 2.5, "RD duplex (2 strata units); 4 units outright but added units rental", grade="B", units=2)
    m = re.match(r"^RTL([1-4])$", z)
    if m:
        f = {1: 0.55, 2: 0.55, 3: 0.60, 4: 0.60}[int(m.group(1))] + 0.10
        return _o(f, "townhouse", 3 if int(m.group(1)) >= 3 else 2, f"{z} townhouse; base + former 0.1 amenity bonus folded in (Bylaw 10760)", grade="B")
    m = re.match(r"^RTM([1-4])$", z)
    if m:
        f = (0.65 if m.group(1) == "2" else 0.70) + 0.10
        return _o(f, "townhouse", 3, f"{z} townhouse 12 m", grade="B")
    m = re.match(r"^RTH([1-4])$", z)
    if m:
        f = {1: 0.75, 2: 0.80, 3: 0.85, 4: 0.90}[int(m.group(1))] + 0.10
        return _o(f, "townhouse", 3, f"{z} high-density townhouse", grade="B")
    if z == "RTP4":
        return _o(1.3, "townhouse", 4, "RTP4 townhouse over parking; min site 2,400 m2", grade="B") if site_m2 >= 2400 else None
    if z.startswith("RI"):
        return _o(0.65, "townhouse", 3, "RI infill (coach house / townhouse); min 312 m2", grade="B") if site_m2 >= 312 else None
    if z == "RAL1":
        return _o(1.0, "woodframe", 3, "RAL1 low-rise apartment 12 m; 0.8 + 0.2 former bonuses", grade="B")
    if z == "RAM1":
        if site_m2 < 2400 and toa:
            return None
        f = (0.6 * min(site_m2, 3000) + 0.9 * max(0, min(site_m2, 9000) - 3000) + 1.2 * max(0, site_m2 - 9000)) / site_m2 + 0.2
        return _o(f, "woodframe", 4, "RAM1 low-rise 15 m, density steps with site size", grade="B")
    if z in ("RAH1", "RAH2"):
        if site_m2 < 2400:
            return None
        return _o(2.2, "midrise", 8, f"{z} mid-rise 25-35 m; min 2,400 m2", grade="B")
    m = re.match(r"^RCL([1-5])$", z)
    if m:
        k = int(m.group(1))
        if k in (2,) and site_m2 < 2400 or k >= 3 and site_m2 < 4000:
            return None
        f = {1: 1.0 if site_m2 < 2000 else 2.0, 2: 2.0, 3: 2.0, 4: 2.5, 5: 2.5}[k]
        o = _o(f, "midrise" if f <= 2.5 else "tower", 12 if k in (1, 3, 5) else 8, f"{z} apartment with limited commercial", grade="B")
        o["mixed_use"] = True
        return o
    if z == "CDT1":
        o = _o(3.0, "tower", 14, "CDT1 downtown commercial 47 m geodetic; >=15% market rental floor area in >60-unit buildings", grade="B")
        o["mixed_use"] = True
        return o
    if z in ("CS2", "CS3"):
        o = _o(1.0, "woodframe", 3 if z == "CS3" else 2, f"{z} service commercial, apartment above grade", grade="B")
        o["mixed_use"] = True
        return o
    return None   # CN (0.5), ZS/ZD/ZT/ZLR/ZHR/ZMU site-specific, AG, industrial, parks


# ------------------------------------------------------------------ New Westminster (Zoning Bylaw 6680 consolidated June 2026)
def _newwest(zone, site_m2, frontage_m, ctx):
    z = zone.upper().strip()
    if z == "RGO-A":
        return _o(0.8, "multiplex", 3, "RGO-A infill: up to 4 units, FSR 0.8, 12 m; DP only, strata permitted", grade="A", units=4)
    if z == "RGO-B":
        return _o(1.0, "multiplex", 3, "RGO-B infill: up to 6 units, FSR 1.0, 12 m; no parking minimum", grade="A", units=6)
    if z in ("RT-A", "RT-B"):
        if site_m2 < 836 or (frontage_m and frontage_m < 20):
            return None
        return _o(1.2, "townhouse", 3, f"{z} pre-zoned townhouse FSR 1.2, 12 m; min 836 m2 and 20 m frontage", grade="A")
    if z in ("RT-2", "RT-2A", "RT-2B", "RT-2C"):
        return _o(0.6, "townhouse", 2, f"{z} townhouse base FSR 0.6 (bonus to 1.2 via s.190.49 cash, not modelled)", grade="A")
    if z in ("RT-3", "RT-3A", "RT-3B"):
        f = {"RT-3": 0.80, "RT-3A": 0.90, "RT-3B": 0.62}[z]
        return _o(f, "townhouse", 3, f"{z} Queensborough townhouse", grade="A")
    if z in ("RM-1", "RM-1A", "RM-1B"):
        return _o(1.2, "townhouse", 2, f"{z} garden apartment / townhouse base FSR 1.2 (bonus 1.8 not modelled)", grade="A")
    if z in ("RM-2",):
        return _o(1.2, "woodframe", 3, "RM-2 apartment base FSR 1.2, 10.67 m (bonus 1.8 not modelled)", grade="A")
    if z in ("RM-2A", "RM-5", "RM-5A"):
        return _o(1.2, "woodframe", 3, f"{z} low-rise apartment; FSR taken as 1.2 (section not read)", grade="D")
    if z == "C-4":
        if site_m2 < 836:
            f = 1.2
        elif site_m2 > 2122:
            f = 3.0
        else:
            f = 1.2 + (site_m2 - 836) / (2122 - 836) * 1.8
        o = _o(f, "woodframe" if f <= 1.8 else "midrise", 4 if f <= 1.8 else 8, "C-4 downtown: residential base density by lot size (bonus to 5.2 not modelled)", grade="A")
        o["mixed_use"] = True
        return o
    if z == "C-8":
        o = _o(1.2, "woodframe", 4, "C-8 Columbia St historic: residential base 1.2 above ground-floor commercial", grade="A"); o["mixed_use"] = True
        return o
    if z == "C-3A":
        if site_m2 < 836:
            return None
        o = _o(5.0, "tower", 20, "C-3A: residential 4.0 + non-residential 1.0", grade="A"); o["mixed_use"] = True
        return o
    if z == "C-3":
        o = _o(3.0, "midrise", 10, "C-3 downtown: 5.2 overall, 3.0 residential assumed outright (70 u/ac base)", grade="D"); o["mixed_use"] = True
        return o
    if z == "C-4A":
        o = _o(3.2, "midrise", 10, "C-4A residential 3.2", grade="A"); o["mixed_use"] = True
        return o
    if z == "C-5":
        o = _o(3.0, "midrise", 8, "C-5 residential 3.0 (>=4 storeys)", grade="A"); o["mixed_use"] = True
        return o
    if z == "C-6":
        o = _o(2.2, "woodframe", 6, "C-6 residential 2.2", grade="A"); o["mixed_use"] = True
        return o
    if z == "C-2A":
        o = _o(1.5, "woodframe", 4, "C-2A 90 u/ac, 4 storeys (FSR derived)", grade="C"); o["mixed_use"] = True
        return o
    if z == "C-2":
        o = _o(1.2, "woodframe", 3, "C-2 3 storeys (FSR derived)", grade="C"); o["mixed_use"] = True
        return o
    return None   # RS/NR/RQ (0.5, single + suite), RT-1 duplex, RM-3/4/6 high-rise (built-out), CD, P, M, C-1


# ------------------------------------------------------------------ City of North Vancouver (Zoning Bylaw 6700; GO & MID zones Dec 2025)
def _cnv(zone, site_m2, frontage_m, ctx):
    z = zone.upper().strip()
    ocp = (ctx.get("ocp") or "").upper()
    if z == "GO":
        if site_m2 <= 280:
            n, fsr = 3, 0.85
        elif ocp in ("LRN2", "R4"):
            n, fsr = 6, 1.0
        else:
            n, fsr = 4, 0.85
        return _o(fsr, "multiplex", 3, f"GO zone: {n} units ({ocp or 'LRN1'}), FSR {fsr}, 3 storeys; strata permitted", grade="A", units=n)
    if z == "MID":
        return _o(2.6, "woodframe", 6, "MID zone: 2.6 FSR, 6 storeys / 21 m outright; inclusionary 2% strata units", grade="A", incl="share_belowmarket:0.02")
    if z == "RM-1":
        return _o(1.6, "woodframe", 3, "RM-1 medium-density apartment 1.6 FSR, 13 m", grade="B")
    if z == "RM-2":
        return _o(1.6, "woodframe", 4, "RM-2: 0.5 base to 1.6 FSR with energy/bonus items, 15 m", grade="B")
    m = re.match(r"^RG-([234])A?$", z)
    if m:
        f = {"2": 0.75, "3": 1.0, "4": 1.25}[m.group(1)]
        return _o(f, "townhouse", 3, f"{z} ground-oriented {f} FSR with bonus items", grade="B")
    return None   # RS-1/RS-2 residual, RT-1, RH-1 (unverified), C-1A/C-1B/C-2, LL-x, CD-xxx (site-specific)


# ------------------------------------------------------------------ District of North Vancouver (Bylaw 3210; R1/R2 July 2026)
def _dnv(zone, site_m2, frontage_m, ctx):
    z = zone.upper().strip()
    if z == "R2" or re.match(r"^RS[1-5]$|^RS(D|EW|H|KL|MF|NQ|PH|Q)$", z):
        # house + secondary suite + coach house, sold as one property (no multiplex outright; Council declined SSMUH Apr 2026)
        if site_m2 <= 464.5:
            gfa = 0.70 * site_m2 + 139.4
        else:
            gfa = min(0.55 * site_m2 + 139.4, 696.8)
        return _o(gfa / site_m2, "duplex", 3, "R2: new house + suite + coach house (max GFA formula, cap 696.8 m2); single-lot sale", grade="A", units=3)
    return None   # R1 rural, RM/RL/RH (Part 5 not verified; largely built-out), C, CD


CITY_RULES = {"burnaby": _burnaby, "richmond": _richmond, "newwest": _newwest, "cnv": _cnv, "dnv": _dnv}


def rule_for(city, zone, site_m2, frontage_m, ctx=None):
    ctx = ctx or {}
    if zone is None or not isinstance(zone, str) or not zone.strip() or not site_m2 or site_m2 <= 0:
        return None
    fn = CITY_RULES.get(city)
    if not fn:
        return None
    try:
        o = fn(zone, float(site_m2), frontage_m, ctx)
    except Exception:
        return None
    if o:
        o.setdefault("mixed_use", False)
    return o


# Bill 47 transit-oriented-area tiers: provincial minimums a rezoning cannot be refused below.
# SkyTrain (tiers 1-3) / bus exchange (tiers 4-5). Not outright zoning anywhere in the inner ring.
TOA_TIERS = {
    "skytrain": [(200, 1, 5.0, "tower", 20, 1348), (400, 2, 4.0, "midrise", 12, 1348), (800, 3, 3.0, "midrise", 8, 460)],
    "bus": [(200, 4, 4.0, "midrise", 12, 1348), (400, 5, 3.0, "midrise", 8, 460)],
}


def toa_tier(kind, dist_m):
    for max_m, tier, fsr, typ, st, min_site in TOA_TIERS.get(kind, []):
        if dist_m <= max_m:
            return dict(tier=tier, fsr=fsr, typology=typ, storeys=st, min_site_m2=min_site, label=f"TOA Tier {tier} (<{max_m} m, {st} st)")
    return None
