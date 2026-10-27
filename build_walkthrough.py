"""Builds output/margin_walkthrough.html: one SVG that walks the pro forma step by step on 4777 W 2nd Ave."""
import html, os

W = 1400
LEFT_X, LEFT_W = 40, 250        # step column
EQ_X, EQ_W = 320, 600           # equation column
SRC_X, SRC_W = 1010, 370         # source column
ROW_H, ROW_GAP = 150, 28
TOP = 250                       # below the method band

GRADE = {
    "A": ("#1f7a4d", "A · official record, measured"),
    "B": ("#2f6fb5", "B · published figure, interpreted"),
    "C": ("#c8742a", "C · survey or asking price"),
    "D": ("#b3261e", "D · inferred, thin evidence"),
    "V": ("#5c655f", "✓ · arithmetic checked by hand"),
}

steps = [
    dict(n=1, name="Lot", who="City of Vancouver open data · BC Assessment",
         eq=["area = shoelace(parcel polygon) · zone, values from 2026 tax roll"],
         out=["3,581 m² = 38,548 sf · R1-1 · West Point Grey", "assessed $9.97M land + $0.65M bldg = $10.62M · built 1930"],
         src=["Parcel polygons + property-tax report, CoV open data.", "Values are BC Assessment's as of 1 Jul 2025.", "Polygon area vs REW lot size: 0.4% apart."], g="A",
         flow="site 38,548 sf · zone R1-1"),
    dict(n=2, name="Entitlement", who="District schedule, encoded as rules",
         eq=["GFA = site area × FSR(zone, site size)"],
         out=["R1-1 ≥ 557 m² → multiplex, 1.00 FSR, 3 st", "38,548 × 1.00 = 38,548 sf buildable"],
         src=["Zoning by-law district schedules to Jul 2026,", "read into zoning_rules.py (R1-1, R3, R4, R5, RM,", "C-2, TOA tiers). Ignores view cones, heritage, slope."], g="B",
         flow="GFA 38,548 sf"),
    dict(n=3, name="Revenue", who="Price table by local area (my survey)",
         eq=["saleable = GFA × efficiency · revenue = saleable × $/sf"],
         out=["38,548 × 0.90 = 34,693 sf saleable (~35 units)", "34,693 × $1,350 = $46.84M"],
         src=["Efficiency: industry rule of thumb (0.90 multiplex,", "0.85 wood-frame, 0.80 tower). $/sf: 2026 brokerage and", "presale surveys, trimmed to asking × 0.92–0.93."], g="C",
         flow="revenue $46.84M"),
    dict(n=4, name="Land", who="REW asking price, else BC Assessment × 1.10",
         eq=["land = price + PTT + 1% closing + $60k demo + 6.5% × 18 mo carry"],
         out=["$10.998M + $0.468M + $0.110M + $0.060M + $1.072M", "= $12.71M (unlisted sites: assessed × 1.10 instead)"],
         src=["Asking: REW listing, 15 Sep 2026 (moved $110k by Oct 9).", "PTT: provincial formula. 1.10, carry and demo:", "assumptions.json. Grade A if listed, D if not."], g="D",
         flow="land $12.71M"),
    dict(n=5, name="Build", who="Contractor bids, as published in cost guides",
         eq=["hard = GFA × $/sf(type) · soft = hard × 22%"],
         out=["38,548 × $420 = $16.19M hard", "$16.19M × 0.22 = $3.56M soft"],
         src=["Altus 2026 Canadian Cost Guide (6,500+ projects) and", "BTY guide, top of range to cover parking and site work.", "A builder's quote for this lot could sit ±15% outside."], g="B",
         flow="build $19.75M"),
    dict(n=6, name="Fees", who="City, Metro Vancouver, TransLink schedules",
         eq=["DCL + ACC per sf (by FSR tier) + DCCs per unit + inclusionary"],
         out=["$7.53 + $2.32 /sf → $0.38M · 35 units × $27,674 → $0.97M", "west-side R1-1 cash-in-lieu $27.50/sf → $1.06M · total $2.41M"],
         src=["CoV DCL bulletin Dec 2025, ACC Sep 2026, Metro DCC 2026,", "TransLink DCC, R1-1 large-lot cash-in-lieu policy.", "Applied mechanically; only the unit count is estimated."], g="A",
         flow="fees $2.41M"),
    dict(n=7, name="Result", who="Residual land value appraisal (RICS, Altus, Coriolis)",
         eq=["profit = revenue − (land + hard + soft + fees) · margin = profit ÷ cost", "max land price = (revenue ÷ 1.15 − non-land cost) ÷ 1.135"],
         out=["$46.84M − $34.87M = $11.97M · 34.3% on cost", "max land price $16.27M (1.5× asking) · equity = land + 25% build"],
         src=["Same formula developers, valuers and the City's fee", "consultants use; 15% target is the low end of the 15–25%", "range developers quote. Recomputed by hand: matches."], g="V",
         flow="profit, margin, max land price"),
    dict(n=8, name="Filter & rank", who="Checks added after bad rows surfaced",
         eq=["drop tax-exempt, implausible land value, <250 / >6,000 m², existing apts"],
         out=["88,971 parcels → 74,580 scored → 3,750 clear 15% at assessed", "1,151 listed → 65 clear 15% at asking · 4777 W 2nd ranks #1 by profit"],
         src=["Tax levy = 0 marks exempt (3,986). Land value < 40% of", "area median marks leaseholds and errors. Filters were", "added after each early top-100 showed an outlier."], g="V",
         flow=None),
]

