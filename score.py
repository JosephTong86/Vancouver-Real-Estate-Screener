#!/usr/bin/env python3
"""
Vancouver pre-zoned redevelopment screener.

Reads:  data/tax_2026_land.csv   (CoV property-tax-report, LAND legal type, report_year 2026)
        data/parcels.csv         (CoV property-parcel-polygons: tax_coord, lat/lon, area_m2)
        data/aux.json            (SkyTrain stations, local-area polygons)
        data/listings.csv        (optional: your MLS / REW export, see README)
        assumptions.json
Writes: output/all_scored.csv, output/top100.csv, output/top100.json, output/summary.json

Model: residual land value margin.
  Revenue  = saleable area x achievable $/sf (by local area & building type)
  Costs    = acquisition (assessed value x market factor + PTT + closing + demo + carry)
           + hard + soft + DCL + ACC + Metro/TransLink DCCs + inclusionary obligations
  Profit   = Revenue - Costs ;  Margin = Profit / Costs
Ranked by profit (absolute $) among sites clearing the target margin; margin rank also given.
"""
import json, math, os, re, sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zoning_rules import rule_for, is_mixed_use

HERE = os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(HERE, "assumptions.json")))
SQFT_PER_M2 = 10.7639
TYPICAL_LOT_DEPTH_M = 37.2   # 122 ft; used to estimate frontage = area / depth


# ---------------------------------------------------------------- helpers
def ptt_bc(price: float) -> float:
    """BC Property Transfer Tax (residential): 1% to 200k, 2% to 2M, 3% above 2M, +2% above 3M."""
    t = 0.01 * min(price, 200_000)
    if price > 200_000:
        t += 0.02 * (min(price, 2_000_000) - 200_000)
    if price > 2_000_000:
        t += 0.03 * (price - 2_000_000)
    if price > 3_000_000:
        t += 0.02 * (price - 3_000_000)
    return t


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def build_area_lookup(areas):
    polys = []
    for a in areas:
        rings = a["coords"] if a["type"] == "Polygon" else [p for mp in a["coords"] for p in mp]
        outer = rings[0] if a["type"] == "Polygon" else None
        if a["type"] == "Polygon":
            polys.append((a["name"], [a["coords"][0]]))
        else:
            polys.append((a["name"], [pg[0] for pg in a["coords"]]))
    def lookup(lon, lat):
        for name, outers in polys:
            for ring in outers:
                if point_in_ring(lon, lat, ring):
                    return name
        return None
    return lookup


def price_for(area, typology):
    tbl = A["prices_per_sf_saleable"]
    row = tbl.get(area) or tbl["_default"]
    if typology in ("duplex", "multiplex", "townhouse"):
        return row[0]
    if typology == "woodframe":
        return row[1]
    return row[2]


def dcl_tier(fsr):
    if fsr <= 1.2:
        return "le_1_2"
    if fsr <= 1.5:
        return "le_1_5"
    return "gt_1_5"


