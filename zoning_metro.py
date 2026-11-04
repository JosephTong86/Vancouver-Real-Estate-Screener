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


# ------------------------------------------------------------------ Surrey (Zoning By-law 12000, consolidated 21 Sep 2026; MR zones renamed 15 Jun 2026)
SURREY_MR = {  # zone: (fsr, typology, storeys, mixed)
    "MR1": (0.7, "townhouse", 3, False), "MR2": (0.9, "townhouse", 3, False), "MR3": (0.8, "townhouse", 3, False), "MR4": (1.0, "townhouse", 3, False),
    "MR5": (1.5, "townhouse", 4, False), "MR6": (1.4, "woodframe", 4, False), "MR6C": (1.6, "woodframe", 4, True),
    "MR7": (2.0, "woodframe", 6, False), "MR7C": (2.2, "woodframe", 6, True), "MR8": (4.0, "tower", 25, False), "MR8C": (4.3, "tower", 25, True),
    "MR9": (5.0, "tower", 40, False), "MR9C": (5.3, "tower", 40, True), "MR10": (5.5, "tower", 40, False), "MR10C": (6.0, "tower", 40, True),
    "MR10CBD": (7.5, "tower", 40, True), "RM70": (1.3, "townhouse", 4, False),
}


def _surrey(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "").replace("-", "")
    if z in ("RA", "R1", "R2", "R2O", "R3", "R4", "R5", "R5S", "R6", "R7"):
        if ctx.get("toa_tier"):
            # inside a transit-oriented area SSMUH does not apply (max 2 units): duplex at FAR 1.0 on the first 560 m2 + 0.6
            fsr = (1.0 * min(site_m2, 560) + 0.6 * max(0, site_m2 - 560)) / site_m2
            return _o(min(fsr, 1.0), "duplex", 3, "R-zone inside a TOA: SSMUH does not apply, duplex (2 units) outright", grade="B", units=2)
        if site_m2 > 4050:
            return None
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        fsr = (1.0 * min(site_m2, 560) + 0.6 * max(0, site_m2 - 560)) / site_m2
        fsr = min(fsr, 600.0 / site_m2 if n >= 3 else fsr)   # houseplex floor area cap 600 m2 (excl. basement)
        return _o(fsr, "multiplex", 3, f"Surrey SSMUH {n} units (houseplex FAR 1.0 to 560 m2 + 0.6, cap 600 m2; 6 units in a Frequent Bus Stop Area)", grade="B", units=n)
    if z in SURREY_MR:
        f, typ, st, mixed = SURREY_MR[z]
        if z.startswith("MR7") and ctx.get("toa_tier"):
            f = 3.0; typ = "midrise"; st = 8
        if typ == "tower" and site_m2 < 1800:
            return None
        o = _o(f, typ, st, f"{z} base density (bonus density via amenity cash not modelled)", grade="B")
        o["mixed_use"] = mixed
        return o
    return None   # C-35 / CCR / CD site-specific, industrial, agricultural


