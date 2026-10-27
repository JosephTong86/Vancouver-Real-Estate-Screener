"""
Outright / conditional density rules for City of Vancouver zoning districts.

Each rule returns the *strata (for-sale)* development option that a developer could
pursue without a rezoning, given the site area and an estimated frontage.

Returns dict(fsr, typology, tenure, storeys, note, incl) or None when the district
has no meaningful residential redevelopment path (industrial, CD-1, parks, etc.).

Sources: CoV Zoning & Development By-law district schedules (Feb-Jul 2026 editions),
Standardized Apartment Districts (R3/R4/R5, enacted Oct 21 2025; R3 small-site 1.60
effective Jul 29 2026), Secured Rental Policy (May 2026).
"""

R1_MULTIPLEX_MIN_M2 = 306      # 3-4 units
R1_5UNIT_MIN_M2 = 464
R1_6UNIT_MIN_M2 = 557
R3_MIN_SITE_M2 = 460
R4R5_MIN_SITE_M2 = 1348


def _opt(fsr, typology, storeys, note="", tenure="strata", incl=None):
    return {"fsr": fsr, "typology": typology, "storeys": storeys,
            "tenure": tenure, "note": note, "incl": incl}


def rule_for(zone: str, site_m2: float, frontage_m: float):
    z = ("" if zone is None or (isinstance(zone, float)) else str(zone)).strip().upper()

    # ---------------- Residential Inclusive (multiplex) ----------------
    if z == "R1-1":
        if site_m2 >= R1_6UNIT_MIN_M2:
            return _opt(1.00, "multiplex", 3, "6-unit multiplex (8 if rental)")
        if site_m2 >= R1_5UNIT_MIN_M2:
            return _opt(1.00, "multiplex", 3, "5-unit multiplex")
        if site_m2 >= R1_MULTIPLEX_MIN_M2:
            return _opt(1.00, "multiplex", 3, "3-4 unit multiplex")
        return _opt(0.70, "duplex", 2, "Lot < 306 m2: duplex only")

    # ---------------- RT two-family / small-scale ----------------
    if z in ("RT-7", "RT-9"):
        if site_m2 >= R1_MULTIPLEX_MIN_M2:
            return _opt(1.00, "multiplex", 3, "Multiplex up to 6 units")
        return _opt(0.75, "duplex", 2)
    if z in ("RT-2", "RT-3", "RT-5", "RT-8"):
        return _opt(0.75, "duplex", 2, "Conditional 0.75 (SSMUH allows 3-6 units)")
    if z == "RT-10":
        return _opt(0.80, "duplex", 2)
    if z == "RT-11":
        return _opt(0.85, "duplex", 3)
    if z in ("RT-1", "RT-4", "RT-4A"):
        return _opt(0.75, "duplex", 2)

    # ---------------- RM multiple dwelling ----------------
    if z == "RM-1":
        return _opt(1.20, "townhouse", 2)
    if z == "RM-2":
        return _opt(0.95, "woodframe", 3)
    if z in ("RM-3", "RM-3A"):
        return _opt(1.20, "woodframe", 3, "1.20 conditional (3.0 only if 100% social)")
    if z == "RM-4":
        return _opt(1.45, "woodframe", 4, "1.45 apartment")
    if z == "RM-5":
        return _opt(1.50, "woodframe", 6)
    if z in ("RM-5A", "RM-5C", "RM-5D"):
        return _opt(2.20, "woodframe", 6)
    if z == "RM-5B":
        return _opt(2.75, "woodframe", 6)
    if z in ("RM-7", "RM-7A"):
        return _opt(1.20, "townhouse", 3)
    if z in ("RM-8", "RM-8A"):
        incl = "RM-8A_cash" if z == "RM-8A" else None
        return _opt(1.20, "townhouse", 3, "Townhouse / rowhouse", incl=incl)
    if z in ("RM-9", "RM-9B", "RM-9A"):
        if frontage_m >= 27.4:
            return _opt(2.00, "woodframe", 4, "Frontage >= 27.4 m")
        if z == "RM-9A" and frontage_m >= 15.2:
            return _opt(1.75 if frontage_m >= 20 else 1.50, "woodframe", 4)
        if frontage_m >= 15.2:
            return _opt(1.50, "woodframe", 4, "Frontage >= 15.2 m")
        if frontage_m >= 12.8:
            return _opt(1.20, "woodframe", 4)
        return _opt(0.75, "townhouse", 3, "Narrow lot")
    if z == "RM-10":
        if frontage_m >= 40 and site_m2 >= 1115:
            return _opt(2.60, "woodframe", 6)
        if frontage_m >= 30 and site_m2 >= 855:
            return _opt(2.40, "woodframe", 6)
        return _opt(0.90, "townhouse", 3, "Below RM-10 apartment thresholds")
    if z == "RM-11":
        if frontage_m >= 36.6:
            return _opt(1.70, "woodframe", 4)
        return _opt(1.20, "townhouse", 3)
    if z == "RM-12":
        return _opt(1.70, "woodframe", 4)

    # ---------------- Standardized apartment districts (Broadway / Cambie pre-zoning) ----------------
    if z in ("R3-1", "R3-3"):
        if site_m2 >= R3_MIN_SITE_M2:
            return _opt(2.00, "woodframe", 6, "Mixed-tenure strata apt (rental option 2.7-3.0)")
        return _opt(1.60, "townhouse", 3, "Small site (< 460 m2)")
    if z == "R3-2":
        # apartment form is rental-only in R3-2; strata limited to townhouse/other 1.60
        return _opt(1.60, "townhouse", 3, "Strata limited to 1.60 (apt form is rental-only: 2.2-2.7)")
    if z == "R4-1":
        if site_m2 >= R4R5_MIN_SITE_M2:
            return _opt(4.00, "midrise", 12, "Mid-rise apartment 4.0 (4.3 mixed-use)")
        return _opt(1.60, "townhouse", 3, "Below R4 min site (1,348 m2) - assembly needed")
    if z == "R5-1":
        if site_m2 >= R4R5_MIN_SITE_M2:
            return _opt(5.00, "tower", 26, "Strata 5.0 with 20% social housing", incl="R5_strata_social")
        return _opt(1.60, "townhouse", 3, "Below R5 min site - assembly needed")
    if z == "R5-3":
        if site_m2 >= R4R5_MIN_SITE_M2:
            return _opt(6.00, "tower", 26, "Strata 6.0 with 20% social housing", incl="R5_strata_social")
        return _opt(1.60, "townhouse", 3, "Below R5 min site - assembly needed")
    if z in ("R5-2", "R5-4"):
        if site_m2 >= R4R5_MIN_SITE_M2:
            return _opt(6.50 if z == "R5-4" else 5.50, "tower", 22, "Rental-only tower (20% below-market)", tenure="rental")
        return _opt(1.60, "townhouse", 3, "Below R5 min site - assembly needed")

    # ---------------- Secured rental districts ----------------
    if z == "RR-2A":
        return _opt(2.00, "woodframe", 4, "Rental-only", tenure="rental")
    if z == "RR-2B":
        return _opt(3.00, "woodframe", 6, "Rental-only", tenure="rental")
    if z in ("RR-3B", "RR-3C"):
        return _opt(3.50, "woodframe", 6, "Rental-only mixed-use", tenure="rental")

    # ---------------- Commercial (mixed-use residential over retail) ----------------
    if z == "C-1":
        return _opt(1.20, "woodframe", 3, "Mixed-use 1.2 (0.75 dwelling)")
    if z in ("C-2", "C-2A", "C-2B"):
        return _opt(2.50, "woodframe", 4, "Strata mixed-use 2.5 (rental 3.5, 6 st)")
    if z in ("C-2C", "C-2C1"):
        return _opt(3.00, "woodframe", 4, "Strata mixed-use 3.0 (rental 3.5, 6 st)")
    if z == "C-3A":
        return _opt(3.00, "midrise", 8, "Discretionary to 3.0 (DP Board)")
    if z in ("C-5", "C-5A"):
        return _opt(2.20, "woodframe", 6)
    if z in ("C-7", "C-8"):
        return _opt(2.25, "woodframe", 4)

    return None


def is_mixed_use(zone: str) -> bool:
    z = str(zone or "").upper()
    return z.startswith("C-") or z.startswith("RR-3")