def esc(s): return html.escape(s, quote=True)

svg = []
H = TOP + len(steps) * (ROW_H + ROW_GAP) + 120
svg.append(f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="How one parcel becomes a margin: eight steps from lot to ranking, each with its equation, the worked numbers for 4777 West 2nd Avenue, its data source and a reliability grade" xmlns="http://www.w3.org/2000/svg">')
svg.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>')

# ---- method band
by = 30
svg.append(f'<text x="{LEFT_X}" y="{by}" class="eyebrow">WHERE THE METHOD COMES FROM</text>')
boxes = [
    ("Residual land value appraisal", ["Revenue − all costs except land − required", "profit = what the land is worth. Standard", "development appraisal; ~2/3 of small and", "mid-sized developers use it with a cash margin", "of 15–25% on cost (RICS survey)."]),
    ("Who runs it today", ["Developers: Excel pro forma, one site at a time.", "Argus Developer (Altus): the commercial standard.", "Vanplex: free, R1-1 multiplex lots only.", "Coriolis for the City: feasibility testing", "before DCL / ACC / CAC rates are set."]),
    ("What this tool changes", ["Same appraisal, written as a script and run on", "every parcel at once, with the inputs taken from", "public documents instead of typed in per site.", "Nothing in the formula is new; the labour and", "the coverage are."]),
]
bw, bh, bg = 420, 150, 30
for i, (t, lines) in enumerate(boxes):
    x = LEFT_X + i * (bw + bg)
    cls = "band-accent" if i == 2 else "band"
    svg.append(f'<rect x="{x}" y="{by+16}" width="{bw}" height="{bh}" rx="10" class="{cls}"/>')
    hc, sc = ("h-acc", "s-acc") if i == 2 else ("h", "s")
    svg.append(f'<text x="{x+18}" y="{by+44}" class="{hc}">{esc(t)}</text>')
    for j, ln in enumerate(lines):
        svg.append(f'<text x="{x+18}" y="{by+70+j*20}" class="{sc}">{esc(ln)}</text>')
    if i < 2:
        svg.append(f'<line x1="{x+bw+2}" y1="{by+16+bh/2}" x2="{x+bw+bg-4}" y2="{by+16+bh/2}" stroke="currentColor" stroke-width="1.6" marker-end="url(#arr)"/>')

# ---- column headers
hy = TOP - 22
svg.append(f'<text x="{LEFT_X}" y="{hy}" class="eyebrow">STEP · WHO SETS THE INPUT</text>')
svg.append(f'<text x="{EQ_X}" y="{hy}" class="eyebrow">EQUATION · WORKED ON 4777 W 2ND AVE (R1-1, LISTED)</text>')
svg.append(f'<text x="{SRC_X}" y="{hy}" class="eyebrow">SOURCE · HOW FAR TO TRUST IT</text>')

# ---- rows
for i, st in enumerate(steps):
    y = TOP + i * (ROW_H + ROW_GAP)
    col, glabel = GRADE[st["g"]]
    # step label
    svg.append(f'<circle cx="{LEFT_X+22}" cy="{y+28}" r="20" class="stepnum-bg"/>')
    svg.append(f'<text x="{LEFT_X+22}" y="{y+34}" text-anchor="middle" class="stepnum">{st["n"]}</text>')
    svg.append(f'<text x="{LEFT_X+56}" y="{y+34}" class="h">{esc(st["name"])}</text>')
    # who, wrapped at ~34 chars
    who = st["who"]; words = who.split(); lines=[]; cur=""
    for w in words:
        if len(cur)+len(w)+1 > 34: lines.append(cur); cur=w
        else: cur = (cur+" "+w).strip()
    lines.append(cur)
    for j, ln in enumerate(lines):
        svg.append(f'<text x="{LEFT_X}" y="{y+66+j*18}" class="s">{esc(ln)}</text>')
    # equation box
    svg.append(f'<rect x="{EQ_X}" y="{y}" width="{EQ_W}" height="{ROW_H}" rx="10" class="eqbox"/>')
    yy = y + 30
    for ln in st["eq"]:
        svg.append(f'<text x="{EQ_X+18}" y="{yy}" class="eq">{esc(ln)}</text>'); yy += 24
    yy += 10
    for ln in st["out"]:
        svg.append(f'<text x="{EQ_X+18}" y="{yy}" class="num">{esc(ln)}</text>'); yy += 24
    # source box
    svg.append(f'<rect x="{SRC_X}" y="{y}" width="{SRC_W}" height="{ROW_H}" rx="10" class="srcbox" stroke="{col}"/>')
    svg.append(f'<rect x="{SRC_X}" y="{y}" width="6" height="{ROW_H}" rx="3" fill="{col}"/>')
    svg.append(f'<text x="{SRC_X+20}" y="{y+28}" class="grade" fill="{col}">{esc(glabel)}</text>')
    import textwrap
    for j, ln in enumerate(textwrap.wrap(" ".join(st["src"]), 46)[:5]):
        svg.append(f'<text x="{SRC_X+20}" y="{y+52+j*20}" class="s2">{esc(ln)}</text>')
    # flow arrow to next row
    if st["flow"]:
        x = EQ_X + 40
        svg.append(f'<line x1="{x}" y1="{y+ROW_H}" x2="{x}" y2="{y+ROW_H+ROW_GAP-2}" stroke="currentColor" stroke-width="1.6" marker-end="url(#arr)"/>')
        svg.append(f'<text x="{x+14}" y="{y+ROW_H+ROW_GAP/2+5}" class="flow">{esc(st["flow"])}</text>')

# ---- bracket: step 3 revenue minus steps 4-6 costs feed step 7
y3 = TOP + 2 * (ROW_H + ROW_GAP)
y6e = TOP + 5 * (ROW_H + ROW_GAP) + ROW_H
y7 = TOP + 6 * (ROW_H + ROW_GAP)
bx = EQ_X + EQ_W + 16
svg.append(f'<path d="M{bx} {y3+8} h10 v{y6e-y3-16} h-10" fill="none" stroke="currentColor" stroke-width="1.6"/>')
svg.append(f'<path d="M{bx+10} {(y3+y6e)/2} h14 V{y7+ROW_H/2} h-14" fill="none" stroke="currentColor" stroke-width="1.6" marker-end="url(#arr)"/>')
mid=(y3+y6e)/2
svg.append(f'<text x="{bx+42}" y="{mid}" class="flow" transform="rotate(90 {bx+42} {mid})" text-anchor="middle">revenue (3) − costs (4–6) → step 7</text>')

# ---- footer legend
ly = H - 60
svg.append(f'<text x="{LEFT_X}" y="{ly}" class="eyebrow">RELIABILITY GRADES</text>')
lx = LEFT_X
for k in ["A", "B", "C", "D", "V"]:
    col, lab = GRADE[k]
    svg.append(f'<rect x="{lx}" y="{ly+14}" width="14" height="14" rx="3" fill="{col}"/>')
    svg.append(f'<text x="{lx+20}" y="{ly+26}" class="s">{esc(lab)}</text>')
    lx += 60 + len(lab) * 7
svg.append('</svg>')
SVG = "\n".join(svg)

page = f"""<title>Margin Walkthrough</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
/* layout: one wide figure, title above, caption below; the figure scrolls sideways on phones */
:root{{--bg:#f2f4f1;--panel:#fbfbf8;--panel-2:#e7ebe6;--fg:#16211d;--muted:#5c655f;--line:#cfd6d1;--accent:#1f5c4a;--accent-ink:#f2f4f1;
--sans:'IBM Plex Sans',system-ui,sans-serif;--mono:'IBM Plex Mono',ui-monospace,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#141a17;--panel:#1c2420;--panel-2:#26302b;--fg:#e8ece9;--muted:#a3ada7;--line:#36413b;--accent:#5fae8e;--accent-ink:#0f1512;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#141a17;--panel:#1c2420;--panel-2:#26302b;--fg:#e8ece9;--muted:#a3ada7;--line:#36413b;--accent:#5fae8e;--accent-ink:#0f1512;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font-family:var(--sans);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:32px 48px}}
main{{max-width:1400px;margin:0 auto}}
h1{{font-size:28px;font-weight:600;margin:0 0 6px;text-wrap:balance}}
.lede{{color:var(--muted);max-width:70ch;margin:0 0 24px;line-height:1.5}}
figure{{margin:0;overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}}
svg{{display:block;width:1400px;max-width:none;height:auto;color:var(--fg);padding:24px}}
@media (min-width:1460px){{svg{{width:100%;max-width:100%}}}}
figcaption{{padding:14px 18px;border-top:1px solid var(--line);color:var(--muted);font-size:14px;line-height:1.5;max-width:none}}
.eyebrow{{font:500 12px var(--sans);letter-spacing:.08em;fill:var(--muted)}}
.h{{font:600 17px var(--sans);fill:var(--fg)}}
.s{{font:400 13.5px var(--sans);fill:var(--muted)}}
.s2{{font:400 12.5px var(--sans);fill:var(--muted)}}
.eq{{font:500 13.5px var(--mono);fill:var(--fg)}}
.num{{font:600 14px var(--mono);fill:var(--accent)}}
.flow{{font:500 12.5px var(--mono);fill:var(--muted)}}
.grade{{font:600 13px var(--sans)}}
.band{{fill:var(--panel-2);stroke:var(--line)}}
.band-accent{{fill:var(--accent)}}
.h-acc{{font:600 17px var(--sans);fill:var(--accent-ink)}}
.s-acc{{font:400 13.5px var(--sans);fill:var(--accent-ink);opacity:.9}}
.eqbox{{fill:var(--panel-2);stroke:var(--line)}}
.srcbox{{fill:var(--panel);stroke-width:1.5}}
.stepnum-bg{{fill:var(--accent)}}
.stepnum{{font:600 17px var(--mono);fill:var(--accent-ink)}}
.foot{{color:var(--muted);font-size:13px;margin-top:16px;line-height:1.5;max-width:90ch}}
</style>
<main>
<h1>How one parcel becomes a margin</h1>
<p class="lede">The eight steps the screener runs on every lot, with the equation, the worked numbers for 4777 West 2nd Avenue, where each input comes from and how far to trust it. Read down the middle column for the arithmetic; the right column is the evidence.</p>
<figure>
{SVG}
<figcaption>Revenue (step 3) minus the costs in steps 4–6 gives the profit in step 7; the margin divides that by total cost. Every green number can be recomputed by hand from the inputs shown. Grades: the two inputs with the most leverage on the answer, sale price (C) and unlisted land price (D), are the two least reliable, so the ranking is more trustworthy than any single margin.</figcaption>
</figure>
<p class="foot">Inputs in assumptions.json, equations in score.py, rules in zoning_rules.py. Method references: RICS Land Journal on developer returns; Altus Group development-feasibility guide; City of Vancouver DCL/ACC rate reports citing Coriolis feasibility testing. Figures as of the 15 Sep 2026 REW crawl and the 2026 assessment roll.</p>
</main>
"""
# the third band box has dark-green fill; its text needs the light ink
page = page.replace('class="band-accent"/>', 'class="band-accent"/>', 1)
out = os.path.join(os.path.dirname(__file__), "output", "margin_walkthrough.html")
open(out, "w").write(page)
print("wrote", out, len(page))