# ------------------------------------------------------------------ Coquitlam (Zoning Bylaw 3000; R-1..R-4 SSMUH zones Jun 2025; RA/MU zones 2026)
def _coquitlam(zone, site_m2, frontage_m, ctx):
    z = zone.upper().strip()
    if z in ("R-1", "R-2"):
        n = 3 if site_m2 <= 280 else 4
        return _o(0.75 + 0.07, "multiplex", 3, f"{z} small-scale: {n} units, FAR 0.75 + parking bonus, 3 storeys / 11 m (no 6-unit tier in Coquitlam)", grade="A", units=n)
    if z == "R-3":
        return _o(0.5, "duplex", 3, "R-3 transitional: 2 principal + 2 accessory units, FAR 0.5 (townhouse-designated, consolidation expected)", grade="A", units=2)
    if z in ("R-4", "RT-1"):
        return _o(0.85 if z == "R-4" else 0.75, "multiplex", 3, f"{z} multiplex FAR {0.85 if z == 'R-4' else 0.75}", grade="A", units=4)
    if z == "RM-1":
        return _o(0.45, "townhouse", 2, "RM-1 townhouse 0.45 FAR", grade="A")
    if z == "RM-2":
        return _o(1.4, "woodframe", 3, "RM-2 apartment 1.4 FAR, 3 storeys", grade="A")
    if z in ("RM-3", "RM-4", "RM-4A", "RM-5", "RM-6"):
        f, typ, st = {"RM-3": (1.8, "woodframe", 6), "RM-4": (2.5, "midrise", 10), "RM-4A": (2.5, "midrise", 10), "RM-5": (3.0, "midrise", 12), "RM-6": (4.0, "tower", 20)}[z]
        return _o(f, typ, st, f"{z} legacy apartment zone; FAR taken from storey range (bylaw table not read)", grade="D")
    if z == "RA-1":
        return _o(1.85, "midrise", 8, "RA-1: 2.04 FAR, density above 1.85 must be rental -> strata modelled at 1.85, 8 storeys", grade="A")
    if z == "RA-2":
        t = ctx.get("toa_tier")
        f, st = (4.0, 12) if t in (1, 2) else (3.0, 8)
        return _o(2.4, "midrise", st, f"RA-2 (TOA): {f} FAR / {st} storeys, strata capped at 2.4 FAR, remainder rental", grade="A")
    if z == "RA-3":
        return _o(4.0, "tower", 20, "RA-3 high-density: 4.0 FAR base (rental bonus to 5.5 not modelled)", grade="A")
    if z in ("MU-1", "MU-2", "MU-3", "MU-4"):
        f, typ, st = {"MU-1": (2.5, "midrise", 8), "MU-2": (4.0, "midrise", 12), "MU-3": (5.0, "tower", 25), "MU-4": (5.5, "tower", 30)}[z]
        o = _o(f, typ, st, f"{z} mixed-use base FAR (employment share and rental bonus not modelled)", grade="A"); o["mixed_use"] = True
        return o
    return None   # RS-* (in TOA, retained), RTM-1, C-1/C-2/C-5/C-6, CD, P, M


# ------------------------------------------------------------------ Port Moody (Bylaw 2937; SSMUH Bylaw 3460 Jun 2024)
def _portmoody(zone, site_m2, frontage_m, ctx):
    z = zone.upper().strip()
    if z.startswith("RS") or z == "RT":
        if ctx.get("toa_tier") or site_m2 > 4050:
            return None
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        fsr = {3: 0.70, 4: 0.80, 6: 1.0}[n]
        return _o(fsr, "multiplex", 3, f"SSMUH {n} units, FAR {fsr}, 3 storeys (DP only, strata permitted)", grade="B", units=n)
    if z in ("RM1", "RM2", "RM3", "RM4"):
        return _o(0.8 if z in ("RM3", "RM4") else 0.7, "townhouse", 3, f"{z} townhouse; FAR estimated (bylaw table not read)", grade="D")
    if z == "RM5":
        return _o(1.5, "woodframe", 4, "RM5 four-storey apartment; FAR estimated", grade="D")
    if z == "RM8":
        return _o(2.0, "woodframe", 6, "RM8 six-storey apartment; FAR estimated", grade="D")
    if z in ("CRM1", "CRM2"):
        o = _o(1.5 if z == "CRM1" else 2.5, "woodframe", 4 if z == "CRM1" else 6, f"{z} mixed-use; FAR estimated", grade="D"); o["mixed_use"] = True
        return o
    return None   # RM6/RM7 Heritage Woods (built out), C1-C8, TC1, CD