def proforma(site_sf, fsr, typology, tenure, area, zone, incl, assessed_total, mixed_use, price_override=None):
    """Return dict with revenue, cost components and profit for one development option."""
    T = A["typologies"][typology]
    L = A["levies"]
    gfa = site_sf * fsr
    saleable = gfa * T["eff"]
    units = max(1, round(saleable / T["unit_sf"]))
    base_price = price_for(area, typology)

    # revenue
    res_share = 1.0 - (A["commercial_share_mixed_use"] if mixed_use else 0.0)
    revenue = saleable * res_share * base_price + saleable * (1 - res_share) * base_price * A["commercial_price_factor"]
    if tenure == "rental":
        bm = A["toa"]["below_market_share"] if "TOA" in (incl or "") or zone.startswith("R5") else 0.0
        revenue = revenue * A["rental_value_factor"] * ((1 - bm) + bm * A["toa"]["below_market_value_factor"])
    incl_cost = 0.0
    if incl == "R5_strata_social":
        revenue *= (1 - A["inclusionary"]["R5_strata_social_share"])   # 20% of floor area delivered turnkey, no revenue
    elif incl == "RM-8A_cash":
        incl_cost = gfa * A["inclusionary"]["RM-8A_cash_per_sf"]
    elif incl == "R1-1_westside_cash":
        incl_cost = gfa * A["inclusionary"]["R1-1_westside_large_lot_cash_per_sf"]

    # acquisition
    acq_price = price_override if price_override else assessed_total * A["acquisition"]["market_over_assessed"]
    acq = acq_price + ptt_bc(acq_price) + acq_price * A["acquisition"]["closing_costs_pct"] \
        + A["acquisition"]["demolition_per_site"]
    carry = acq_price * A["acquisition"]["carry_rate_annual"] * A["acquisition"]["carry_months"] / 12

    # construction
    hard = gfa * T["hard"]
    soft = hard * A["soft_cost_pct_of_hard"]
    tier = dcl_tier(fsr)
    dcl = gfa * L["dcl_per_sf"][tier]
    if tenure == "rental":
        dcl *= (1 - L["dcl_rental_waiver_pct"])
    acc = gfa * L["acc_per_sf"][tier]
    dcc = units * (L["metro_dcc_per_unit"][T["dcc_type"]] + L["translink_dcc_per_unit"] + L["permits_misc_per_unit"])

    cost = acq + carry + hard + soft + dcl + acc + dcc + incl_cost
    profit = revenue - cost
    # residual land value: max purchase price that still yields the target margin on cost
    non_land = hard + soft + dcl + acc + dcc + incl_cost + A["acquisition"]["demolition_per_site"]
    tgt = A["target_margin_on_cost"]
    # solve revenue/(1+tgt) = non_land + P*(1 + ptt_rate + closing + carry) ; approximate PTT at marginal blended 3%
    k = 1 + 0.03 + A["acquisition"]["closing_costs_pct"] + A["acquisition"]["carry_rate_annual"] * A["acquisition"]["carry_months"] / 12
    rlv = max(0.0, (revenue / (1 + tgt) - non_land) / k)
    return dict(gfa_sf=gfa, saleable_sf=saleable, units=units, price_psf=base_price,
                revenue=revenue, acquisition=acq + carry, hard=hard, soft=soft,
                levies=dcl + acc + dcc + incl_cost, total_cost=cost, profit=profit,
                margin=profit / cost if cost else np.nan,
                land_per_buildable=acq_price / gfa if gfa else np.nan,
                rlv_at_target=rlv, rlv_vs_assessed=rlv / assessed_total if assessed_total else np.nan)


