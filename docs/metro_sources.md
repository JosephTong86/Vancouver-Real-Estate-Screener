# Inner-ring municipalities: data sources, zoning rules and grades

Research compiled 3 November 2026 for `fetch_metro.py`, `zoning_metro.py` and `metro_config.py`.
Grades: **A** read from consolidated bylaw / statute text · **B** city bulletin, council report or reputable secondary source · **C** derived or modelled · **D** placeholder to verify.

## Why land values are modelled outside Vancouver

Only the City of Vancouver publishes BC Assessment land and improvement values per parcel as open data (property-tax-report). Burnaby, Richmond, New Westminster and both North Vancouvers publish parcels and (mostly) zoning, but no assessed values; BC Assessment's parcel-level "Data Advice" is a licensed product (UBC Library holds it under a research licence that forbids republishing). The screener therefore models the acquisition price as

    value = HPI_detached(sub-area, Sep 2026) × (site_m2 / reference_lot_m2) ^ 0.55

The 0.55 elasticity is the within-neighbourhood regression of log assessed value on log lot area across 61,000 Vancouver R1-1 lots (range 0.39 South Cambie – 0.90 Kitsilano). Reference lot = the municipality's median residential lot. Pre-zoned apartment / commercial land is valued at no less than a $/buildable-sf figure (grade D). Improvement values and year built are unknown except in New Westminster (building footprints carry a construction year), so "already rebuilt" lots cannot be screened out as they are in Vancouver.

## Parcel and zoning endpoints

| City | Parcels | Zoning | Extra |
|---|---|---|---|
| Burnaby | ParcelMap BC WFS, `MUNICIPALITY LIKE 'Burnaby%'`, PARCEL_CLASS Subdivision (35,770) | `gis.burnaby.ca/arcgis/rest/services/OpenData/OpenData1/MapServer/8` (ZONECODE, OVERLAY_ZONE; republished 9 Jul 2026, 8 days after the new bylaw) | Legal Parcels `OpenData4/MapServer/7` (LTO_PID, ADDRESS, STRATA, LOT_WIDTH) joined on PID; SkyTrain `OpenData5/MapServer/10` |
| Richmond | ParcelMap BC WFS, `'Richmond, City%'` (96,330 polygons incl. strata; ~35,600 lots) | **No open zoning layer** (RIM services are token-locked). MountainMath / UBC Metro Vancouver Zoning Project aggregate GeoJSON (c. 2020), RS1/RS2 remapped to the June 2024 RSM pre-zoning outside TOAs | Canada Line stations from the regional station layer |
| New Westminster | `services3.arcgis.com/A7O8YnTNtzRPIn7T/.../Properties/FeatureServer/0`, `FEATURETYPE='PARCEL' AND LEGAL_TYPE='LAND'` (8,309), carries ZONING, SITEAREA, FRONTAGE, PID, NGBRHOOD | on the parcel (incl. RGO-A / RGO-B infill zones, June 2026) | `Building_Footprints2` BLDGAGE = year built; `Skytrain_Station_Pts` (52 regional stations) |
| North Vancouver City | ParcelMap BC WFS `'North Vancouver, City%'`; address from `gisext2.cnv.org/.../query_layers/MapServer/2` | `query_layers/MapServer/16` (ZONING; 683 polygons incl. the 14 GO polygons of Dec 2025) | OCP `CityMapPro/MapServer/27` (LRN1 / LRN2 decides 4 vs 6 units) |
| North Vancouver District | ParcelMap BC WFS `'North Vancouver%District%'` (38,044 polygons) | `geoweb.dnv.org/arcgis/rest/services/Data_DynamicLayers_Zoning/MapServer/0` (Zoning; 2,616 polygons, R1/R2 since 20 Jul 2026) | OCP `Data_DynamicLayers_OCP/MapServer/0` (OCPClass) |

Licences: Open Government Licence – BC (ParcelMap BC), Open Government Licence – Burnaby / New Westminster / North Vancouver; CNV services carry no licence string (publicly served, terms per CityMap disclaimer); MountainMath file has no stated licence (academic project).

## Zoning rules encoded (zoning_metro.py)