# ------------------------------------------------------------------ Delta (Zoning Bylaw 7600; SSMUH in force Jun 2024, Delta's own site standards)
def _delta(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    flags = ctx.get("flags") or set()
    if "alr" in flags:
        return None
    if re.match(r"^RS[1-7]A?$|^RSC$|^RSF$|^RD[1-4]$", z):
        if site_m2 > 4050:
            return None
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        fsr = (0.30 * site_m2 + 93.0) / site_m2
        typ = "duplex"   # house or duplex + suites + garden suites, sold as one property (suites not strata-able)
        return _o(fsr, typ, 2.5, f"{z}: {n} units allowed (house/duplex + suites + garden suites), FSR 0.3 x lot + 93 m2, 2.5 storeys; single-lot product", grade="B", units=n)
    m = re.match(r"^RT(40|50|62|76)$", z)
    if m:
        f = {"40": 0.6, "50": 0.7, "62": 0.8, "76": 0.9}[m.group(1)]
        return _o(f, "townhouse", 3, f"{z} townhouse {m.group(1)} units/ha (FAR derived)", grade="C") if site_m2 >= 2000 else None
    if z == "TH2":
        return _o(0.8, "townhouse", 3, "TH2 townhouse (FAR derived)", grade="C")
    if z == "RA6":
        return _o(3.0, "midrise", 6, "RA6: FAR 3.0, 6 storeys (Bylaw 8426, 2024)", grade="A") if site_m2 >= 2000 else None
    if z == "RA20":
        return _o(0.6, "woodframe", 3, "RA20 low-rise apartment 20 units/ha (FAR derived)", grade="C")
    if z in ("RA112", "RA120"):
        return _o(1.2, "woodframe", 4, f"{z} apartment ~120 units/ha, 4 storeys / 17 m (FAR derived)", grade="C") if site_m2 >= 2000 else None
    if z == "RH40":
        return _o(2.0, "midrise", 8, "RH40 high-rise zone; FAR placeholder", grade="D")
    if z in ("MUL", "MULW"):
        o = _o(2.5, "woodframe", 6, "Ladner MUL mixed-use, 6 storeys, residential rental-only (no FAR stated; 2.5 assumed)", tenure="rental", grade="D"); o["mixed_use"] = True
        return o
    return None   # C zones (secondary residential only), CD/CDZ site-specific, A, I, P


# ------------------------------------------------------------------ West Vancouver (Bylaw 4662; Bill 25 SSMUH amendments pending Sept 2026)
def _westvan(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    if z in ("RD1", "RD2"):
        return _o(0.5, "duplex", 2, "RD1/RD2: duplex / ground-oriented FAR 0.5, 2 storeys + basement (4-6 units allowed since Aug 2024 within the same FAR)", grade="A", units=4)
    if z == "RD3":
        return _o(0.75, "multiplex", 2, "RD3: FAR 0.75, 4 units (6 near a prescribed bus stop)", grade="A", units=4)
    if z == "RM1":
        return _o(2.0, "midrise", 12, "RM1 apartment FAR 2.0 (1.75 west of 23rd St), up to 20 storeys", grade="A") if site_m2 >= 1115 else None
    if z == "RM2":
        return _o(2.0, "midrise", 8, "RM2 apartment FAR 2.0", grade="A") if site_m2 >= 1115 else None
    if z == "RM5":
        return _o(1.0, "woodframe", 3, "RM5 apartment FAR 1.0, 3 storeys", grade="A") if site_m2 >= 650 else None
    if z in ("RG-1A", "RG-1B", "RG1A", "RG1B", "RG-2", "RG2"):
        return _o(0.6, "townhouse", 3, f"{z} Horseshoe Bay ground-oriented, FAR 0.6 with amenity unit ($45/sf)", grade="A")
    if z in ("RG-3", "RG3"):
        return _o(1.0, "townhouse", 3, "RG-3 Horseshoe Bay FAR 1.0 with amenity unit", grade="A")
    if z in ("AC1", "AC2"):
        o = _o(1.0, "woodframe", 3, f"{z} Ambleside Centre base FAR 1.0 (1.75 with amenity contribution, rate unpublished)", grade="B"); o["mixed_use"] = (z == "AC1")
        return o
    return None   # RS1-RS10 (FAR 0.30 house; Bylaw 5446 SSMUH amendments pending), RM3/RM4, C1-C4 (no FAR), CD, CV


# ------------------------------------------------------------------ Langley City (Zoning Bylaw 3300, adopted 9 Mar 2026)
def _langleycity(zone, site_m2, frontage_m, ctx):
    z = zone.upper().strip()
    if z == "R1":
        if ctx.get("toa_tier"):
            return None   # inside a TOA R1 allows one principal dwelling + suite only
        n = 6 if ctx.get("ftn") else 4
        return _o(0.9, "multiplex", 3, f"R1 plex home: {n} units, no FAR (coverage 36%, 9 m / 3 storeys) -> derived 0.9", grade="C", units=n)
    if z == "R2":
        return _o(1.2, "townhouse", 3, "R2 townhouse FAR 1.2, 11 m", grade="A") if site_m2 >= 1000 else None
    if z in ("R3", "R3A"):
        return _o(2.1, "woodframe", 6, f"{z} low-rise apartment FAR 2.1 base (2.6 with 13% below-market bonus), 6 storeys", grade="A") if site_m2 >= 1000 else None
    if z == "R4":
        return _o(2.6, "midrise", 12, "R4 mid-rise FAR 2.6 base (3.5 bonus), 12 storeys", grade="A") if site_m2 >= 1850 else None
    if z == "R5":
        return _o(4.5, "tower", 15, "R5 high-rise FAR 4.5, 46 m", grade="A") if site_m2 >= 1850 else None
    if z == "C1":
        o = _o(2.6, "midrise", 8, "C1 downtown commercial mixed-use FAR 2.6 base (3.5 in Mixed-Use OCP area)", grade="A"); o["mixed_use"] = True
        return o
    return None   # R5a, C2/C3, I, M, P, U1


# ------------------------------------------------------------------ Langley Township (Bylaw 2500; SSMUH Bylaw 6020 Nov 2024, no FSR)
def _langleytwp(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    flags = ctx.get("flags") or set()
    if re.match(r"^(SR-1|SR-3|R-1[A-E]|R-2|R-CL(\([A-Z]+\))?)$", z):
        if ctx.get("toa_tier") or site_m2 > 4050:
            return None
        n = 3 if site_m2 <= 280 else 4
        # coverage 45% with infill, 9 m, third storey limited to 50-80% of the ground floor -> ~0.95 effective
        return _o(0.95, "multiplex", 3, f"SSMUH {n} units; no FSR (45% coverage, 9 m, limited third storey) -> derived 0.95; water/sewer connection deferral may apply", grade="C", units=n)
    if z in ("RM-1", "RM-2"):
        return _o(0.7 if z == "RM-1" else 0.8, "townhouse", 3, f"{z} townhouse; FAR estimated (Bylaw 2500 tables not read)", grade="D")
    if z in ("RM-3", "RM-3A", "RM-4"):
        return _o(1.75 if z != "RM-4" else 2.0, "woodframe", 4, f"{z} apartment; FAR estimated (Bylaw 2500 tables not read)", grade="D")
    return None   # RU-*, SR-2 (rural / ALR), C-*, CD-*, M, P


# ------------------------------------------------------------------ Maple Ridge (Bylaw 7600-2019; RUR infill zone 2026)
def _mapleridge(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    flags = ctx.get("flags") or set()
    if z in ("RS-1", "RS-1A", "RS-1B", "RS-1D", "RS-2", "RS-3", "SRS", "RUR", "R-1", "R-2", "R-3", "R-4", "RT-1"):
        if "urban_area" not in flags or site_m2 > 4050:
            return None
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        return _o(0.75, "multiplex", 3, f"Urban infill residential (SSMUH) {n} units; FAR taken as 0.75 (s.627 RUR not read)", grade="D", units=n)
    if z == "RT-2":
        return _o(0.75, "multiplex", 2, "RT-2 triplex/fourplex infill FAR 0.75", grade="B", units=4)
    if z in ("RST", "RST-SV"):
        return _o(0.9, "townhouse", 3, "RST fee-simple street townhouse (FAR derived from 223 m2 cap per unit)", grade="C")
    if z in ("RM-1", "RM-4"):
        return _o(0.6 if z == "RM-1" else 0.75, "townhouse", 3, f"{z} townhouse FAR base (+0.15 bonus not modelled)", grade="B") if site_m2 >= 1000 else None
    if z == "RM-5":
        return _o(0.8, "woodframe", 3, "RM-5 low-density apartment FAR 0.8", grade="B") if site_m2 >= 1115 else None
    if z == "RM-2":
        return _o(1.8, "woodframe", 4, "RM-2 medium-density apartment FAR 1.8 (+0.4 bonus not modelled)", grade="B") if site_m2 >= 1300 else None
    if z == "RM-3":
        return _o(1.2, "woodframe", 5, "RM-3 apartment; FAR 1.2 (column mapping uncertain)", grade="D") if site_m2 >= 1300 else None
    if z == "RM-6":
        return _o(1.6, "midrise", 10, "RM-6 Town Centre high-density apartment; FAR 1.6 (+0.5) uncertain", grade="D") if site_m2 >= 2000 else None
    if z in ("C-3", "CRM"):
        o = _o(1.0, "woodframe", 4, f"{z} town centre / commercial-residential, residential FAR 1.0 (bonus not modelled)", grade="D"); o["mixed_use"] = True
        return o
    return None   # C-7 Lougheed corridor (not read), CD, A, P, M, H


# ------------------------------------------------------------------ Abbotsford (Zoning Bylaw 2400-2014; SSMUH zones Bylaws 3690/3691/3692-2025, adopted 16 Dec 2025)
ABBY_RM = {"RM16": 0.21, "RM30": 0.40, "RM45": 0.60, "RM60": 0.80}   # units/ha townhouse zones -> FAR derived at ~130 m2 per unit


def _abbotsford(zone, site_m2, frontage_m, ctx):
    z = zone.upper().strip()
    flags = ctx.get("flags") or set()
    if "alr" in flags or "luc" in flags:
        return None
    if z == "SSMUH 1":
        if site_m2 > 4050 or "urban_area" not in flags:
            return None
        n = 3 if site_m2 <= 280 else 4
        return _o(0.9 if n == 3 else 1.2, "multiplex", 3, f"SSMUH 1: {n}-unit townhouse form, FSR {0.9 if n == 3 else 1.2}, 11 m (principal units may be owned)", grade="B", units=n)
    if z.startswith("SSMUH"):
        if site_m2 > 4050 or "urban_area" not in flags:
            return None
        n = 3 if site_m2 <= 280 else 4
        return _o(0.65, "duplex", 3, f"{z}: duplex + suites / garden suite ({n} units), FSR 0.65, 9.5 m; accessory units not strata-able -> single-lot product", grade="B", units=n)
    if z in ("TH1", "TH2"):
        return _o(1.5, "townhouse", 3, f"{z} townhouse FSR 1.5, 11 m", grade="C" if z == "TH2" else "B") if site_m2 >= 1000 else None
    if z in ("RMG", "RMR"):
        return _o(1.5, "townhouse", 3, f"{z} ground-oriented / rowhouse FSR 0.5-1.5", grade="A") if site_m2 >= 900 else None
    if z == "RMF":
        return _o(0.8, "townhouse", 3, "RMF flex townhouse, 60 units/ha (FAR derived)", grade="C") if site_m2 >= 1000 else None
    if z in ABBY_RM:
        return _o(ABBY_RM[z], "townhouse", 3, f"{z} townhouse {z[2:]} units/ha (FAR derived)", grade="C") if site_m2 >= 1500 else None
    if z == "RML":
        return _o(1.4, "woodframe", 6, "RML low-rise apartment FSR 1.4 (1.7 with bonus), 6 storeys", grade="A") if site_m2 >= 1200 else None
    if z in ("RMM", "RMM-R"):
        return _o(2.5, "woodframe", 6, "RMM mid-rise apartment FSR 2.5, 6 storeys (12 on three Gladwin / Old Yale sites)", grade="A", tenure="rental" if z.endswith("-R") else "strata") if site_m2 >= 1500 else None
    if z in ("RMU", "RMX", "RMC", "RH1", "RMH"):
        return _o(2.0, "woodframe", 5, f"{z} multi-family; FSR placeholder", grade="D") if site_m2 >= 1200 else None
    if z == "C7":
        hist = "historic" in str(ctx.get("ocp") or "").lower()
        o = _o(3.0 if hist else 2.5, "woodframe" if hist else "midrise", 3 if hist else 6, f"C7 downtown commercial: FSR {'3.0 (Historic Centre, 3 st)' if hist else '2.5 (Urban Centre; 3.5 with bonus)'}, residential with another principal use", grade="A"); o["mixed_use"] = True
        return o
    return None   # RS* (not yet SSMUH-mapped), SR/SRH/RR rural, A*, C1-C5, N* comprehensive development, I*, P*


# ------------------------------------------------------------------ Whistler (Zoning Bylaw 303 s.35; SSMUH Bylaws 2440 (Jun 2024) and 2461 (Mar 2025))
def _whistler(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    flags = ctx.get("flags") or set()
    if z in ("RS1", "RI1", "RS2", "RS4", "RT1", "RT2", "RT6") and ("ssmuh4" in flags or "ssmuh3" in flags):
        if ctx.get("toa_tier") or site_m2 > 4050:
            return None
        n = 3 if "ssmuh3" in flags else 4
        cap = 0.45 if z in ("RT1", "RT6") else 0.40
        fsr = min(cap, 511.0 / site_m2)
        return _o(fsr, "multiplex", 2, f"SSMUH {n} units; GFA the lower of FSR {cap} or 511 m2; {n // 2} units employee-restricted rental (strata with housing agreement)", grade="A", units=n, incl="share_employee:0.5")
    return None   # RM1..RM74 / RTA / CC / LC site-specific zones are built out; nightly-rental and tourist zones not modelled


# ------------------------------------------------------------------ Victoria (Zoning Regulation Bylaw 80-159 Schedule P houseplex; Missing Middle Bylaw 22-045 Jan 2023 + SSMUH Jun 2024)
def _victoria(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    if z in ("R1-B", "R1-G", "R1-A", "R-2", "R1-S", "R1-S2", "R-K", "R-J", "R-N", "R-2-CH"):
        if site_m2 > 4050:
            return None
        n = 3 if site_m2 <= 280 else 6   # Schedule P houseplex: up to 6 units on Traditional Residential lots, no transit test
        fsr = min(1.0, 1410.0 / site_m2)
        return _o(fsr, "multiplex", 3, f"Schedule P houseplex: {n} units, FSR 1.0, 11 m, coverage 40% (corner townhouse 1.1 not modelled)", grade="A", units=n)
    if z in ("R3-1", "R3-2", "R3-A1", "R3-A2", "R3-AM-1", "R3-AM-2", "R3-C", "R3-G", "R3-S"):
        return _o(1.0 if z in ("R3-1", "R3-2") else 1.4, "woodframe", 4, f"{z} multiple dwelling district; FSR placeholder", grade="D") if site_m2 >= 900 else None
    if z in ("R-48", "R-59", "R-68"):
        return _o(1.2, "woodframe", 4, f"{z} multiple dwelling; FSR placeholder", grade="D") if site_m2 >= 900 else None
    if z == "GRD-1":
        return _o(1.0, "townhouse", 3, "GRD-1 ground-oriented residential (ZB2018) FSR 1.0 placeholder", grade="D") if site_m2 >= 700 else None
    if z in ("LVD-1", "CVD-1"):
        return _o(1.5 if z == "LVD-1" else 2.0, "woodframe", 4 if z == "LVD-1" else 6, f"{z} (ZB2018) FSR placeholder", grade="D") if site_m2 >= 900 else None
    if z in ("C-1", "C1-N", "C1-S", "C1-G", "CA-1", "CA-3", "CA-4"):
        o = _o(3.0, "midrise", 8, f"{z} central-area commercial: FSR 3.0 (Downtown Core Area Plan), ground-floor commercial", grade="C"); o["mixed_use"] = True
        return o
    return None


# ------------------------------------------------------------------ Saanich (Zoning Bylaw 8200 Schedule G SSMUH, in force 30 Jun 2024)
def _saanich(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    flags = ctx.get("flags") or set()
    if "alr" in flags:
        return None
    if re.match(r"^RS-\d+[A-Z]?$|^RD-\d+$|^A-[12]$", z):
        if "urban_area" not in flags or site_m2 > 4050 or ctx.get("toa_tier"):
            return None
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        fsr = 1.1 if n == 6 else 1.0
        return _o(fsr, "multiplex", 3, f"Schedule G SSMUH {n} units (6 in the Transit Proximity Area), FSR {fsr}, 11 m; strata permitted", grade="B", units=n)
    if z.startswith("RT-"):
        return _o(0.8, "townhouse", 3, f"{z} attached housing; FSR placeholder", grade="D") if site_m2 >= 900 else None
    if z.startswith("RA-") or z.startswith("RM-"):
        return _o(1.3, "woodframe", 4, f"{z} apartment; FSR placeholder", grade="D") if site_m2 >= 1200 else None
    if z in ("C-3", "C-4", "C-5", "C-6", "C-13") or z.startswith("CMU"):
        o = _o(2.0, "woodframe", 6, f"{z} commercial / mixed-use; FSR placeholder", grade="D"); o["mixed_use"] = True
        return o
    return None


# ------------------------------------------------------------------ Oak Bay (Zoning Bylaw 3531 Schedule G, SSMUH adopted Jun 2024: houseplex FSR 1.0, coverage 50%)
def _oakbay(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    if z.startswith("RS") and site_m2 <= 4050:
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        return _o(1.0, "multiplex", 3, f"SSMUH houseplex {n} units, FSR 1.0, coverage 50% (zone assumed RS: Oak Bay publishes no zoning layer)", grade="D", units=n)
    return None


# ------------------------------------------------------------------ Esquimalt (Zoning Bylaw 2050; RSM-1 small-scale multi-unit zone Jun 2024)
def _esquimalt(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    flags = ctx.get("flags") or set()
    if "rsm1" in flags or z in ("RS-1", "RS-2", "RS-3", "RS-4", "RS-5", "RS-6", "RD-1", "RD-2", "RD-3", "RD-4", "RSM-1", "RSM1"):
        if site_m2 > 4050:
            return None
        n = 3 if site_m2 <= 280 else 4
        return _o(0.8, "multiplex", 3, f"RSM-1 small-scale multi-unit: {n} units; FSR placeholder 0.8", grade="D", units=n)
    if z.startswith("RM-"):
        return _o(1.2, "woodframe", 4, f"{z} multiple family; FSR placeholder", grade="D") if site_m2 >= 1000 else None
    return None


# ------------------------------------------------------------------ Langford (Zoning Bylaw 300; SSMUH Amendment Bylaw 2183 Schedule AA, Jun 2024)
def _langford(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    if z in ("R2", "RS1", "RS2", "RS3", "R1", "RR1", "RR2", "RR3"):
        if ctx.get("toa_tier") or site_m2 > 4050 or z.startswith("RR") and site_m2 > 2000:
            return None
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        return _o(0.9, "multiplex", 3, f"SSMUH {n} units (Schedule AA frequent-stop lots get 6); FSR placeholder 0.9", grade="D", units=n)
    if z.startswith("RT"):
        return _o(1.0, "townhouse", 3, f"{z} townhouse; FSR placeholder", grade="D") if site_m2 >= 900 else None
    if z.startswith("RM") or z.startswith("RH"):
        return _o(1.6 if z.startswith("RM") else 3.0, "woodframe" if z.startswith("RM") else "midrise", 4 if z.startswith("RM") else 10, f"{z} multi-family; FSR placeholder", grade="D") if site_m2 >= 1000 else None
    if z.startswith("MU") or z in ("CC1", "CC2", "C1", "C3"):
        o = _o(2.5, "woodframe", 6, f"{z} mixed-use / city centre; FSR placeholder", grade="D"); o["mixed_use"] = True
        return o
    return None


# ------------------------------------------------------------------ Colwood (Land Use Bylaw 151; SSMUH Jun 2024)
def _colwood(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    if z in ("R1", "R2", "R3", "R4", "R5", "R6", "RC1"):
        if ctx.get("toa_tier") or site_m2 > 4050:
            return None
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        return _o(0.8, "multiplex", 3, f"SSMUH {n} units; FSR placeholder 0.8", grade="D", units=n)
    if z.startswith("RT"):
        return _o(1.0, "townhouse", 3, f"{z} townhouse; FSR placeholder", grade="D") if site_m2 >= 900 else None
    if z.startswith("RM"):
        return _o(1.4, "woodframe", 4, f"{z} multi-family; FSR placeholder", grade="D") if site_m2 >= 1000 else None
    if z.startswith("MU") or z.startswith("C"):
        o = _o(2.0, "woodframe", 5, f"{z} commercial / mixed-use; FSR placeholder", grade="D"); o["mixed_use"] = True
        return o
    return None


# ------------------------------------------------------------------ View Royal (Zoning Bylaw 900; SSMUH map Aug 2024; six prescribed stops)
def _viewroyal(zone, site_m2, frontage_m, ctx):
    z = zone.upper().replace(" ", "")
    if z.startswith("R1") and site_m2 <= 4050:
        n = _ssmuh_units(site_m2, ctx.get("ftn", False))
        return _o(0.8, "multiplex", 3, f"SSMUH {n} units; FSR placeholder 0.8 (zone assumed R1: no open zoning layer)", grade="D", units=n)
    return None


CITY_RULES = {"burnaby": _burnaby, "richmond": _richmond, "newwest": _newwest, "cnv": _cnv, "dnv": _dnv,
              "surrey": _surrey, "coquitlam": _coquitlam, "portmoody": _portmoody, "delta": _delta, "westvan": _westvan,
              "langleycity": _langleycity, "langleytwp": _langleytwp, "mapleridge": _mapleridge,
              "abbotsford": _abbotsford, "whistler": _whistler, "victoria": _victoria, "saanich": _saanich, "oakbay": _oakbay,
              "esquimalt": _esquimalt, "langford": _langford, "colwood": _colwood, "viewroyal": _viewroyal}

# Cities where Bill 47 tiers apply only to bus-exchange / commuter-rail TOAs (B.C. Reg. 263/2023 tables 4-5), or not at all
TOA_KINDS = {"delta": ("bus",), "westvan": (), "mapleridge": ("bus",), "dnv": ("bus",), "cnv": ("bus",),
             "abbotsford": ("bus_bc",), "whistler": ("bus_whistler",), "victoria": ("bus_bc",), "saanich": ("bus_bc",), "oakbay": (),
             "esquimalt": (), "langford": ("bus_bc",), "colwood": ("bus_bc",), "viewroyal": ("bus_bc",)}


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
    "bus_bc": [(200, 4, 3.5, "midrise", 10, 1348), (400, 5, 2.5, "woodframe", 6, 460)],         # Table 4-5 item 2 (Abbotsford, Capital Region, ...)
    "bus_whistler": [(200, 4, 2.5, "woodframe", 6, 1000), (400, 5, 1.5, "woodframe", 4, 460)],  # Table 4-5 item 3 (Whistler, Penticton, Lantzville)
}


def toa_tier(kind, dist_m):
    for max_m, tier, fsr, typ, st, min_site in TOA_TIERS.get(kind, []):
        if dist_m <= max_m:
            return dict(tier=tier, fsr=fsr, typology=typ, storeys=st, min_site_m2=min_site, label=f"TOA Tier {tier} (<{max_m} m, {st} st)")
    return None
