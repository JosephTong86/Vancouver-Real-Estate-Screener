#!/usr/bin/env python3
"""
Score the inner-ring municipalities (Burnaby, Richmond, New Westminster, North Vancouver City & District).

Reads:  data/metro/<city>.csv (from fetch_metro.py), assumptions.json, metro_config.py, zoning_metro.py
Writes: output/metro/<city>_scored.csv, output/metro/all_scored.csv, output/metro_summary.json

Same residual-land-value pro forma as score.py (Vancouver), with three differences that are flagged on every row:
  * land value is modelled from the GVR HPI benchmark and lot size (grade C), not read from the assessment roll;
  * city fees come from each municipality's own DCC / ACC / SSAC schedules (per unit, per sf or per m2);
  * zoning entitlements come from zoning_metro.py (grades A-D per rule).
"""
import json, math, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import ptt_bc, A, SQFT_PER_M2, TYPICAL_LOT_DEPTH_M          # noqa: E402
from metro_config import CITIES, METRO_DCC, TRANSLINK, PERMITS_MISC_PER_UNIT, LAND_ELASTICITY, sub_area, burnaby_quadrant   # noqa: E402
from zoning_metro import rule_for, toa_tier                            # noqa: E402

DATA = os.path.join(HERE, "data", "metro")
OUT = os.path.join(HERE, "output", "metro")
os.makedirs(OUT, exist_ok=True)

GROUND = ("duplex", "multiplex", "townhouse")


def price_for(cfg, area, typology):
    row = cfg["prices"].get(area) or next(iter(cfg["prices"].values()))
    return row[0] if typology in GROUND else (row[1] if typology == "woodframe" else row[2])


def city_fees(cfg, typology, gfa_sf, units, queensborough=False):
    T = A["typologies"][typology]
    f = cfg["fees"].get(typology, 0) * units
    if "fees_per_sf" in cfg:
        f += cfg["fees_per_sf"].get(typology, 0) * gfa_sf
    if "fees_per_m2" in cfg:
        tbl = cfg["fees_per_m2_queensborough"] if queensborough and "fees_per_m2_queensborough" in cfg else cfg["fees_per_m2"]
        f += tbl.get(typology, 0) * gfa_sf / SQFT_PER_M2
    f += units * (METRO_DCC[cfg["metro"]][T["dcc_type"]] + TRANSLINK[T["dcc_type"]] + PERMITS_MISC_PER_UNIT)
    return f


def proforma_city(cfg, site_sf, fsr, typology, tenure, area, incl, acq_price, mixed_use, queensborough=False, units_cap=None):
    T = A["typologies"][typology]
    gfa = site_sf * fsr
    saleable = gfa * T["eff"]
    units = max(1, round(saleable / T["unit_sf"]))
    if units_cap:
        units = min(units, units_cap)
    base_price = price_for(cfg, area, typology)
    res_share = 1.0 - (A["commercial_share_mixed_use"] if mixed_use else 0.0)
    revenue = saleable * res_share * base_price + saleable * (1 - res_share) * base_price * A["commercial_price_factor"]
    if tenure == "rental":
        revenue *= A["rental_value_factor"]
    if incl and str(incl).startswith("share_belowmarket:"):
        share = float(str(incl).split(":")[1])
        revenue *= 1 - share * (1 - A["toa"]["below_market_value_factor"])
    acq = acq_price + ptt_bc(acq_price) + acq_price * A["acquisition"]["closing_costs_pct"] + A["acquisition"]["demolition_per_site"]
    carry = acq_price * A["acquisition"]["carry_rate_annual"] * A["acquisition"]["carry_months"] / 12
    hard = gfa * T["hard"] * cfg["hard_factor"]
    soft = hard * A["soft_cost_pct_of_hard"]
    fees = city_fees(cfg, typology, gfa, units, queensborough)
    cost = acq + carry + hard + soft + fees
    profit = revenue - cost
    non_land = hard + soft + fees + A["acquisition"]["demolition_per_site"]
    tgt = A["target_margin_on_cost"]
    k = 1 + 0.03 + A["acquisition"]["closing_costs_pct"] + A["acquisition"]["carry_rate_annual"] * A["acquisition"]["carry_months"] / 12
    rlv = max(0.0, (revenue / (1 + tgt) - non_land) / k)
    return dict(gfa_sf=gfa, saleable_sf=saleable, units=units, price_psf=base_price, revenue=revenue,
                acquisition=acq + carry, hard=hard, soft=soft, levies=fees, total_cost=cost, profit=profit,
                margin=profit / cost if cost else np.nan, land_per_buildable=acq_price / gfa if gfa else np.nan,
                rlv_at_target=rlv, rlv_vs_assessed=rlv / acq_price if acq_price else np.nan)


