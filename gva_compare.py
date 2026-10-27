#!/usr/bin/env python3
"""
Metro Vancouver municipality comparison: the same three redevelopment prototypes run through
each city's 2026 land prices, achievable sale prices, hard costs and government charges.

Prototype A  Multiplex on a standard 50 x 120 ft lot (557 m2, 6,000 sf) under each city's SSMUH zoning
Prototype B  6-storey wood-frame strata on a 1,400 m2 (15,070 sf) assembled site at 2.5 FSR
Prototype C  20-storey concrete tower on a 2,000 m2 (21,530 sf) transit-area site at 5.0 FSR

Writes output/gva_compare.json. All inputs cited in the dashboard notes; estimates flagged.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
SQFT = 10.7639
TARGET = 0.15
SOFT = {"A": 0.22, "B": 0.24, "C": 0.28}           # soft incl. financing, marketing, consultants
CARRY_M = {"A": 18, "B": 30, "C": 48}               # months of land carry at 6.5% (permit + build + sell-out)
EFF = {"A": 0.90, "B": 0.85, "C": 0.80}
UNIT_SF = {"A": 1000, "B": 800, "C": 750}
BASE_HARD = {"A": 420, "B": 360, "C": 560}          # Vancouver all-in $/sf GFA incl. parking & site work (tower: BTY 2026 $500-750 range)
CONCRETE_ACHIEVED = 0.92                            # concrete presale clearing prices vs asking in 2026
DEMO = 60000

# Metro Vancouver regional DCC after the July 24 2026 rollback (per unit) + TransLink 2026
METRO = {
    "fraser":   {"th": 20296, "apt": 14396},
    "van":      {"th": 19874, "apt": 13392},
    "nshore":   {"th": 19277, "apt": 13099},
    "lulu":     {"th": 15208, "apt": 10610},
}
TRANSLINK = {"th": 2837, "apt": 1774}

def ptt(p):
    t = 0.01 * min(p, 2e5)
    if p > 2e5: t += 0.02 * (min(p, 2e6) - 2e5)
    if p > 2e6: t += 0.03 * (p - 2e6)
    if p > 3e6: t += 0.02 * (p - 3e6)
    return t

# ------------------------------------------------------------------ per-municipality inputs
# price: achievable 2026 $/sf net saleable [multiplex/TH, wood-frame condo, concrete condo]  (asking x ~0.93 for condos)
# lot: Sept 2026 HPI benchmark detached (what a standard lot with an old house costs)
# land_bsf: land $/buildable sf for [6-st wood-frame site, high-rise transit site]  (est. from 2025-26 comps/asks)
# ssmuh: [units on a 557 m2 lot, FSR]
# fees(proto, gfa, units) -> municipal DCC + ACC/CAC + SSAC  (Metro + TransLink added separately)
CITIES = {
 "Vancouver West": dict(metro="van", hard=1.00, price=[1300, 1300, 1500], lot=2916100, land_bsf=[350, 100], ssmuh=[6, 1.00],
    fees=lambda p,g,u: g*(8.26+2.32) if p=="A" else g*(32.47+5.00), ssac=0,
    zoning="R1-1 multiplex 1.0 FSR outright; R3/R4/R5 pre-zoned on Broadway & Cambie; TOAs rezoning-based",
    note="Oakridge/Kits scarcity pricing; Broadway tower land now ~$70-100/bsf (down ~50% since 2022)"),
 "Vancouver East": dict(metro="van", hard=1.00, price=[800, 1050, 1250], lot=1630500, land_bsf=[220, 80], ssmuh=[6, 1.00],
    fees=lambda p,g,u: g*(8.26+2.32) if p=="A" else g*(32.47+5.00), ssac=0,
    zoning="R1-1 multiplex 1.0 FSR outright; C-2 arterials 2.5-3.0; Joyce/Nanaimo TOAs rezoning-based",
    note="Multiplex end-units $650-850/sf don't cover $420/sf build + $1.6M lot"),
 "Burnaby": dict(metro="fraser", hard=0.95, price=[980, 1000, 1050], lot=1800000, land_bsf=[180, 70], ssmuh=[4, 0.90],
    fees=lambda p,g,u: u*56297 if p=="A" else u*38841, ssac=800,
    zoning="New height-based Zoning Bylaw in force Jul 1 2026: R2-R8 (4-40 st) outright in town centres; R1 SSMUH 3-4 units (6 near frequent bus), rolled back to 3 st Oct 2025",
    note="Lowest fees of the big cities; but 1,200 completed-unsold condos, achieved high-rise ~$1,000-1,100/sf vs $1,400 at 2022 peak"),
 "Surrey (City Centre)": dict(metro="fraser", hard=0.87, price=[640, 800, 950], lot=1304100, land_bsf=[90, 50], ssmuh=[4, 0.80],
    fees=lambda p,g,u: (51633+11669)*u/4 + u*600 if p=="A" else (g*(30.72+10.58) if p=="B" else g*(30.30+10.58)), ssac=0,
    zoning="SSMUH 3/4/6 units (under review Jul 2026); 10 SkyTrain TOAs with new MR7-MR10 zones (3.0-6.0 FAR) but still rezoning-based",
    note="DCC cut 7-9% pending; ACC from Jun 2026; Centra tower in foreclosure, distressed land sales"),
 "Coquitlam (Burquitlam)": dict(metro="fraser", hard=0.95, price=[900, 980, 960], lot=1584400, land_bsf=[140, 70], ssmuh=[4, 0.80],
    fees=lambda p,g,u: u*(43483+21205) if p=="A" else (u*24435 + g*21.31 if p=="B" else u*24435 + g*38.53), ssac=800,
    zoning="SSMUH 3-4 units (no 6-unit tier); 8 TOAs NOT pre-zoned, rezoning required; SW Shoulders & Corridors plan May 2026",
    note="Highest per-unit DCC+ACC on multiplex in the region (~$65k/unit before Metro); 15% density-bonus cut for 2025 permits"),
 "New Westminster": dict(metro="fraser", hard=0.95, price=[760, 800, 900], lot=1356900, land_bsf=[130, 60], ssmuh=[4, 0.80],
    fees=lambda p,g,u: g*9.76 + u*8000 + u*1000 if p=="A" else g*13.26 + g*8.0 + u*1000, ssac=0,
    zoning="Infill Housing Program Jun 2026: RGO-A 4 units / RGO-B 6 units pre-zoned (~3,000 lots); TOA not outright",
    note="Cheapest per-sf DCC in Metro; ACC rate table not published (est. $8/sf used)"),
 "Richmond": dict(metro="lulu", hard=0.95, price=[1000, 810, 1020], lot=1871100, land_bsf=[170, 80], ssmuh=[4, 0.58],
    fees=lambda p,g,u: u*(47182+12102) if p=="A" else (g*(34.31+12.94)), ssac=800,
    zoning="RSM 3/4/6 units but FSR only 0.6 on first 464.5 m2 + 0.3 on balance, 2.5 st; TOAs rezoning-based; arterial policy 4-5 st",
    note="SSMUH FSR too low to pencil; DCC increase deferred to Jan 2027; apartment permits down ~40% in 2025"),
 "North Vancouver City": dict(metro="nshore", hard=0.95, price=[1000, 1060, 1280], lot=2042000, land_bsf=[200, 120], ssmuh=[4, 0.85],
    fees=lambda p,g,u: u*14884 if p=="A" else (u*12593 if p=="B" else u*10304 + g*0.5*110), ssac=800,
    zoning="Multiplex bylaw Dec 2025: 4 units 0.85 FSR (6 units 1.0 FSR on ~600 lots); Lonsdale density via OCP bonus + CAC $110-140/sf, no outright TOA",
    note="Strong concrete pricing ($1,250-1,480/sf asking) but CAC on bonus density is the region's steepest"),
 "North Vancouver District": dict(metro="nshore", hard=0.95, price=[1110, 1030, 1000], lot=2042000, land_bsf=[180, 90], ssmuh=[3, 0.50],
    fees=lambda p,g,u: u*64865 if p=="A" else u*45818, ssac=800,
    zoning="3 units at 0.35-0.50 FSR; 4 units on ~4,000 lots (Dec 2025); Council refused 6-unit/3-st compliance Apr 2026; TOAs rezoning-based",
    note="ACC replaced fixed CACs at +18-32%; lowest small-lot density in the region"),
 "Port Moody": dict(metro="fraser", hard=0.95, price=[900, 910, 960], lot=1903500, land_bsf=[140, 70], ssmuh=[4, 0.80],
    fees=lambda p,g,u: u*(34892*0.6+11218) if p=="A" else g*20.0 + u*7159, ssac=800,
    zoning="SSMUH 3/4/6 units 3 st; Moody Centre & Inlet Centre TOAs NOT outright, application process unchanged",
    note="Multi-res DCC schedule not retrieved (est. $20/sf); +167% DCC proposal referred back Mar 2026; staff: no scenario reached 15% margin"),
 "Langley Township": dict(metro="fraser", hard=0.87, price=[620, 780, None], lot=1471100, land_bsf=[60, None], ssmuh=[4, 0.40],
    fees=lambda p,g,u: u*(55000+13584) if p=="A" else u*(38482+8634), ssac=800,
    zoning="SSMUH 3/4 units at ~0.40 FSR / 9 m (adopted last in region, Nov 2024); Willowbrook TOA designated May 2025, rezoning-based",
    note="Highest SF DCC in region ($86,787/lot) with a draft 15-18% cut under review; no concrete projects selling"),
}

def proforma(city, proto):
    c = CITIES[city]
    if proto == "A":
        site_sf = 557 * SQFT; units_max, fsr = c["ssmuh"]; gfa = site_sf * fsr
        land = c["lot"]; price = c["price"][0]
        units = min(units_max, max(1, round(gfa * EFF["A"] / UNIT_SF["A"])))
        metro = METRO[c["metro"]]["th"] * units + TRANSLINK["th"] * units
    elif proto == "B":
        site_sf = 1400 * SQFT; fsr = 2.5; gfa = site_sf * fsr
        if c["land_bsf"][0] is None: return None
        land = gfa * c["land_bsf"][0]; price = c["price"][1]
        units = round(gfa * EFF["B"] / UNIT_SF["B"])
        metro = METRO[c["metro"]]["apt"] * units + TRANSLINK["apt"] * units
    else:
        site_sf = 2000 * SQFT; fsr = 5.0; gfa = site_sf * fsr
        if c["land_bsf"][1] is None or c["price"][2] is None: return None
        land = gfa * c["land_bsf"][1]; price = c["price"][2] * CONCRETE_ACHIEVED
        units = round(gfa * EFF["C"] / UNIT_SF["C"])
        metro = METRO[c["metro"]]["apt"] * units + TRANSLINK["apt"] * units
    saleable = gfa * EFF[proto]
    revenue = saleable * price
    hard = gfa * BASE_HARD[proto] * c["hard"]
    soft = hard * SOFT[proto]
    carry = 0.065 * CARRY_M[proto] / 12
    fees = c["fees"](proto, gfa, units) + c["ssac"] * units + metro + units * 6000
    acq = land + ptt(land) + land * 0.01 + DEMO + land * carry
    cost = acq + hard + soft + fees
    profit = revenue - cost
    nonland = hard + soft + fees + DEMO
    k = 1 + 0.03 + 0.01 + carry
    rlv = max(0, (revenue / (1 + TARGET) - nonland) / k)
    # developer equity: all of the land, plus the 25% of construction+soft+fees a lender won't fund (75% LTC construction loan)
    equity = acq + 0.25 * (hard + soft + fees)
    return dict(city=city, proto=proto, gfa=round(gfa), units=units, price=price, revenue=round(revenue), land=round(land),
                acq=round(acq), hard=round(hard), soft=round(soft), fees=round(fees), cost=round(cost), profit=round(profit),
                equity=round(equity), roe=round(profit / equity, 4),
                margin=round(profit / cost, 4), rlv=round(rlv), rlv_vs_land=round(rlv / land, 2) if land else None,
                fees_per_unit=round(fees / units), land_per_bsf=round(land / gfa), hard_psf=round(BASE_HARD[proto] * c["hard"]))

rows = [r for city in CITIES for p in "ABC" if (r := proforma(city, p))]
meta = {city: dict(zoning=c["zoning"], note=c["note"], lot=c["lot"], price=c["price"], land_bsf=c["land_bsf"], ssmuh=c["ssmuh"], hard=c["hard"])
        for city, c in CITIES.items()}
json.dump({"rows": rows, "cities": meta}, open(os.path.join(HERE, "output", "gva_compare.json"), "w"), indent=1)
for p, name in [("A", "Multiplex on a 557 m2 lot"), ("B", "6-st wood-frame, 2.5 FSR"), ("C", "20-st tower, 5.0 FSR")]:
    print(f"\n== {name}")
    for r in sorted([r for r in rows if r["proto"] == p], key=lambda r: -r["margin"]):
        print(f"  {r['city']:26} cost {r['cost']/1e6:6.1f}M  equity {r['equity']/1e6:5.1f}M  profit {r['profit']/1e6:7.2f}M  margin {r['margin']*100:6.1f}%  profit/equity {r['roe']*100:6.0f}%")