**Burnaby — Zoning Bylaw 2026 (No. 14815), in force 1 Jul 2026.** Height-based districts with no FAR: R1 SSMUH (3 units ≤280 m², 4 above, 6 within a frequent-transit area; 3 storeys / 10 m after the Oct 2025 amendments; coverage 40–45 %) → derived FSR ≈1.0 (C); R2 townhouse 4 st (derived 1.3, C); R3 4 st; R4 6 st (8 in a TOA); R5 12 st; R6 20 st; R7 30 st; R8 40 st — floor area built up from 55 % coverage to storey 6 (plate ≤1,400 m²), 45 % to storey 12, then a 900 m² tower plate, capped at FSR 10 (C). C1/C2/E1 bases take the height of their R overlay with ≥60 % commercial ground floor. "r" suffix = rental only. Inclusionary rental 10 % of units (NW/SW) or 5 % (NE/SE) in R5–R8. TOAs (Bylaw 14665): 11 SkyTrain stations, provincial minimums at rezoning only. Fees: DCC 14645 + ACC 14646 per unit (low 81,833 / medium 56,297 / high 38,841), SSAC SD41, Metro Vancouver (Vancouver Sewerage Area) and TransLink. Sources: burnaby.ca zoning-bylaw PDFs (Parts 1, 2, 4, 5), provincial-housing-legislation-changes page, development-funding-program page, Oct 16 2025 council news, GVR HPI Sep 2026.

**Richmond — Zoning Bylaw 8500.** RSM/S-M-L-XL pre-zoned June 2024 (Bylaw 10573): 3/4/6 units, FAR 0.60 on the first 464.5 m² + 0.30 on the balance + 50 m², 2.5 st / 10 m, **units may not be stratified** (modelled as rental, which is why RSM rarely pencils); RS lots inside the five Canada Line TOAs kept RS zoning (single-detached, not scored). RD duplex 0.55; RTL 0.55–0.60 (+0.1 former bonus folded in by Bylaw 10760); RTM 0.65–0.70 (+0.1); RTH 0.75–0.90 (+0.1); RTP4 1.2 (+0.1); RAL1 0.8 (+0.2); RAM1 stepped 0.6/0.9/1.2 (+0.2); RAH1/2 2.0 (+0.2), min 2,400 m²; RCL1–5 2.0–2.5; CDT1 3.0; CS2/3 1.0; site-specific ZS/ZD/ZT/ZLR/ZHR/ZMU not scored. TOAs (Bylaw 10560) rezoning-based; LEMR 15 % of floor area in City Centre rezonings. Fees: DCC Bylaw 9499 (TH $33.79/sf, apt $35.79/sf, SSMUH $33.65/sf pending Bylaw 10732), **no ACC**, SSAC SD38, Metro (Lulu Island West) and TransLink. Sources: richmond.ca bylaw 8500 part PDFs, Bulletins Planning-08/09, INFO-58/60/22, council minutes 2 Mar & 19 May 2026.

**New Westminster — Zoning Bylaw 6680 consolidated 8 Jun 2026.** RGO-A 4 units / FSR 0.8 and RGO-B 6 units / FSR 1.0 (Bylaw 8578, ~3,000 lots, strata permitted, DP only) (A); RT-A/RT-B townhouse FSR 1.2 / 12 m, min 836 m² & 20 m frontage (A); RT-2 series base 0.6 (bonus to 1.2 by cash not modelled); RT-3 series 0.62–0.90; RM-1 family 1.2; RM-2 1.2 / 10.67 m; RM-2A/5/5A taken as 1.2 (D); C-4 residential base 1.2 → 3.0 by lot size (A), C-8 1.2, C-3A 5.0, C-3 3.0 (D), C-4A 3.2, C-5 3.0, C-6 2.2, C-2A ≈1.5 (C), C-2 ≈1.2 (C). RS/NR/RQ (0.5, house + suite), RT-1, high-rise RM-3/4/6 and CD zones not scored. TOD areas are OCP designations only (rezoning required). Queensborough exempt from SSMUH to 2029. Fees: DCC per m² GFA (TH 105.04, apt 142.72; Queensborough 137.49 / 156.32), ACC per m² GFA (TH 240.56, apt 330.32), SSAC SD40, Metro (Fraser Sewerage Area) and TransLink; Inclusionary Housing Policy 10 % of units on rezonings. Sources: newwestcity.ca 300/400/500-series PDFs, infillhousing page, DCC/ACC rate tables, Inclusionary Housing Policy, GVR HPI.

**City of North Vancouver — Zoning Bylaw 6700, GO & MID zones (Bylaw 9137, 8 Dec 2025).** GO: 3 units ≤280 m²; 4 units (FSR 0.85) in OCP LRN1; 6 units (FSR 1.0) in LRN2 / Residential Level 4; 3 storeys; strata permitted (A). MID: 2.6 FSR, 6 st / 21 m outright, inclusionary 2 % strata (A). RM-1 1.6 (B); RM-2 1.6 with bonus items (B); RG-2/3/4 0.75/1.0/1.25 (B). RH-1, C-1A/B, C-2, LL-x and CD zones not scored (densities via OCP bonus + rezoning). TOA: Lonsdale Quay bus exchange (tiers 4/5), rezoning-based. Fees: DCC Bylaw 8471 as amended Nov 2025 per unit (TH 14,884; apt 12,593; apt 5+ st 10,304), no ACC (density-bonus CAC applies to bonus floor area only), no SD44 SSAC found, Metro (North Shore) and TransLink. Sources: cnv.org Bylaw 9137 extract, GO handout, OCP Bylaw 9114, DCC 8471-C, Inclusionary Housing Policy M7, B.C. Reg. 263/2023.