def score_city(city):
    cfg = CITIES[city]
    path = os.path.join(DATA, f"{city}.csv")
    if not os.path.exists(path):
        print(f"-- {cfg['label']}: no data file, skipped")
        return None
    df = pd.read_csv(path, dtype={"pid": str, "zone": str, "overlay": str, "ocp": str, "address": str}, low_memory=False)
    for c in ("site_m2", "frontage_m", "lat", "lon", "station_dist_m", "year_built", "existing_fsr"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["strata"] = df["strata"].astype(str).str.lower().isin(("true", "1", "y", "yes"))
    df["zone"] = df["zone"].fillna("").astype(str)
    df["address"] = df["address"].fillna("").astype(str)
    df.loc[df["address"].str.strip() == "", "address"] = "PID " + df["pid"].fillna("").astype(str).str.replace(r"(\d{3})(\d{3})(\d{3})", r"\1-\2-\3", regex=True)
    df["site_sf"] = df["site_m2"] * SQFT_PER_M2
    df["frontage_m_est"] = df["frontage_m"].fillna(df["site_m2"] / TYPICAL_LOT_DEPTH_M)
    df["local_area"] = [sub_area(city, la, lo, nb if isinstance(nb, str) else "", sd, z)
                        for la, lo, nb, sd, z in zip(df["lat"], df["lon"], df["neighbourhood"], df["station_dist_m"], df["zone"])]

    # ---- modelled land value (grade C): HPI benchmark detached x (site / reference lot) ^ 0.55
    res_mask = df["zone"].str.upper().str.match(r"^(R|RS|RSM|RD|RGO|RT|NR|RQ|GO)") & df["site_m2"].between(250, 1500)
    ref = float(df.loc[res_mask, "site_m2"].median()) if res_mask.sum() > 100 else 557.0
    hpi = df["local_area"].map(lambda a: cfg["hpi_detached"].get(a) or next(iter(cfg["hpi_detached"].values())))
    df["land_value_model"] = hpi * (df["site_m2"].clip(lower=150) / ref) ** LAND_ELASTICITY
    df["land_ref_m2"] = ref

    # ---- candidate filter (mirrors Vancouver's, minus the assessment-based tests we cannot run)
    F = A["candidate_filter"]
    lu = df["landuse"].fillna("").astype(str).str.upper()
    excl_use = lu.str.contains("PARK|SCHOOL|INSTITUT|CHURCH|CEMET|UTILIT|GOVERN|HOSPITAL", regex=True)
    heritage = df["heritage"].fillna("").astype(str).str.strip().ne("") if "heritage" in df else pd.Series(False, index=df.index)
    owner_ok = ~df["owner_type"].fillna("Unknown").isin(["Local Government", "Crown Provincial", "Crown Federal", "Crown Agency", "Crown Municipal", "First Nation", "Untitled Provincial"])
    built_out = (df["year_built"].fillna(1900) >= F["year_built_cutoff"]) | (df["existing_fsr"].fillna(0) > 0.9)
    df["is_candidate"] = owner_ok & ~df["strata"] & ~excl_use & ~heritage & ~built_out & df["site_m2"].between(F["min_site_m2"], F["max_site_m2"])

    # ---- outright option
    rows, toa_rows = [], []
    for r in df.itertuples(index=False):
        tier = toa_tier(r.station_kind, r.station_dist_m) if pd.notna(r.station_dist_m) else None
        ftn = (city == "newwest" and r.zone == "RGO-B") or (city == "cnv" and str(r.ocp).upper() in ("LRN2", "R4"))
        ctx = dict(overlay=r.overlay if isinstance(r.overlay, str) else "", ocp=r.ocp if isinstance(r.ocp, str) else "",
                   ftn=ftn, toa_tier=tier["tier"] if tier else None, zcat=r.zcat,
                   quadrant=burnaby_quadrant(r.lat, r.lon) if city == "burnaby" else "")
        opt = rule_for(city, r.zone, r.site_m2, r.frontage_m_est, ctx)
        qb = r.local_area == "Queensborough"
        if opt is None or not r.is_candidate:
            rows.append(None)
        else:
            # pre-zoned apartment / commercial land: vendor wants max(house value, $/buildable)
            acq = r.land_value_model
            if opt["typology"] not in GROUND:
                acq = max(acq, cfg["land_bsf"].get(opt["typology"], 100) * r.site_sf * opt["fsr"])
                land_grade = "D"
            else:
                land_grade = cfg["grade_land"]
            pf = proforma_city(cfg, r.site_sf, opt["fsr"], opt["typology"], opt["tenure"], r.local_area, opt.get("incl"),
                               acq, opt.get("mixed_use", False), qb, units_cap=opt.get("units"))
            pf.update(fsr=opt["fsr"], typology=opt["typology"], tenure=opt["tenure"], storeys=opt["storeys"],
                      zoning_note=opt["note"], incl=opt.get("incl") or "", grade=opt["grade"], land_grade=land_grade, acq_price=acq)
            rows.append(pf)
        # TOA rezoning upside (provincial minimums; needs a rezoning + inclusionary housing)
        if tier and r.is_candidate and r.site_m2 >= tier["min_site_m2"] and str(r.zone).upper()[:1] in ("R", "C", "G", "N", "M"):
            incl = f"share_belowmarket:{cfg['inclusionary_toa']}" if cfg["inclusionary_toa"] else None
            acq = max(r.land_value_model, cfg["land_bsf"].get(tier["typology"], 100) * r.site_sf * tier["fsr"] * 0.8)
            pf = proforma_city(cfg, r.site_sf, tier["fsr"], tier["typology"], "strata", r.local_area, incl, acq, False, qb)
            pf.update(fsr=tier["fsr"], typology=tier["typology"], tier=tier["label"])
            toa_rows.append(pf)
        else:
            toa_rows.append(None)
    oz = pd.DataFrame([x if x else {} for x in rows], index=df.index)
    for c in oz.columns:
        df["oz_" + c] = oz[c]
    tz = pd.DataFrame([x if x else {} for x in toa_rows], index=df.index)
    for c in ("fsr", "typology", "tier", "gfa_sf", "revenue", "total_cost", "profit", "margin"):
        df["toa_" + c] = tz[c] if c in tz else np.nan

    scored = df[df["oz_profit"].notna()].copy()
    tgt = A["target_margin_on_cost"]
    scored["clears_target"] = scored["oz_margin"] >= tgt
    scored = scored.sort_values("oz_profit", ascending=False)
    scored["rank_profit"] = np.arange(1, len(scored) + 1)
    scored["rank_margin"] = scored["oz_margin"].rank(ascending=False, method="first").astype(int)
    scored["best_profit"] = scored[["oz_profit", "toa_profit"]].max(axis=1)
    scored["best_basis"] = np.where(scored["toa_profit"].fillna(-1e18) > scored["oz_profit"], "TOA rezoning", "Outright zoning")
    scored["city_label"] = cfg["label"]
    scored["assessed_total"] = scored["oz_acq_price"]   # modelled acquisition value stands in for the assessment roll
    scored["land_value"] = scored["land_value_model"]
    scored["improvement_value"] = np.nan
    scored.to_csv(os.path.join(OUT, f"{city}_scored.csv"), index=False)
    top = scored[scored["clears_target"]].head(100) if scored["clears_target"].sum() >= 100 else scored.head(100)
    top = top.copy(); top["rank"] = np.arange(1, len(top) + 1)
    keep_cols = ["rank", "address", "pid", "zone", "local_area", "site_m2", "assessed_total", "land_value", "oz_fsr", "oz_typology", "oz_storeys", "oz_units",
                 "oz_gfa_sf", "oz_price_psf", "oz_revenue", "oz_acquisition", "oz_hard", "oz_soft", "oz_levies", "oz_total_cost", "oz_profit", "oz_margin",
                 "oz_rlv_at_target", "oz_grade", "oz_land_grade", "oz_zoning_note", "nearest_station", "station_dist_m", "toa_tier", "toa_profit", "toa_margin", "lat", "lon"]
    top[[c for c in keep_cols if c in top.columns]].to_csv(os.path.join(OUT, f"{city}_top100.csv"), index=False)
    summ = {
        "city": cfg["label"], "parcels_total": int(len(df)), "parcels_with_zone": int((df["zone"] != "").sum()),
        "parcels_candidates": int(df["is_candidate"].sum()), "parcels_scored": int(len(scored)),
        "positive_margin": int((scored["oz_margin"] > 0).sum()), "clearing_target": int(scored["clears_target"].sum()),
        "median_profit_top100": float(top["oz_profit"].median()) if len(top) else None,
        "median_margin_top100": float(top["oz_margin"].median()) if len(top) else None,
        "by_zone_top100": top["zone"].value_counts().head(12).to_dict(),
        "by_typology_top100": top["oz_typology"].value_counts().to_dict(),
        "land_ref_m2": ref, "grade_land": cfg["grade_land"], "grade_zoning": cfg["grade_zoning"],
        "zones_seen": df["zone"].value_counts().head(30).to_dict(),
    }
    print(f"-- {cfg['label']}: {len(df):,} parcels, {int(df['is_candidate'].sum()):,} candidates, {len(scored):,} scored, "
          f"{summ['positive_margin']:,} positive, {summ['clearing_target']:,} clear 15%; ref lot {ref:.0f} m2")
    print(top[["address", "zone", "site_m2", "assessed_total", "oz_fsr", "oz_typology", "oz_profit", "oz_margin"]].head(8).to_string(index=False))
    return scored, summ


def main():
    frames, summary = [], {}
    for city in CITIES:
        res = score_city(city)
        if res:
            s, summ = res
            frames.append(s); summary[city] = summ
    if frames:
        allc = pd.concat(frames, ignore_index=True)
        allc = allc.sort_values("oz_profit", ascending=False)
        allc["rank_region"] = np.arange(1, len(allc) + 1)
        allc.to_csv(os.path.join(OUT, "all_scored.csv"), index=False)
    json.dump(summary, open(os.path.join(HERE, "output", "metro_summary.json"), "w"), indent=2, default=float)
    print(json.dumps({k: {kk: v[kk] for kk in ("parcels_total", "parcels_candidates", "parcels_scored", "positive_margin", "clearing_target")} for k, v in summary.items()}, indent=1))


if __name__ == "__main__":
    main()