# ---------------------------------------------------------------- main
def main():
    data = os.path.join(HERE, "data")
    out = os.path.join(HERE, "output")
    os.makedirs(out, exist_ok=True)

    tax = pd.read_csv(os.path.join(data, "tax_2026_land.csv"), dtype=str)
    par = pd.read_csv(os.path.join(data, "parcels.csv"), dtype={"tax_coord": str, "site_id": str, "civic_number": str})
    aux = json.load(open(os.path.join(data, "aux.json")))

    for c in ("current_land_value", "current_improvement_value"):
        tax[c] = pd.to_numeric(tax[c], errors="coerce").fillna(0)
    tax["year_built"] = pd.to_numeric(tax["year_built"], errors="coerce")
    levy_path = os.path.join(data, "tax_levy.csv")
    if os.path.exists(levy_path):
        lv = pd.read_csv(levy_path, dtype=str).drop_duplicates("land_coordinate")
        lv["tax_levy"] = pd.to_numeric(lv["tax_levy"], errors="coerce").fillna(0)
        tax = tax.merge(lv[["land_coordinate", "tax_levy"]], on="land_coordinate", how="left")
    else:
        tax["tax_levy"] = pd.to_numeric(tax.get("tax_levy", 0), errors="coerce").fillna(0)

    # one row per parcel (land_coordinate); several legal lots can share a polygon
    g = tax.groupby("land_coordinate").agg(
        pid=("pid", lambda s: "; ".join(sorted({str(x) for x in s if pd.notna(x)}))),
        n_lots=("pid", "size"),
        zone=("zoning_district", "first"),
        zclass=("zoning_classification", "first"),
        civic=("to_civic_number", "first"),
        civic_from=("from_civic_number", "first"),
        street=("street_name", "first"),
        postal=("property_postal_code", "first"),
        land_value=("current_land_value", "sum"),
        improvement_value=("current_improvement_value", "sum"),
        year_built=("year_built", "min"),
        tax_levy=("tax_levy", "sum"),
    ).reset_index()

    par = par.dropna(subset=["tax_coord"])
    par["area_m2"] = pd.to_numeric(par["area_m2"], errors="coerce")
    par["lat"] = pd.to_numeric(par["lat"], errors="coerce")
    par["lon"] = pd.to_numeric(par["lon"], errors="coerce")
    # --- resolve parcel geometry quirks ---
    # (a) one tax_coord drawn as several polygons -> sum their areas
    # (b) several tax_coords (air-space / stacked parcels) sharing one identical polygon -> one site, values summed
    par["geom_key"] = par["lat"].round(6).astype(str) + "," + par["lon"].round(6).astype(str) + "," + par["area_m2"].round(1).astype(str)
    geoms = par.drop_duplicates("geom_key").set_index("geom_key")["area_m2"]
    tc = par.groupby("tax_coord").agg(geom_keys=("geom_key", lambda s: "|".join(sorted(set(s)))),
                                      site_id=("site_id", "first"), civic_number=("civic_number", "first"),
                                      streetname=("streetname", "first"), lat=("lat", "mean"), lon=("lon", "mean")).reset_index()
    tc["area_m2"] = tc["geom_keys"].map(lambda k: float(sum(geoms[g] for g in k.split("|"))))
    g = g.merge(tc, left_on="land_coordinate", right_on="tax_coord", how="inner")
    # collapse stacked parcels sharing identical geometry into one site
    df = g.groupby("geom_keys").agg(
        land_coordinate=("land_coordinate", lambda s: "; ".join(sorted(set(s)))),
        pid=("pid", lambda s: "; ".join(sorted(set(s)))), n_lots=("n_lots", "sum"),
        zone=("zone", "first"), zclass=("zclass", "first"), civic=("civic", "first"), civic_from=("civic_from", "first"),
        street=("street", "first"), postal=("postal", "first"), land_value=("land_value", "sum"),
        improvement_value=("improvement_value", "sum"), year_built=("year_built", "min"), tax_levy=("tax_levy", "sum"),
        site_id=("site_id", "first"), civic_number=("civic_number", "first"), streetname=("streetname", "first"),
        lat=("lat", "first"), lon=("lon", "first"), area_m2=("area_m2", "first"), stacked_parcels=("tax_coord", "nunique"),
    ).reset_index(drop=True)

    civic = df["civic"].fillna(df["civic_from"]).fillna(df["civic_number"]).fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    street = df["street"].fillna(df["streetname"]).fillna("").astype(str).str.title()
    df["address"] = (civic + " " + street).str.strip()
    nociv = civic.eq("")
    df.loc[nociv, "address"] = df.loc[nociv, "address"].replace("", "Unknown") + " (no civic no.)"
    df["assessed_total"] = df["land_value"] + df["improvement_value"]
    df["imp_ratio"] = df["improvement_value"] / df["land_value"].replace(0, np.nan)
    df["site_sf"] = df["area_m2"] * SQFT_PER_M2
    df["frontage_m_est"] = df["area_m2"] / TYPICAL_LOT_DEPTH_M

    # local area (neighbourhood) by point-in-polygon
    lookup = build_area_lookup(aux["areas"])
    df["local_area"] = [lookup(lo, la) if pd.notna(lo) and pd.notna(la) else None for lo, la in zip(df["lon"], df["lat"])]

    # nearest SkyTrain station
    st = pd.DataFrame(aux["stations"]).dropna(subset=["lat", "lon"])
    lat = df["lat"].to_numpy()[:, None]; lon = df["lon"].to_numpy()[:, None]
    d = haversine_m(lat, lon, st["lat"].to_numpy()[None, :], st["lon"].to_numpy()[None, :])
    idx = np.nanargmin(np.where(np.isnan(d), np.inf, d), axis=1)
    df["nearest_station"] = st["station"].to_numpy()[idx]
    df["station_dist_m"] = d[np.arange(len(df)), idx]

    # plausibility: assessed land $/m2 far below its local-area/zone-class median usually means
    # leasehold, exempt (city/co-op/non-profit) or partial-interest records -> not acquirable at that price
    df["land_per_m2"] = df["land_value"] / df["area_m2"]
    grp = df.groupby(["local_area", "zclass"])["land_per_m2"]
    med = grp.transform("median").where(grp.transform("size") >= 30, df.groupby("local_area")["land_per_m2"].transform("median"))
    df["land_value_plausible"] = df["land_per_m2"] >= A["candidate_filter"]["min_land_per_m2_vs_median"] * med
    # tax-exempt (levy = 0): parks, schools, churches, government, non-profits -> not on the market
    df["tax_exempt"] = df["tax_levy"].fillna(0) <= 0
    # likely existing apartment building (rental replacement / tenant relocation policies apply)
    apt_zones = df["zone"].astype(str).str.match(r"^(RM-|R3-|R4-|R5-|FM-|RR-)")
    df["likely_existing_apartment"] = apt_zones & (df["area_m2"] >= 1200) & df["year_built"].between(1930, 1999)

    # candidate filter
    F = A["candidate_filter"]
    cand = (df["land_value_plausible"] & ~df["tax_exempt"] & ~(df["likely_existing_apartment"] & (not F["include_existing_apartments"])) &
            df["area_m2"].between(F["min_site_m2"], F["max_site_m2"])
            & (df["land_value"] >= F["min_land_value"])
            & ((df["imp_ratio"].fillna(0) <= F["max_improvement_to_land_ratio"])
               | (df["year_built"].fillna(1900) < F["year_built_cutoff"])))
    df["is_candidate"] = cand

    # ---- outright zoning option
    rows = []
    west = set(A["westside_areas"])
    for r in df.itertuples(index=False):
        opt = rule_for(r.zone, r.area_m2, r.frontage_m_est)
        if opt is None or not r.is_candidate or r.local_area is None:
            rows.append(None); continue
        incl = opt["incl"]
        if r.zone == "R1-1" and r.local_area in west and r.area_m2 >= A["inclusionary"]["R1-1_westside_large_lot_min_m2"]:
            incl = "R1-1_westside_cash"
        pf = proforma(r.site_sf, opt["fsr"], opt["typology"], opt["tenure"], r.local_area, r.zone, incl,
                      r.assessed_total, is_mixed_use(r.zone))
        pf.update(fsr=opt["fsr"], typology=opt["typology"], tenure=opt["tenure"], storeys=opt["storeys"], zoning_note=opt["note"],
                  incl=incl or "")
        rows.append(pf)
    oz = pd.DataFrame([x if x else {} for x in rows], index=df.index)
    for c in oz.columns:
        df["oz_" + c] = oz[c]

    # ---- TOA rezoning upside (separate scenario)
    toa_rows = []
    for r in df.itertuples(index=False):
        tier = next((t for t in A["toa"]["tiers"] if r.station_dist_m <= t["max_m"]), None)
        if tier is None or not r.is_candidate or r.local_area is None or r.area_m2 < tier["min_site_m2"] \
                or not (str(r.zone).startswith(("R", "C-"))):
            toa_rows.append(None); continue
        pf = proforma(r.site_sf, tier["fsr"], tier["typology"], "rental", r.local_area, r.zone, "TOA",
                      r.assessed_total, False)
        pf.update(fsr=tier["fsr"], typology=tier["typology"], tier=tier["label"])
        toa_rows.append(pf)
    tz = pd.DataFrame([x if x else {} for x in toa_rows], index=df.index)
    for c in ("fsr", "typology", "tier", "gfa_sf", "revenue", "total_cost", "profit", "margin"):
        df["toa_" + c] = tz[c] if c in tz else np.nan

    # ---- optional listings flag
    lst_path = os.path.join(data, "listings.csv")
    df["listed"] = False; df["list_price"] = np.nan; df["listing_url"] = ""
    if os.path.exists(lst_path):
        ls = pd.read_csv(lst_path, dtype=str)
        ls["key"] = ls["address"].map(norm_addr)
        df["key"] = df["address"].map(norm_addr)
        m = df.merge(ls[["key", "list_price", "url"]].drop_duplicates("key"), on="key", how="left", suffixes=("", "_l"))
        df["listed"] = m["list_price_l"].notna().to_numpy() if "list_price_l" in m else m["list_price"].notna().to_numpy()
        df["list_price"] = pd.to_numeric(m["list_price_l"] if "list_price_l" in m else m["list_price"], errors="coerce").to_numpy()
        df["listing_url"] = m["url"].fillna("").to_numpy()
        df.drop(columns=["key"], inplace=True)
        # re-run the pro forma at the actual asking price for listed sites
        ask_profit, ask_margin = [], []
        for r in df.itertuples(index=False):
            if r.listed and r.list_price and r.list_price > 0 and pd.notna(r.oz_fsr) and r.local_area:
                incl = r.oz_incl if isinstance(r.oz_incl, str) and r.oz_incl else None
                pf = proforma(r.site_sf, r.oz_fsr, r.oz_typology, r.oz_tenure, r.local_area, r.zone,
                              incl, r.assessed_total, is_mixed_use(r.zone), price_override=float(r.list_price))
                ask_profit.append(pf["profit"]); ask_margin.append(pf["margin"])
            else:
                ask_profit.append(np.nan); ask_margin.append(np.nan)
        df["ask_profit"] = ask_profit; df["ask_margin"] = ask_margin
    else:
        df["ask_profit"] = np.nan; df["ask_margin"] = np.nan

    # ---- ranking
    scored = df[df["oz_profit"].notna()].copy()
    tgt = A["target_margin_on_cost"]
    scored["clears_target"] = scored["oz_margin"] >= tgt
    scored = scored.sort_values("oz_profit", ascending=False)
    scored["rank_profit"] = np.arange(1, len(scored) + 1)
    scored["rank_margin"] = scored["oz_margin"].rank(ascending=False, method="first").astype(int)
    scored["best_profit"] = scored[["oz_profit", "toa_profit"]].max(axis=1)
    scored["best_basis"] = np.where(scored["toa_profit"].fillna(-1e18) > scored["oz_profit"], "TOA rezoning", "Outright zoning")

    cols = ["rank_profit", "rank_margin", "address", "postal", "local_area", "zone", "zclass", "pid", "n_lots", "stacked_parcels", "likely_existing_apartment", "tax_exempt",
            "area_m2", "site_sf", "frontage_m_est", "land_value", "improvement_value", "assessed_total", "year_built",
            "oz_fsr", "oz_typology", "oz_tenure", "oz_storeys", "oz_zoning_note", "oz_gfa_sf", "oz_saleable_sf", "oz_units",
            "oz_price_psf", "oz_revenue", "oz_acquisition", "oz_hard", "oz_soft", "oz_levies", "oz_total_cost",
            "oz_profit", "oz_margin", "oz_land_per_buildable", "oz_rlv_at_target", "oz_rlv_vs_assessed", "clears_target",
            "nearest_station", "station_dist_m", "toa_tier", "toa_fsr", "toa_typology", "toa_gfa_sf", "toa_revenue",
            "toa_total_cost", "toa_profit", "toa_margin", "best_profit", "best_basis",
            "listed", "list_price", "listing_url", "ask_profit", "ask_margin", "lat", "lon", "land_coordinate"]
    scored = scored[cols]
    scored.to_csv(os.path.join(out, "all_scored.csv"), index=False)

    top = scored[scored["clears_target"]].head(100) if scored["clears_target"].sum() >= 100 else scored.head(100)
    top = top.copy(); top["rank"] = np.arange(1, len(top) + 1)
    top.to_csv(os.path.join(out, "top100.csv"), index=False)
    top_json = top.replace({np.nan: None}).to_dict(orient="records")
    json.dump(top_json, open(os.path.join(out, "top100.json"), "w"), default=float)

    summary = {
        "parcels_total": int(len(df)), "parcels_candidates": int(df["is_candidate"].sum()),
        "parcels_scored": int(len(scored)), "clearing_target": int(scored["clears_target"].sum()),
        "target_margin": tgt,
        "by_zone_top100": top["zone"].value_counts().to_dict(),
        "by_area_top100": top["local_area"].value_counts().to_dict(),
        "by_typology_top100": top["oz_typology"].value_counts().to_dict(),
        "median_profit_top100": float(top["oz_profit"].median()),
        "median_margin_top100": float(top["oz_margin"].median()),
    }
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=2)
    print(json.dumps(summary, indent=2))
    print(top[["rank", "address", "local_area", "zone", "area_m2", "assessed_total", "oz_fsr", "oz_typology",
               "oz_profit", "oz_margin"]].head(25).to_string(index=False))


def norm_addr(s):
    s = str(s).upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(STREET|ST)\b", "ST", s); s = re.sub(r"\b(AVENUE|AVE|AV)\b", "AVE", s)
    s = re.sub(r"\b(DRIVE|DR)\b", "DR", s); s = re.sub(r"\b(ROAD|RD)\b", "RD", s)
    s = re.sub(r"\b(BOULEVARD|BLVD)\b", "BLVD", s); s = re.sub(r"\b(PLACE|PL)\b", "PL", s)
    s = re.sub(r"\b(EAST|E)\b", "E", s); s = re.sub(r"\b(WEST|W)\b", "W", s)
    s = re.sub(r"\b(VANCOUVER|BC|BRITISH COLUMBIA|V\d[A-Z] ?\d[A-Z]\d)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # canonical direction placement: "3692 W 19TH AVE" and "3692 19TH AVE W" -> "3692 19TH AVE W"
    m = re.match(r"^(\d+[A-Z]?) (E|W|N|S) (.+)$", s)
    if m:
        s = f"{m.group(1)} {m.group(3)} {m.group(2)}"
    return s


if __name__ == "__main__":
    main()