**District of North Vancouver — Zoning Bylaw 3210, R1/R2 (Bylaw 8799, 20 Jul 2026).** R2: house + secondary suite + coach house, max GFA 0.70×lot + 139.4 m² (≤464.5 m²) or 0.55×lot + 139.4 m² capped at 696.8 m², 3 storeys (A) — modelled as a single-lot "house + coach" sale. Council resolved **not** to implement SSMUH (13 Apr 2026), so no 4/6-unit multiplex is outright. RM/RL/RH and C zones (Part 5 not retrievable) and CD zones not scored. TOAs: Phibbs Exchange and Capilano University (bus-exchange tiers), rezoning-based. Fees: DCC (Dec 2024) + ACC (Feb 2025) per unit (SF 43,533 + 41,358; TH 27,644 + 37,221; apt 19,625 + 26,193; coach house 75 % of apt DCC, ACC exempt) (B), Metro (North Shore) and TransLink. Sources: docs.dnv.org bylaw-3210.pdf, zoning-guide-section-525.pdf, Schedule A to Bylaw 8799, council minutes 13 Apr 2026, UDI update on DCC/ACC.

## Prices (achievable 2026 $/sf saleable; grade C unless noted)

Burnaby North/South/East ground-oriented 900–1,000, wood-frame 950–1,020, concrete 1,000–1,100 (resale median $904/sf, zealty Sep 2026; Metrotown presale $1,225–1,450/sf in 2023, down 6–10 % since). Richmond City Centre 1,000 / 850 / 1,080, elsewhere 950 / 780 / 950 (new-build listings $1,050–1,210/sf City Centre, $690–810 Hamilton). New Westminster 760 / 800 / 900 (Downtown 780 / 850 / 950; Queensborough 700 / 750 / 850). North Vancouver City 1,000 / 1,060 / 1,280 (Lonsdale 1,050 / 1,150 / 1,350; One20 presale ≈$1,100–1,340/sf). North Vancouver District 1,050 / 1,030 / 1,000. HPI benchmark detached, September 2026 (GVR): Burnaby North $1,808,500, South $1,894,600, East $1,694,900; Richmond $1,871,100; New Westminster $1,356,900; North Vancouver (City + District) $2,042,000 (B).

## Known gaps (grade D or unverified)

* Burnaby: exact post-Oct-2025 R1 lot-coverage table; July 2026 ACC amendment content; whether the open zoning layer carries the new R1–R8 codes (the fetch log prints the zone codes seen — if RM3/C3-style codes appear, the legacy mapping in `zoning_metro.py` is used).
* Richmond: zoning vintage (c. 2020) and MountainMath field names (detected heuristically at run time); adoption of Bylaws 10760 (bonus removal) and 10732 (SSMUH DCC).
* New Westminster: RM-2A / RM-3 / RM-4 / RM-5 / RM-6 / RMW densities (400-series sections 431–480 not read); handling of lots ≤280 m² inside RGO-A.
* CNV: RH-1 and Lonsdale commercial zone densities; FTN boundary taken from OCP LRN2 polygons.
* DNV: Part 5 multi-family densities; adopted DCC/ACC rate schedules; whether the Province has imposed SSMUH since September 2026.
* All: no year-built / improvement data except New Westminster, so recently rebuilt houses are not screened out; frequent-transit (6-unit) eligibility is only known for New Westminster (RGO-B) and CNV (LRN2) — Burnaby and Richmond lots are scored at 4 units.

---

# Batch 2 (research 4 Nov 2026): Surrey, Coquitlam, Port Moody, Delta, West Vancouver, Langley City, Langley Township, Maple Ridge

## Parcel and zoning endpoints

| City | Parcels | Zoning | Enrichment |
|---|---|---|---|
| Surrey | ParcelMap BC `'Surrey, City%'` (202,164 polygons, Subdivision class filtered) | `gisservices.surrey.ca/arcgis/rest/services/OpenData/MapServer/239` (ZONING_TEXT; 4,277; MR renaming of 15 Jun 2026 present) | Lots `Lots/MapServer/7` (PID→MSLINK) → Address Points `OpenData/MapServer/138` (LOT_LINK, HOUSE_NO, GCROADS) and Frequent Bus Stop Eligible Lots `Public/Planning/MapServer/64` (6-unit SSMUH eligibility); TOA Properties `Planning/MapServer/61` |
| Coquitlam | ParcelMap BC `'Coquitlam, City of'` (62,426) | `geodata.coquitlam.ca/arcgis/rest/services/DynamicServices/Planning/MapServer/1` (ZONING; 1,087; `where=OBJECTID>0`) | Property Information `Cadastral/MapServer/15` (PID, ADDRESS) |
| Port Moody | ParcelMap BC `'Port Moody, City of'` (15,500) | `services9.arcgis.com/XMHGoEc3tdJ8TphG/ArcGIS/rest/services/Zoning/FeatureServer/3` (zoning; 957) | `Parcel_Information/FeatureServer/0` (pid, address, legal_type); SSMUH areas `Provincial_Housing_Statutes_Mapping/FeatureServer/7` (Bill44 3/4/6 units) |
| Delta | City Hub `services9.arcgis.com/w2mu7sRltY6PiQ7J/.../Property_Parcels/FeatureServer/0` (52,330 rows incl. strata units; PID, CIVIC_ADDRESS, ZONING, OCPDES, ALR, FLOODPLN, SCOTTSDALE, SSMUHUNITAREA) + ParcelMap BC `'Delta, City of'` (38,666) for owner type | on the parcel | — |
| West Vancouver | DWV `dwvmaps.westvancouver.ca/server/rest/services/Cadastral/PublishedService_ParcelsExternal/MapServer/0` (PID, ADDRESS, ZONING_DESIGNATION, LAND_USE_DESIGNATION, DATE_BUILT; query endpoint may refuse non-browser clients — falls back to ParcelMap BC `'West Vancouver, The Corporation of the District of'` (19,162) without zoning) | on the parcel | — |
| Langley City | ParcelMap BC `'Langley, City of'` (13,183) | `maps.langleycity.ca/server/rest/services/Maps/Open_Data/MapServer/90` (ZONING; 526; Bylaw 3300 codes) | Address Points `/182` (FULL_ADD) assigned by point-in-parcel |
| Langley Township | GeoSource `mapsvr.tol.ca/arcgisext02/rest/services/GeoSource/DynamicServices/MapServer/3` (57,271; PID, Address, Zoning, LOT_SIZE, StatisticalAreaDescr) + ParcelMap BC `'Langley, The Corporation of the Township of'` (58,625) | on the parcel | — |
| Maple Ridge | ParcelMap BC `'Maple Ridge, City of'` (37,214) | `geoservices.mapleridge.ca/server/rest/services/DataCatalog/PlanningDevelopment/MapServer/6` (ZoningCode; 1,085; R-1…R-4/RT-1 deleted Jul 2026 → RUR) | Parcel `Property/MapServer/3` (Address, StreetName) and Urban Development Area `PlanningDevelopment/MapServer/5` (SSMUH eligibility) by spatial join |

Transit: Surrey–Langley SkyTrain stations (Green Timbers, 152 St, Fleetwood, Bakerview–166 St, Hillcrest–184 St, Clayton, Willowbrook, Langley City Centre; opening 2029) are designated TOAs and are scored as SkyTrain tiers; Scottsdale, Guildford, Newton, Langley Centre, Haney Place exchanges and the Port Haney / Maple Meadows West Coast Express stations use bus-exchange tiers 4–5 (400 m). Delta is only in B.C. Reg. 263/2023's tier 4–5 tables (Scottsdale spill-over); the Scott Road 800 m rings create no obligation in Delta. West Vancouver has no prescribed TOA (Park Royal is a Housing Supply Act directive, not a TOA).

## Zoning rules encoded (grades)

**Surrey — Zoning By-law 12000 consolidated 21 Sep 2026.** R-zones (RA, R1–R7, R2-O, R5-S) SSMUH: <280 m² 3 units, 281–4,050 m² 4, 6 in a Frequent Bus Stop Area (layer 64); houseplex/duplex FAR 1.0 on the first 560 m² + 0.6 (houseplex cap 600 m²), 3 storeys (B; current R3 text only partly read). Inside a TOA SSMUH does not apply (duplex only). MR1 0.7 / MR2 0.9 / MR3 0.8 / MR4 1.0 / MR5 1.5 townhouse; MR6 1.4 (MR6-C 1.6) 4 st; MR7 2.0 (3.0 in TOA), MR7-C 2.2; MR8 4.0 / MR9 5.0 / MR10 5.5 / MR10-CBD 7.5 towers (base; Schedule G bonus not modelled); RM-70 ≈1.3 (E). C-35, CCR, CD not scored. Fees: DCC Bylaw 2026 (SSMUH $51,633/lot + $17.21/sf; TH $27.15/sf; apt $30.72/sf, City Centre $24.31; high-rise $30.30 / $21.88), ACC Jun 2026 (SSMUH ~$11,669/lot + ~$11k per added unit; TH $6.83/sf; apt $10.58/sf), SSAC SD36, Metro Fraser, TransLink. Prices: FVREB HPI Oct 2026 by sub-area; presale condo $650–850/sf, TH $550–700/sf.

**Coquitlam — Zoning Bylaw 3000.** R-1/R-2 small-scale (Bylaw 5449, Jun 2025): 3–4 units, FAR 0.75 (+0.07 parking bonus), 3 st / 11 m, no 6-unit tier (A); R-3 transitional 0.5 (duplex + 2 ADU); R-4 / RT-1 multiplex 0.85 / 0.75; RM-1 0.45 TH; RM-2 1.4; RM-3…RM-6 legacy (D); RA-1 2.04 (strata to 1.85); RA-2 TOA 4.0/12 st or 3.0/8 st, strata to 2.4; RA-3 4.0 base; MU-1 3.0 (strata 2.5), MU-2 4.0, MU-3 5.0, MU-4 5.5 mixed-use (A). RS-* inside TOAs, C-1/C-2/C-5/C-6 and CD not scored. Fees: DCC Bylaw 5411 per unit, ACC Jul 2025 ($21,205/unit low-rise; apartments $21.31/sf ≤12 fl, $38.53/sf above), SSAC SD43, Metro Fraser, TransLink. Prices: GVR HPI Oct 2026 $1,571,400 detached (sub-areas P/E).

**Port Moody — Bylaw 2937; SSMUH Bylaw 3460.** RS*/RT SSMUH 3/4/6 units at FAR 0.70/0.80/1.0, 3 storeys, outside TOAs (B; 6-unit areas from the city's statutes layer). RM1–RM4 townhouse ≈0.7–0.8, RM5 ≈1.5, RM8 ≈2.0, CRM1/CRM2 ≈1.5/2.5 (D — bylaw tables not retrievable). TOAs Moody Centre / Inlet Centre rezoning-based. Fees: DCC Bylaw 3054/3478 (SFD-duplex $34,893; TH $149.98/m²; apt $122.88/m², >6 st $138.10/m²), ACC Bylaw 3551 (Jul 2026), SSAC SD43, Metro Fraser, TransLink; 2022 inclusionary policy 15 % of floor area above 2.0 FAR (rezonings). Prices: GVR HPI Sep 2026 $1,903,500 detached. Staff memo (Mar 2026): no tested scenario reached 15 % margin.

**Delta — Zoning Bylaw 7600; SSMUH in force Jun 2024 with Delta's own standards.** RS1–RS7/RSC/RSF/RD1–RD4: house or duplex + suites + up to two garden suites (3/4/6 units; 6 along the Scott Road R6 corridor, SSMUHUNITAREA), FSR 0.3 × lot + 93 m², 2.5 storeys — suites are not strata-able so it is modelled as a single-lot product (B); Nov 2025 reform package not adopted. RT40/50/62/76 townhouse (FAR derived 0.6–0.9, C); TH2 0.8; RA6 3.0 / 6 st (A); RA20 ≈0.6, RA112/RA120 ≈1.2 (C); RH40 (D); MUL/MULW Ladner rental-only mixed-use (D). ALR parcels excluded. Fees: DCC ≈ $19,845 / $13,524 / $9,923 per unit (2026, +2.6 %), no ACC (PRCAC $1,000/unit on rezonings), no SSAC, Metro Fraser, TransLink. Prices: North Delta (FVREB) $1,159,600; Ladner $1,284,100; Tsawwassen $1,508,500 (Sep 2026).

**West Vancouver — Bylaw 4662.** RD1/RD2 duplex FAR 0.5 (4–6 units allowed since Aug 2024 within that FAR), RD3 0.75 (A); RS zones FAR 0.30 single-family — Amendment Bylaw 5446 (3/4/6 units, FAR 0.65–0.75, new RG-4 zone) read Sept 2026 but adoption unconfirmed → not scored; RM1 2.0 (1.75 west of 23rd), RM2 2.0, RM5 1.0; RG-1A/1B/2 0.6 and RG-3 1.0 with Horseshoe Bay amenity unit; AC1/AC2 Ambleside 1.0 base (1.75 with amenity, rate unpublished); C1–C4 have no FAR → not scored. No TOA. Fees: DCC Bylaw 3801 $9,197/unit ("Other" area), no ACC, no SSAC, Metro North Shore, TransLink. Prices: GVR HPI Sep 2026 detached $2,822,900; new condos $1,300–1,700/sf.

**Langley City — Zoning Bylaw 3300 (adopted 9 Mar 2026).** R1 plex home 4 units (6 within 400 m of a frequent stop), no FAR → derived 0.9 (C); inside TOAs R1 = house + suite (not scored). R2 townhouse 1.2; R3/R3a 2.1 (2.6 with 13 % below-market bonus); R4 2.6 (→3.5); R5 4.5; C1 2.6 (→3.5) (A). TOAs (Willowbrook, Langley City Centre, Langley Centre exchange) rezoning-based with 2.5 % inclusionary. Fees: DCC Bylaw 3256 2026 (SF 45,563; TH 32,683; apt 21,246), Policy CO-80 amenity on rezonings, SSAC SD35, Metro Fraser, TransLink. Prices: FVREB HPI Oct 2026 Langley $1,448,100.

**Langley Township — Bylaw 2500; SSMUH Bylaw 6020 (Nov 2024).** SR-1/SR-3/R-1A–E/R-2/R-CL*: 4 units (3 if ≤280 m²), no FSR — 45 % coverage, 9 m, limited third storey → derived 0.95 (C); not in the Willowbrook TOA; water/sewer connection deferral unresolved. RM-1/RM-2 ≈0.7/0.8, RM-3/RM-4 ≈1.75/2.0 (D — Bylaw 2500 tables not retrievable). RU/SR-2 rural and CD not scored. Fees: DCC Bylaw 5897/6024 (SF 86,787; ground-oriented MF 55,268; apt 38,482; 15–18 % cut proposed), ACC (SF 19,571; GOMF 13,584; apt 8,634; adoption per press), SSAC SD35, Metro Fraser, TransLink.

**Maple Ridge — Bylaw 7600-2019; RUR infill zone (Bylaw 8104-2026).** RS/SRS/RUR lots inside the Urban Development Area: 3/4/6-unit infill, FAR taken as 0.75 (D — s.627 not read); RT-2 0.75; RST ≈0.9; RM-1 0.6, RM-4 0.75, RM-5 0.8, RM-2 1.8 (B); RM-3 1.2 and RM-6 1.6 (D); C-3/CRM residential 1.0 (D). TOAs: Port Haney and Maple Meadows (West Coast Express) and Haney Place exchange at tiers 4/5. Fees: DCC Bylaw 7863-2022 (SFD/duplex $41,011; TH $241.37/m²; apt $235.96/m², ≥6 st $191.81/m²), CAC policy on rezonings (ACC from 2027), SSAC SD42, Metro Fraser, TransLink. Prices: GVR HPI Sep/Oct 2026 by sub-area (West Central $978,000 … Silver Valley $1,360,200); presale median $567/sf.

## Known gaps (batch 2)

* Surrey: MR-zone metric heights; current (non-"proposed") R3 text; C-35 FAR; DCC Bylaw 2026 adoption date.
* Coquitlam: RM-3…RM-6 legacy tables; RT-2; sub-area HPI (only Burke Mountain and Central published).
* Port Moody: every RM / C FAR (PDF truncated); 2026 DCC update unadopted.
* Delta: 2026 DCC schedule (civicweb blocked); RA/RT zones beyond those read; strata status of SSMUH units.
* West Vancouver: Bylaw 5446 adoption; Ambleside amenity-unit rate; DWV query endpoint access from non-browser clients.
* Langley Township: Bylaw 2500 RM tables; DCC reduction and ACC adoption status; servicing deferral.
* Maple Ridge: RUR (s.627) FSR / coverage; RM-3 / RM-6 / C-7 standards; ACC rate schedule.
* All batch-2 cities: no open assessed values or year built (except West Vancouver's DATE_BUILT when its layer responds), so recently rebuilt houses are not screened out.

---

# Batch 3 (research 4 Nov 2026): Abbotsford, Whistler, Greater Victoria core (Victoria, Saanich, Oak Bay, Esquimalt, Langford, Colwood, View Royal)

## Parcel and zoning endpoints

| City | Parcels | Zoning | Enrichment / land values |
|---|---|---|---|
| Abbotsford | AGOL `services8.arcgis.com/ZYlQy38aWlfDG1Qh/.../Parcel_Layers_External_Feature/FeatureServer/0` (30,825; PID, PROP_ADDRESS, ZONING, OCP_LandUse, UDA, ALR, FLOODPLN, HAP, LUC) | on the parcel (also `Development_Layers_External_Feature/45`) | **BC Assessment LAND_VALUE / IMP_VALUE on the parcel (29,484 rows) — grade A** |
| Whistler | `webmap.whistler.ca/server/rest/services/ExternalVS/Parcels/MapServer/0` (15,442 incl. strata lots; non-strata 2,544; PID, FOLIOADRSS, ZONING1) | on the parcel | SSMUH dwelling-count polygons `ExternalVS/Land_Use/MapServer/4` (3 / 4 units); TOA buffers `/3` |
| Victoria | CRD lot fabric `mapservices.crd.bc.ca/arcgis/rest/services/Properties/MapServer/2` (BCAJurisdiction 234; 13,472 subdivision lots; PID, FullAddress, OwnerType) | `maps.victoria.ca/server/rest/services/OpenData/OpenData_PlanningAndDevelopment/MapServer/12` (Zoning; 705 district polygons, ZB1980 / ZB2018) | **Property Assessment Report 2026 `services.arcgis.com/EHSKalEvBxdO9ljW/.../Property_Assessment_Report_2026/FeatureServer/0` (land_gross / impr_gross by PID) — grade A**; Heritage Properties `/10` |
| Saanich | CRD lot fabric (308 / 309 / 389; 30,754) | `map.saanich.ca/server/rest/services/MAPS/SaanichMapService_External/MapServer/28` (ZONINGTYPE) | SSMUH Transit Proximity Area `/128` (6 units), Urban Containment Boundary `/11`, ALR `/10`, OCP `/134` |
| Oak Bay | CRD lot fabric (317; 5,972) | **none published** — private lots 200–4,050 m² assumed RS (zoning grade D) | — |
| Esquimalt | CRD lot fabric (307; 2,791) | `gis.esquimalt.ca/arcgis/rest/services/Services/Zoning/MapServer/0` (Zone) | RSM-1 small-scale multi-unit parcels `Services/RSM/MapServer/0` (PID) |
| Langford | `arcex.langford.ca/server/rest/services/Parcel_Info_Map/Parcel_Info_Webmap_EB/MapServer/10` (Parcels_For_CV; PID, Full_Address, ZONE_ABR) | on the parcel (`/12` Zoning) | **LandValue / ImprovementsValue on the parcel — grade A**; OCP `/30` |
| Colwood | AGOL `services3.arcgis.com/MLf7r3NQY1Pb8feC/.../mapParcel/FeatureServer/0` (PID, Address, OwnerType, SubCategory) | `mapZoning/FeatureServer/1` (ZoneCode) | — |
| View Royal | CRD lot fabric (401 / 402; 2,097) | **PDF only** — private lots assumed R1 (zoning grade D) | — |

Transit (B.C. Reg. 263/2023 Schedule; Tables 4–5 item 2 = FAR 3.5 / 10 st within 200 m, 2.5 / 6 st to 400 m; item 3 for Whistler = 2.5 / 6 and 1.5 / 4): Bourquin Exchange (Abbotsford), Gondola Exchange (Whistler), Legislature (Victoria), Uptown, Royal Oak, UVic (Saanich), Colwood, Langford and VGH (View Royal) exchanges. Esquimalt and Oak Bay have no prescribed TOA. Outside Metro Vancouver there is no regional or TransLink DCC.

## Zoning rules encoded (grades)

**Abbotsford — Zoning Bylaw 2400-2014; SSMUH zones (Bylaws 3690/3691/3692-2025) adopted 16 Dec 2025, Application Guide Jan 2026.** SSMUH 1: townhouse form up to 4 principal units, FSR 0.9 (3 units) / 1.2 (4), 11 m, coverage 50/75 %, min 495 m² / 16.5 m; principal units may be owned (B). SSMUH 2 / 2g / 3 / 4: house or duplex + suites / garden suite / coach house, FSR 0.65, 9.5 m — accessory units cannot be sold separately, modelled as a single-lot duplex product (B). Lots inside the Urban Development Boundary only (UDA flag); no 6-unit tier (no frequent bus service); ALR and land-use-contract lots excluded. TH1 FSR 1.5 (B), TH2 1.5 (C); RMG / RMR 0.5–1.5 (A); RMF 60 u/ha and RM16/30/45/60 u/ha townhouse → derived FAR 0.21–0.8 (C); RML 1.4 (1.7 bonus) 6 st and RMM 1.0–2.5 6 st (A); C7 3.0 Historic Centre (3 st) / 2.5 Urban Centre (A). Fees: DCC Bylaw 3633-2025 + ACC Bylaw 3637-2025 (1 Feb 2026) per unit incl. ACC and SSAC — duplex $40,497; townhouse/SSMUH $31,743; apartment $20,423 (A). Prices: presale condo $550–650/sf, townhouse ~$500/sf (E).

**Whistler — Zoning and Parking Bylaw 303 s.35; SSMUH Bylaws 2440 (Jun 2024) and 2461 (Mar 2025).** RS1 / RI1 / RS2 / RS4 / RT1 / RT2 / RT6 lots ≤ 4,050 m² inside the Urban Development Containment Area with water and sewer, outside the Gondola Exchange TOA: 3 units (≤ 280 m²) or 4; GFA the lower of FSR 0.40 (0.45 in RT1/RT6) or 511 m²; 4 units → 2 employee-restricted rental units (housing agreement; strata permitted with it) (A). Employee units valued at 65 % of market (E). RM1–RM74 / RTA / CC site-specific zones are built out and not scored. Fees: no RMOW DCC bylaw found — $8,000/unit works-and-services placeholder (E). Prices: new product $1,500–2,000/sf (E); HPI detached ~$3.0M (E).

**Victoria — Zoning Regulation Bylaw 80-159 Schedule P (Missing Middle Bylaw 22-045, Jan 2023; SSMUH Jun 2024).** Traditional Residential lots (R1-B, R1-G, R1-A, R-2 …): houseplex 3–6 units, FSR 1.0, 11 m, coverage 40 %, max 1,410 m² floor area, no transit test; corner townhouse FSR 1.1 (corner lots not identifiable → not modelled) (A). R3-*, R-48/59/68, GRD-1, LVD-1, CVD-1 legacy / 2018 districts: FSR placeholders (D). C-1 / CA-* central area FSR 3.0 (C). Fees: City DCC ~$12,000/unit + CRD sewer ~$2,500 + SSAC (E). Land values: BC Assessment 2026 by PID (A).

**Saanich — Zoning Bylaw 8200 Schedule G (SSMUH in force 30 Jun 2024).** RS-* / RD-* / A-1/A-2 lots inside the Urban Containment Boundary, ≤ 4,050 m², outside TOAs: 3 / 4 units, 6 within the SSMUH Transit Proximity Area (400 m of an SSMUH bus stop); FSR 1.0 (1.1 for 6 units), 11 m; strata permitted (B — the guide lists FSR 0.6 / 1.0 / 1.1 without mapping to unit counts). RT / RA / RM / C: placeholders (D). Fees: DCC ~$15,000/unit + CRD + SSAC (E).

**Oak Bay — Zoning Bylaw 3531 Schedule G (adopted 10 Jun 2024).** Houseplex 3–4 units (6 near a frequent stop), FSR 1.0, coverage 50 % (B via architect summary). No zoning layer: every private lot 200–4,050 m² is treated as RS (D). Fees ~$17,000/unit (E).

**Esquimalt — Zoning Bylaw 2050; RSM-1 small-scale multi-unit zone (Jun 2024).** RSM-1 parcels (city layer) and RS-* / RD-*: 3–4 units; FSR not retrieved → 0.8 placeholder (D). No TOA, no 6-unit tier.

**Langford — Zoning Bylaw 300; SSMUH Amendment Bylaw 2183 with Schedule AA stops (May 2024).** R2 / RS1 / R1 lots 281–4,047 m² outside the Langford Exchange TOA: 4 units, 6 within 400 m of a Schedule AA stop (stops not retrieved → ftn unknown); FSR placeholder 0.9 (D). RT / RM / RH / MU / CC: placeholders (D). Land values: BC Assessment on the parcel layer (A).

**Colwood — Land Use Bylaw 151 (SSMUH Jun 2024).** R1–R6 lots outside the Colwood Exchange TOA: 3–4 units; FSR placeholder 0.8 (D).

**View Royal — Zoning Bylaw 900 (SSMUH map Aug 2024).** R1 lots: 3–4 units, 6 within 400 m of six prescribed stops (not retrieved); FSR placeholder 0.8; zoning assumed R1 (D).

## Known gaps (batch 3)

* Abbotsford: SSMUH 3 / 4 standards; TH2, RMU/RMX/RMC/RH1 FSR; C7 Urban Centre height; sub-area HPI (assessed values make this secondary).
* Whistler: RMOW DCC / works-and-services charges; employee-unit value discount; RS1 height increase (2025 proposal).
* Victoria: FSR for R3-*, R-48/59/68, GRD-1, LVD-1, CVD-1 and the 2025 OCP pre-zoning; corner-lot detection; 2026 DCC schedule.
* Saanich: which FSR (0.6 / 1.0 / 1.1) applies to which unit count; Schedule G coverage by lot type; DCC schedule; apartment / commercial FSRs.
* Oak Bay and View Royal: no open zoning layer — zones assumed; View Royal prescribed stops.
* Esquimalt, Langford, Colwood: SSMUH FSR / height from the bylaw text; multi-family and mixed-use FSRs; DCC schedules; Langford Schedule AA stops.
* All Capital Region cities: prices and HPI are estimates (VREB benchmark not fetched); no year-built data except through assessed improvement ratios (Victoria, Langford).
