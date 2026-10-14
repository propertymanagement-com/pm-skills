#!/usr/bin/env python3
"""Build the monthly Property Owner Update package from the loader's outputs.

Inputs : <out>/company.json + owners.json (from `appfolio_loader.py features`), the client config, the templates in ../assets/
Outputs, all under <out>/newsletter/:
  merge.csv / merge.json          one row per eligible owner with every merge field (numbers, paragraphs, report link)
  previews/*.html                 a handful of rendered emails for review (largest owner, one with a [CONFIRM], a promoter, a quiet single-home owner ...)
  reports/<token>.html            one portfolio report page per owner; host this folder at report_base_url so the email button works
  newsletter-studio.html          owner picker + faithful preview + editable fields + export (comms lead review surface)
  email-template.html / .txt      the merge templates to paste into the mail-merge tool
Usage  : python3 build_newsletter.py --out out --config assets/client-config.json --month 2026-10 [--previews 6] [--render-all] [--report-base-url URL]
"""
import argparse, collections, csv, datetime as dt, hashlib, html, json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__)); ASSETS = os.path.join(os.path.dirname(HERE), "assets")
sys.path.insert(0, HERE)
from pm_benchmarks import available, load as load_benchmarks

BENCH = {}
BENCH_OK = False
LEASE_HORIZON_DAYS = 90; VACANT_FLAG_DAYS = 30; MARKET_BAND_PCT = 5; MARKET_ARTIFACT_PCT = 35
e = html.escape

def money(v): return "n/a" if v is None else f"${max(v, 0):,.0f}"
def pct(v): return "n/a" if v is None else f"{v:.0f}%"
def fill(t, row): return re.sub(r"\{\{(\w+)\}\}", lambda m: str(row.get(m.group(1), "")), t)
def month_label(m): y, mo = m.split("-"); return dt.date(int(y), int(mo), 1).strftime("%B %Y")
def nice_date(s): return dt.date.fromisoformat(s).strftime("%b %d").replace(" 0", " ")
def since(s): return dt.date.fromisoformat(s).strftime("%b %Y")

# ---- describing a property the way its owner would recognise it -------------------------------------------------
def base_kind(p):
    t = (p.get("type") or "").lower(); u = p["units"]
    if u > 1: return f"{u}-unit building"
    if t.startswith("single"): return "single-family home"
    if t.startswith("condo"): return "condo"
    if t.startswith("town"): return "townhome"
    if t.startswith("mixed"): return "mixed-use building"
    return "home"

def where(p):
    """'single-family home at 100 Example St' when the directory carried an address, else '... in Testville'."""
    k = base_kind(p); a = re.sub(r"\s+", " ", (p.get("address") or "").strip()); c = (p.get("city") or "").strip()
    if a: return f"{k} at {a}" + (f" in {c}" if c and c.lower() not in a.lower() else "")
    return f"{k} in {c}" if c else k

MARKET_OK = True   # set from the config's newsletter.show_rent_vs_market; False hides every market comparison (use when the team does not trust AppFolio's Computed Market Rent)
ENTITY_RE = re.compile(r"\b(LLC|L\.L\.C\.?|Inc\.?|Corp\.?|Co\.|Company|Trust|Properties|Property|Holdings|Investments?|Ventures|Capital|Partners|Group|Fund|Estates?|Realty|Management|Development|Enterprises|Rentals|Homes)\b", re.I)
TIER_RANK = {"Call this week": 0, "Watch": 1, "Healthy": 2, "No signal": 3, "Departed": 4}

def market_phrase(rvm, plural=False, with_pct=True):
    """None when market comparisons are off, there is no market rent, or the gap is so large it is almost certainly a stale AppFolio market-rent field.
    The homes paragraph uses the qualitative form (an owner reads a percentage as a fact to argue with); the renewal stance keeps the number because it justifies the action."""
    if not MARKET_OK or rvm is None or abs(rvm) > MARKET_ARTIFACT_PCT: return None
    lead = "rents " if plural else ""
    if abs(rvm) < MARKET_BAND_PCT: return lead + "in line with market"
    return lead + (f"{abs(rvm):.0f}% " if with_pct else "") + f"{'above' if rvm > 0 else 'below'} market"

def merge_owners(group):
    """One email per inbox. AppFolio often holds one person as several owner records (a person plus their LLCs, or two records on one property);
    sending each record its own copy means one inbox gets two to four near-identical emails. Merge them: every property once, the person's first name if any record is a person."""
    if len(group) == 1: return group[0]
    P, seen = [], set()
    for o in group:
        for pr in o["properties_detail"]:
            if pr["property_id"] not in seen: seen.add(pr["property_id"]); P.append(pr)
    persons = [o for o in group if o["first_name"] and not ENTITY_RE.search(o["name"])]
    first = (persons or [o for o in group if o["first_name"]] or [group[0]])[0]["first_name"]
    m = dict(group[0])
    m.update({"owner_id": "+".join(o["owner_id"] for o in group), "name": " / ".join(dict.fromkeys(o["name"] for o in group)), "first_name": first,
              "properties_detail": P, "properties": len(P), "units": sum(pr["units"] for pr in P), "occupied": sum(pr["occupied"] for pr in P),
              "rent_month": sum(pr.get("rent_month") or 0 for pr in P), "past_due": sum(pr.get("past_due") or 0 for pr in P),
              "managers": list(dict.fromkeys(mm for o in group for mm in o["managers"])), "regions": sorted({r for o in group for r in o.get("regions", [])}),
              "signals": [sg for o in group for sg in o["signals"]], "score": max(o["score"] for o in group),
              "tier": min((o["tier"] for o in group), key=lambda t: TIER_RANK.get(t, 9)),
              "survey": min((o["survey"] for o in group if o.get("survey")), key=lambda sv: sv.get("nps", 10), default=None),
              "_merged_from": [o["name"] for o in group]})
    return m

def home_line(p):
    w = where(p); bits = []
    if p["units"] > 1:
        bits.append("leasing up for the first time, " + f"{p['occupied']} of {p['units']} units leased" if p.get("lease_up") else f"{p['occupied']} of {p['units']} units leased")
        if p.get("rent_month"): bits.append(f"{money(p['rent_month'])}/mo total")
        mp = market_phrase(p.get("rent_vs_market_pct"), plural=True, with_pct=False)
        if mp: bits.append(mp)
    else:
        if p["occupied"]:
            bits.append(f"leased at {money(p['rent_month'])}/mo" if p.get("rent_month") else "leased")
            mp = market_phrase(p.get("rent_vs_market_pct"), with_pct=False)
            if mp: bits.append(mp)
        else:
            d = p.get("max_days_vacant") or 0; u0 = (p.get("units_detail") or [{}])[0]
            bits.append("listed for its first lease with us" if u0.get("never_leased") else (f"vacant {d:.0f} days" if d else "between tenants"))
    if p.get("managed_since"): bits.append(f"with us since {since(p['managed_since'])}")
    return w, ", ".join(bits)

def homes_paragraph(P):
    if len(P) == 1:
        w, b = home_line(P[0]); return f"Your {w}: {b}."
    parts = [f"{w} ({b})" for w, b in (home_line(p) for p in P[:6])]
    tail = f"; and {len(P) - 6} more" if len(P) > 6 else ""
    return "Your properties: " + "; ".join(parts) + tail + "."

# ---- the "coming up" recommendations: rule table from the config, sentences from here -----------------------------
def recommendations(P, cfg, month_start, mgr):
    """One or two sentences an owner can act on. Rule table lives in the config; the horizon starts at the send month so a lease that ended before the email goes out is not 'coming up'."""
    cap = cfg.get("newsletter", {}).get("max_increase_pct", 5); items = []; single = len(P) == 1
    horizon = month_start + dt.timedelta(days=LEASE_HORIZON_DAYS)
    def ref(p, capital=False):   # a single-property owner already saw the address in the homes paragraph; repeating it reads like a form letter
        r = f"your {base_kind(p)}" if single else f"your {where(p)}"
        return (r[0].upper() + r[1:]) if capital else r
    for p in P:
        rvm = p.get("rent_vs_market_pct"); d = p.get("max_days_vacant") or 0; vac = p.get("vacant_units") or 0; u = p["units"]
        if vac and d > VACANT_FLAG_DAYS:
            lead = f"{ref(p, True)} has been vacant {d:.0f} days." if u == 1 else ((("Both units" if u == 2 else f"All {u} units") + f" at {ref(p)} have been vacant up to {d:.0f} days.") if vac == u else f"{vac} of {u} units at {ref(p)} {'has' if vac == 1 else 'have'} been vacant up to {d:.0f} days.")
            items.append((1, -d, lead + f" [CONFIRM: the pricing or condition change being made to lease {'it' if vac <= 1 else 'them'}.]"))
        if (p.get("past_due") or 0) > (p.get("rent_month") or 0) > 0:
            items.append((2, -p["past_due"], f"A tenant balance of {money(p['past_due'])} is outstanding at {ref(p)}. [CONFIRM: the collection step under way and the next date.]"))
        ends = p.get("lease_ends_120d") or ([p["next_lease_end"]] if p.get("next_lease_end") else [])
        nl = next((d for d in sorted(ends) if month_start <= dt.date.fromisoformat(d) <= horizon), None)   # first lease end inside the send-month horizon, not the property's earliest
        if nl:
            when = nice_date(nl); plural = u > 1
            lead = f"The lease at {ref(p)} ends {when}." if not plural else f"The next lease at {ref(p)} ends {when}."
            mp = market_phrase(rvm, plural)
            if mp is None: stance = "We will send renewal terms with a current market comparison before then."
            elif abs(rvm) < MARKET_BAND_PCT: stance = f"{'Rents are' if plural else 'Rent is'} in line with market, so we recommend renewing at the current rent and keeping a paying tenant in place."
            elif rvm < 0: stance = f"{'Rents sit' if plural else 'Rent sits'} {abs(rvm):.0f}% below market, so we will propose an increase toward market, capped at {cap}%, with the comparison attached."
            else: stance = f"{'Rents are' if plural else 'Rent is'} {rvm:.0f}% above market; we recommend renewing flat, since a turn would likely reprice the unit down."
            items.append((3, nl, lead + " " + stance))
        if vac and d <= VACANT_FLAG_DAYS:
            never = p.get("lease_up") or (u == 1 and (p.get("units_detail") or [{}])[0].get("never_leased"))
            if never: items.append((4, -d, f"{ref(p, True)} is being leased for the first time with us; {mgr} will send the leasing update."))
            elif u == 1: items.append((4, -d, f"{ref(p, True)} is between tenants" + (f" ({d:.0f} days so far)" if d else "") + f"; {mgr} will send the leasing update."))
            else: items.append((4, -d, (("Both units" if u == 2 else f"All {u} units") + f" at {ref(p)} are vacant" if vac == u else f"{vac} of {u} units at {ref(p)} {'is' if vac == 1 else 'are'} vacant") + (f" ({d:.0f} days so far)" if d else "") + f"; {mgr} will send the leasing update."))
    items.sort(key=lambda x: (x[0], str(x[1]))); out = []
    for _, _, sent in items:
        if sent not in out: out.append(sent)
        if len(out) == 2: break
    return out

def how_you_compare(o, collected, home_word, company, cfg):
    nl = cfg.get("newsletter", {}); rules = nl.get("compare", {}); co = cfg.get("company", {}); S = company.get("survey", {}) or {}; R = company.get("renewals", {}) or {}; C = company.get("collections", {}) or {}
    short = co.get("short_name", "we"); bits = []
    if rules.get("collections", True) and C.get("rate_pct") is not None:
        med = BENCH.get("rent_collection_median") if BENCH_OK else None
        if collected is not None:
            bits.append(f"Rent collected on your {home_word}: {collected:.1f}% over the last 90 days, {short} overall {C['rate_pct']:.1f}%" + (f", verified property managers nationally {med}%." if med is not None else "."))
        else:
            bits.append(f"Across every home we manage, rent collected ran {C['rate_pct']:.1f}% over the last 90 days" + (f"; the verified-PM median is {med}%." if med is not None else "."))
    certs = [f"our {c['metric']} at {c['value']} (verified-PM median {c['benchmark']})" for c in nl.get("certifications_to_feature", []) if c.get("metric") and c.get("value") and c.get("benchmark")] if rules.get("certifications", True) else []
    if certs: bits.append("PropertyManagement.com has certified " + (" and ".join(certs) if len(certs) <= 2 else ", ".join(certs[:-1]) + ", and " + certs[-1]) + ".")
    if rules.get("survey", True) and S.get("nps") is not None and S.get("responses"):
        nps_b = f", against +{BENCH['nps_all']} across all verified property managers" if BENCH_OK and BENCH.get("nps_all") is not None else ""
        bits.append(f"In the PropertyManagement.com property-owner survey, {S['responses']} of our property owners have rated us: a Net Promoter Score of +{S['nps']:.0f}{nps_b}.")
    if BENCH_OK and rules.get("renewals", True) and R.get("rate_pct") is not None and R["rate_pct"] >= BENCH["renewal_median"] - rules.get("renewal_within_pct", 5):
        bits.append(f"Lease renewals across our book ran {R['rate_pct']:.0f}% last quarter, against the verified-PM median of {BENCH['renewal_median']}%.")
    return " ".join(bits) or "Verified comparisons appear here once the survey and collection data are loaded."


# ---- visuals -----------------------------------------------------------------------------------------------------
# Email visuals are built from table cells with inline styles (the only thing every mail client renders). The report page and studio may use SVG.
def email_chip(text, bg, fg="#ffffff"):
    return f'<span style="display:inline-block;background:{bg};color:{fg};font-size:11px;font-weight:700;letter-spacing:.02em;padding:3px 8px;border-radius:999px;white-space:nowrap;">{e(text)}</span>'

def unit_status(u):
    """(label, css class, email colour) for one unit."""
    if u["status"] == "leased": return "Leased", "leased", None
    if u["status"] == "notice": return "Notice given", "notice", "#B54708"
    if u.get("pre_leased"): return "Pre-leased", "pre", "#067647"
    d = u.get("days_vacant") or 0
    return (f"Vacant {d:.0f} d" if d else "Between tenants"), ("v60" if d > 60 else "v30" if d > 30 else "vac"), ("#B42318" if d > 60 else "#B54708" if d > 30 else "#98A2B3")

def email_unit_cells(units, primary, per_row=20):
    """A row of small coloured cells, one per unit: leased in the brand colour, vacant grey, aged vacancies amber/red. Table cells, so it survives Outlook."""
    if not units: return ""
    rows = [units[i:i + per_row] for i in range(0, len(units), per_row)]; out = ['<table role="presentation" cellpadding="0" cellspacing="2" border="0" style="border-collapse:separate;">']
    for r in rows:
        out.append("<tr>")
        for u in r:
            lab, cls, col = unit_status(u); bg = primary if cls == "leased" else (col or "#E5E7EB"); border = "" if cls != "vac" else "border:1px solid #CBD2DC;"
            out.append(f'<td title="{e(u["unit"])}: {e(lab)}" style="width:12px;height:12px;background:{bg};{border}border-radius:3px;font-size:0;line-height:0;">&nbsp;</td>')
        out.append("</tr>")
    out.append("</table>"); return "".join(out)

def email_property_rows(P, primary):
    """One table row per property: address, the unit cells, a status chip, rent."""
    rows = []
    for p in P:
        units = p.get("units_detail", []); w, bits = home_line(p)
        if p["units"] > 1: chip = email_chip(f"{p['occupied']} of {p['units']} leased", primary if p["occupied"] == p["units"] else "#B54708" if p["occupied"] < p["units"] * 0.7 else "#475467")
        elif units: lab, cls, col = unit_status(units[0]); chip = email_chip(lab, primary if cls == "leased" else col or "#98A2B3")
        else: chip = ""
        sub = bits.split(": ", 1)[-1]
        rows.append(f'<tr><td style="padding:10px 0;border-top:1px solid #EEF0F4;vertical-align:top;"><div style="font-size:14px;font-weight:700;color:#111827;">{e(w[0].upper() + w[1:])}</div><div style="font-size:12.5px;color:#6b7280;margin-top:2px;">{e(sub)}</div><div style="margin-top:6px;">{email_unit_cells(units, primary)}</div></td><td style="padding:10px 0 10px 12px;border-top:1px solid #EEF0F4;text-align:right;vertical-align:top;white-space:nowrap;">{chip}<div style="font-size:13px;font-weight:700;color:#111827;margin-top:6px;">{e(money(p.get("rent_month")) + "/mo" if p.get("rent_month") else "")}</div></td></tr>')
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">' + "".join(rows) + "</table>"

def email_compare_bars(rows_, primary, accent):
    """rows_: [(label, value_pct, colour)], drawn as table-cell bars to a common 100% scale with the label left and the value right."""
    out = ['<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 4px;">']
    for lab, v, col in rows_:
        if v is None: continue
        w = max(2, min(100, v)); out.append(f'<tr><td style="width:34%;font-size:12.5px;color:#374151;padding:3px 8px 3px 0;">{e(lab)}</td><td style="padding:3px 0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="width:{w:.0f}%;background:{col};height:9px;border-radius:5px;font-size:0;line-height:0;">&nbsp;</td><td style="font-size:0;line-height:0;">&nbsp;</td></tr></table></td><td style="width:14%;text-align:right;font-size:12.5px;font-weight:700;color:#111827;padding:3px 0 3px 8px;">{v:.1f}%</td></tr>')
    out.append("</table>"); return "".join(out)

def svg_compare(rows_, width=520):
    """Report-page version of the comparison bars."""
    rows_ = [r for r in rows_ if r[1] is not None]
    if not rows_: return ""
    h = 26 * len(rows_) + 6; out = [f'<svg viewBox="0 0 {width} {h}" width="100%" style="max-width:{width}px;display:block" role="img">']
    for i, (lab, v, col) in enumerate(rows_):
        y = i * 26 + 3; bw = (width - 220) * max(0, min(100, v)) / 100
        out.append(f'<text x="150" y="{y+15}" text-anchor="end" font-size="12.5" fill="#374151">{e(lab)}</text><rect x="160" y="{y+5}" width="{width-220}" height="12" rx="6" fill="#EEF0F4"/><rect x="160" y="{y+5}" width="{bw:.1f}" height="12" rx="6" fill="{col}"/><text x="{width-52}" y="{y+15}" font-size="12.5" font-weight="700" fill="#111827">{v:.1f}%</text>')
    out.append("</svg>"); return "".join(out)

def svg_donut(occupied, total, primary, size=110):
    """Occupancy ring: leased share of units."""
    if not total: return ""
    import math
    r = 44; c = 2 * math.pi * r; frac = occupied / total; dash = f"{c*frac:.1f} {c*(1-frac):.1f}"
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img"><circle cx="55" cy="55" r="{r}" fill="none" stroke="#EEF0F4" stroke-width="12"/>'
            f'<circle cx="55" cy="55" r="{r}" fill="none" stroke="{primary}" stroke-width="12" stroke-dasharray="{dash}" stroke-dashoffset="{c/4:.1f}" stroke-linecap="round" transform="rotate(-90 55 55)"/>'
            f'<text x="55" y="52" text-anchor="middle" font-size="20" font-weight="700" fill="#111827">{occupied}/{total}</text><text x="55" y="70" text-anchor="middle" font-size="11" fill="#6b7280">leased</text></svg>')

def svg_lease_calendar(P, month_start, primary, accent, width=520):
    """Twelve months from the send month; a column per month with the number of this owner's leases ending in it."""
    counts = collections.Counter()
    for p in P:
        for u in p.get("units_detail", []):
            if u.get("lease_end"):
                d = dt.date.fromisoformat(u["lease_end"]); k = (d.year - month_start.year) * 12 + d.month - month_start.month
                if 0 <= k < 12: counts[k] += 1
    if not counts: return ""
    vmax = max(counts.values()); colw = (width - 20) / 12; h = 90
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" style="max-width:{width}px;display:block" role="img">']
    for k in range(12):
        m = month_start.month - 1 + k; y = month_start.year + m // 12; m = m % 12 + 1; lab = dt.date(y, m, 1).strftime("%b"); v = counts.get(k, 0); bh = 50 * v / vmax if vmax else 0; x = 10 + k * colw
        out.append(f'<rect x="{x+4:.1f}" y="{60-bh:.1f}" width="{colw-8:.1f}" height="{bh:.1f}" rx="3" fill="{accent if v else "#EEF0F4"}"/>' + (f'<text x="{x+colw/2:.1f}" y="{55-bh:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="#111827">{v}</text>' if v else "") + f'<text x="{x+colw/2:.1f}" y="78" text-anchor="middle" font-size="11" fill="#6b7280">{lab}</text>')
    out.append("</svg>"); return "".join(out)

def html_unit_chips(P):
    """Report page / studio version of the unit cells (CSS classes, no inline colours)."""
    out = []
    for p in P:
        chips = "".join(f'<i class="u {unit_status(u)[1]}" title="{e(u["unit"])}: {e(unit_status(u)[0])}"></i>' for u in p.get("units_detail", []))
        out.append(f'<span class="chips">{chips}</span>')
    return out

def build_rows(company, owners, cfg, month, base_url, salt):
    co = cfg.get("company", {}); team = {m["first_name"]: m for m in cfg.get("team", {}).get("managers", [])}; nl = cfg.get("newsletter", {}); excl_cfg = cfg.get("exclusions", {})
    as_of = (company.get("as_of", {}) or {}).get("rent_roll") or dt.date.today().isoformat(); y, mo = month.split("-"); month_start = dt.date(int(y), int(mo), 1)
    global MARKET_OK; MARKET_OK = bool(nl.get("show_rent_vs_market", True))
    rows, excluded, eligible = [], [], []
    for o in owners:
        reason = None
        if o["tier"] == "Departed": reason = "management ended"
        elif excl_cfg.get("management_end_date_set", True) and any(s["signal"].startswith("Management end date") for s in o["signals"]): reason = "management end date set"
        elif excl_cfg.get("no_email", True) and not o["emails"]: reason = "no email on the owner directory"
        elif o["units"] == 0: reason = "no active units on the rent roll"
        if reason: excluded.append({"owner": o["name"], "owner_id": o["owner_id"], "reason": reason}); continue
        eligible.append(o)
    groups = {}
    for o in eligible: groups.setdefault(o["emails"][0].lower(), []).append(o)
    merged_log = [{"email": em, "owners": (grp[0].get("merged_from") if len(grp) == 1 else [n for g in grp for n in (g.get("merged_from") or [g.get("display_name") or g["name"]])])} for em, grp in groups.items() if len(grp) > 1 or grp[0].get("merged_from")]
    for em, grp in groups.items():
        o = merge_owners(grp)
        P = [p for p in o["properties_detail"] if p.get("units", 0) > 0]   # a property with no rent-roll units (a lot, a shell, a placeholder) has nothing to say to its owner
        if not P: excluded.append({"owner": o.get("display_name") or o["name"], "owner_id": o["owner_id"], "reason": "no active units on the rent roll"}); continue
        mgr_key = (o["managers"] or ["Unassigned"])[0]; m = team.get(mgr_key, {})
        unassigned = mgr_key in ("Unassigned", ""); mgr = "our team" if unassigned else mgr_key
        mgr_name = (co.get("short_name", "our") + " team") if unassigned else (m.get("full_name") or mgr_key); mgr_phone = (m.get("phone") if not unassigned else None) or co.get("phone", "")
        n = o["properties"]; home_word = "home" if (n == 1 and o["units"] == 1) else ("building" if n == 1 else ("homes" if all(p["units"] == 1 for p in P) else "properties"))
        ch = sum(p.get("charged_90d") or 0 for p in P); paid = sum((p.get("charged_90d") or 0) * (p.get("collected_90d_pct") or 0) / 100 for p in P)
        collected = round(100 * paid / ch, 1) if (ch and o["occupied"]) else None
        past_due = max(o.get("past_due") or 0, 0); recs = recommendations(P, cfg, month_start, mgr)
        coming = " ".join(recs) if recs else f"No leases end in the next {LEASE_HORIZON_DAYS} days and nothing is vacant. Nothing you need to decide this month; {mgr} will flag anything that changes."
        first = o["first_name"] or ""; token = hashlib.sha1(f"{salt}:{o['owner_id']}".encode()).hexdigest()[:16]
        pre = [f"{o['occupied']} of {o['units']} leased"] + ([f"{pct(collected)} of rent collected"] if collected is not None else []) + ["what is coming up"]
        primary = cfg.get("brand", {}).get("primary", "#0B2545"); accent = cfg.get("brand", {}).get("accent", "#4A5568"); C = company.get("collections", {}) or {}
        all_units = [u for p in P for u in p.get("units_detail", [])]
        cmp_rows = [(f"Your {home_word}", collected, primary), (co.get("short_name", "Company") + " overall", C.get("rate_pct"), "#98A2B3")]
        if collected is None:
            cmp_rows = [(co.get("short_name", "Company") + " overall", C.get("rate_pct"), primary)]
        if BENCH_OK and BENCH.get("rent_collection_median") is not None:
            cmp_rows.append(("Verified PMs (median)", BENCH["rent_collection_median"], accent))
        row = {"owner_id": o["owner_id"], "email": o["emails"][0], "first_name": first or "there", "owner_name": o.get("display_name") or o["name"], "manager_first": mgr, "manager_name": mgr_name, "manager_phone": mgr_phone,
               "homes_rows": email_property_rows(P, primary), "occupancy_cells": email_unit_cells(all_units, primary), "compare_bars": email_compare_bars(cmp_rows, primary, accent), "compare_note": "Rent collected over the last 90 days." if collected is not None else "Rent collected over the last 90 days across every home we manage.",
               "month": month, "month_label": month_label(month), "home_word": home_word, "home_word_upper": home_word.upper(), "properties_count": n, "units": o["units"], "occupied": o["occupied"],
               "subject": (f"{first}, your" if first else "Your") + f" {month_label(month)} property update from {co.get('short_name', co.get('name', 'us'))}",
               "preheader": ", ".join(pre[:-1]) + ", and " + pre[-1] + ".",
               "intro_line": f"A short monthly read on your {home_word}: the numbers, what is coming up, and what we changed.",
               "occupancy_txt": f"{o['occupied']} of {o['units']}", "occupancy_label": ("units" if o["units"] > 1 else "unit") + " leased today",
               "collected_txt": pct(collected), "collected_label": "of rent collected, last 90 days" if collected is not None else "no rent charges this period",
               "rent_txt": money(o["rent_month"]), "rent_label": "in monthly rent on leased units", "past_due_txt": money(past_due), "past_due_label": "past due today",
               "homes_paragraph": homes_paragraph(P), "coming_up": coming, "company_block": nl.get("company_block", "[CONFIRM: company update]"),
               "how_you_compare": how_you_compare(o, collected, home_word, company, cfg), "profile_url": co.get("pmcom_profile_url", "https://propertymanagement.com/"),
               "report_url": f"{base_url.rstrip('/')}/{token}.html", "report_token": token,
               "report_button": (f'<a href="{base_url.rstrip("/")}/{token}.html" style="display:inline-block;background:{cfg.get("brand", {}).get("primary", "#0B2545")};color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:11px 16px;border-radius:9px;">See your portfolio report</a>' if nl.get("report_link") else ""),
               "report_line": (f"See your portfolio report: {base_url.rstrip('/')}/{token}.html" if nl.get("report_link") else ""),
               "closing_line": f"Questions about your {home_word}? Reply to this email or call {mgr_name} at {mgr_phone}.", "referral_line": nl.get("referral_line", ""),
               "company_name": co.get("name", ""), "company_phone": co.get("phone", ""), "logo_url": co.get("logo_url", ""),
               "brand_primary": cfg.get("brand", {}).get("primary", "#0B2545"), "brand_accent": cfg.get("brand", {}).get("accent", "#4A5568"),
               "font_display": cfg.get("brand", {}).get("font_display", "Georgia, serif"), "font_body": cfg.get("brand", {}).get("font_body", "Helvetica Neue, Arial, sans-serif"),
               "font_link": (f'<link rel="stylesheet" href="{cfg.get("brand", {}).get("font_link")}">' if cfg.get("brand", {}).get("font_link") else ""),
               "as_of": as_of, "benchmarks_as_of": BENCH.get("as_of") if BENCH_OK else "", "footer_note": "You receive this because we manage property for you.",
               "_needs_confirm": "[CONFIRM" in coming, "_radar_tier": o["tier"], "_properties": P, "_collected": collected, "_company_collections": C,
               "_survey_band": ("promoter" if (o.get("survey") or {}).get("nps", 0) >= 9 else "detractor" if (o.get("survey") or {}).get("nps", 10) <= 6 else "passive") if o.get("survey") else "no survey"}
        rows.append(row)
    return rows, excluded, merged_log

def report_page(row, cfg):
    P = row["_properties"]; co = cfg.get("company", {}); primary = row["brand_primary"]; accent = row["brand_accent"]
    y, mo = row["month"].split("-"); month_start = dt.date(int(y), int(mo), 1); chips = html_unit_chips(P)
    C = row.get("_company_collections") or {}
    cmp_rows = [(f"Your {row['home_word']}", row.get("_collected"), primary), (co.get("short_name", "Company") + " overall", C.get("rate_pct"), "#98A2B3")]
    if BENCH_OK and BENCH.get("rent_collection_median") is not None:
        cmp_rows.append(("Verified PMs (median)", BENCH["rent_collection_median"], accent))
    cal = svg_lease_calendar(P, month_start, primary, accent)
    def tr(p):
        vs = market_phrase(p.get("rent_vs_market_pct"), p["units"] > 1) or "n/a"
        col = "n/a" if p.get("collected_90d_pct") is None else f"{p['collected_90d_pct']:.1f}%"
        nxt = nice_date(p["next_lease_end"]) if p.get("next_lease_end") else ("month to month" if p.get("m2m_units") else "none in 120 days")
        turns = str(p.get("turns_12mo", 0)) + (f" · median {p['turn_median_days']} d" if p.get("turn_median_days") else "")
        return (f"<tr><td>{e(where(p))}<br>{chips[P.index(p)]}</td><td>{p['occupied']}/{p['units']}</td><td>{money(p.get('rent_month'))}</td><td>{e(vs)}</td><td>{e(nxt)}</td>"
                f"<td>{turns}</td><td>{money(p.get('past_due'))}</td><td>{col}</td></tr>")
    trs = "".join(tr(p) for p in P)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Portfolio report · {e(row['first_name'])}</title>
<style>body{{margin:0;background:#f4f5f8;font-family:{row['font_body']};color:#1f2937}}.wrap{{max-width:900px;margin:0 auto;padding:24px 20px 60px}}.hd{{background:{primary};color:#fff;border-radius:12px;padding:18px 22px}}.hd h1{{margin:6px 0 0;font-family:{row['font_display']};font-size:22px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}}.t{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px}}.t b{{display:block;font-size:22px;color:{primary}}}.t span{{font-size:12px;color:#6b7280}}
.chips{{display:inline-flex;flex-wrap:wrap;gap:3px;margin-top:4px}}.u{{display:inline-block;width:12px;height:12px;border-radius:3px;background:#E5E7EB;border:1px solid #CBD2DC;box-sizing:border-box}}.u.leased{{background:{primary};border-color:{primary}}}.u.notice{{background:#B54708;border-color:#B54708}}.u.pre{{background:#067647;border-color:#067647}}.u.v30{{background:#B54708;border-color:#B54708}}.u.v60{{background:#B42318;border-color:#B42318}}
.viz{{display:grid;grid-template-columns:130px 1fr;gap:16px;align-items:center;background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px;margin:12px 0}}@media(max-width:600px){{.viz{{grid-template-columns:1fr}}}}.legend{{font-size:11.5px;color:#6b7280;margin-top:6px}}.legend i{{margin-right:3px;vertical-align:middle}}
.tw{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;font-size:13.5px}}th{{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#6b7280;padding:8px 10px;border-bottom:2px solid #e5e7eb;white-space:nowrap}}td{{padding:8px 10px;border-bottom:1px solid #f1f3f7}}h2{{font-size:16px;margin:22px 0 8px}}p{{font-size:14px;line-height:1.55}}.foot{{font-size:12px;color:#6b7280;margin-top:24px}}a{{color:{primary}}}</style></head><body><div class="wrap">
<div class="hd"><div style="font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:{row['brand_accent']}">{e(co.get('name',''))} · Portfolio report · {e(row['month_label'])}</div><h1>{e(row['first_name'])}, your {e(row['home_word'])} at a glance</h1></div>
<div class="tiles"><div class="t"><b>{e(row['occupancy_txt'])}</b><span>{e(row['occupancy_label'])}</span></div><div class="t"><b>{e(row['collected_txt'])}</b><span>{e(row['collected_label'])}</span></div><div class="t"><b>{e(row['rent_txt'])}</b><span>{e(row['rent_label'])}</span></div><div class="t"><b>{e(row['past_due_txt'])}</b><span>{e(row['past_due_label'])}</span></div></div>
<div class="viz">{svg_donut(row['occupied'], row['units'], primary)}<div><div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#6b7280">Rent collected, last 90 days</div>{svg_compare(cmp_rows)}<div class="legend"><i class="u leased"></i> leased &nbsp; <i class="u"></i> between tenants &nbsp; <i class="u v30"></i> vacant 30+ days &nbsp; <i class="u v60"></i> vacant 60+ days &nbsp; <i class="u pre"></i> pre-leased &nbsp; <i class="u notice"></i> notice given</div></div></div>
{('<h2>Lease calendar, next 12 months</h2><div class="viz" style="grid-template-columns:1fr">' + cal + '<div class="legend">Leases ending each month across your ' + e(row['home_word']) + '. We start renewal conversations 90 days out.</div></div>') if cal else ''}
<h2>Property by property</h2><div class="tw"><table><thead><tr><th>Property</th><th>Leased</th><th>Rent / mo</th><th>vs market</th><th>Next lease end</th><th>Maintenance jobs, 12 mo</th><th>Past due</th><th>Collected, 90 d</th></tr></thead><tbody>{trs}</tbody></table></div>
<h2>Coming up</h2><p>{e(row['coming_up'])}</p><h2>How you compare</h2><p>{e(row['how_you_compare'])} <a href="{e(row['profile_url'])}">See our verified profile on PropertyManagement.com</a>.</p><h2>What we're changing</h2><p>{e(row['company_block'])}</p>
<p>{e(row['closing_line'])}</p><div class="foot">Numbers as of {e(row['as_of'])} from {e(co.get('name',''))}'s property management system. Verified-PM comparisons from PropertyManagement.com{" as of " + e(BENCH.get("as_of", "")) if BENCH_OK else " (benchmarks not loaded)"}. This page is for the property owner it was prepared for.</div></div></body></html>"""

def studio(rows, excluded, tpl_html, tpl_txt, cfg, month, merged_log=()):
    merged_log = list(merged_log)
    public_rows = [{k: v for k, v in r.items() if k not in ("_properties", "_company_collections")} for r in rows]
    data = json.dumps({"month": month, "rows": public_rows, "excluded": excluded, "template_html": tpl_html, "template_txt": tpl_txt, "company": cfg.get("company", {}).get("name", ""), "merged_inboxes": merged_log}).replace("</", "<\\/")
    return r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Owner Update Studio</title>
<style>:root{--ink:#111827;--muted:#6b7280;--line:#e5e7eb;--bg:#f4f5f8;--pri:#0B2545}body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
header{background:var(--pri);color:#fff;padding:14px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}header h1{font-size:16px;margin:0}header .m{color:#d1d5db;font-size:12.5px}select,button,input,textarea{font:inherit}select{padding:6px 8px;border-radius:8px;border:1px solid var(--line);min-width:260px}
button{background:#fff;color:var(--pri);border:1px solid var(--line);border-radius:8px;padding:7px 12px;font-weight:700;cursor:pointer}button.p{background:var(--pri);color:#fff;border:0}
main{display:grid;grid-template-columns:420px 1fr;gap:0;height:calc(100vh - 108px)}@media(max-width:900px){main{grid-template-columns:1fr;height:auto}}
aside{overflow:auto;background:#fff;border-right:1px solid var(--line);padding:14px 16px}aside h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:14px 0 6px}
.f{margin-bottom:9px}.f label{display:block;font-size:11.5px;color:var(--muted);margin-bottom:2px}.f input,.f textarea{width:100%;box-sizing:border-box;border:1px solid var(--line);border-radius:8px;padding:6px 8px}.f textarea{min-height:64px;resize:vertical}.f.edited input,.f.edited textarea{border-color:#B54708;background:#fffbea}
.stage{overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}iframe{width:100%;height:calc(100vh - 150px);min-height:600px;border:1px solid var(--line);border-radius:12px;background:#fff}
.meta{display:flex;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--muted)}.pill{background:#eef1fa;border-radius:999px;padding:2px 9px;color:var(--pri);font-weight:700}.flag{background:#fff3d6;color:#8a5300;border-radius:999px;padding:2px 9px;font-weight:700}
.filters{display:flex;gap:8px;align-items:center;padding:8px 20px;background:#fff;border-bottom:1px solid var(--line);flex-wrap:wrap}.fl{font-size:12px;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}.pill{background:#f4f5f8;border:1px solid var(--line);border-radius:999px;padding:4px 11px;font-size:12.5px;font-weight:600;color:#374151}.pill.on{background:var(--pri);color:#fff;border-color:var(--pri)}
.ready{display:flex;align-items:center;gap:10px;font-size:12.5px;color:#374151}.ready .bar{width:220px;height:10px;border-radius:5px;background:#eef0f4;overflow:hidden;display:flex}.ready .bar i{display:block;height:100%}.ready .ok{background:#067647}.ready .need{background:#B54708}
.toast{position:fixed;bottom:16px;right:16px;background:#111827;color:#fff;padding:10px 14px;border-radius:10px;opacity:0;transition:opacity .2s}.toast.on{opacity:1}details{margin-top:10px;font-size:12.5px;color:var(--muted)}</style></head><body>
<header><h1>Owner Update Studio</h1><span class="m" id="company"></span><select id="pick"></select><span class="m" id="count"></span><span style="flex:1"></span><button id="txt">Plain text</button><button id="reset">Reset owner</button><button class="p" id="export">Export merge CSV</button><button id="exportjson">Export JSON</button></header>
<div class="filters"><span class="fl">Show</span><button class="pill on" data-f="all">All</button><button class="pill" data-f="confirm">Needs a sentence</button><button class="pill" data-f="call">Radar: call this week</button><button class="pill" data-f="edited">Edited</button><button class="pill" data-f="nosurvey">No survey</button><span style="flex:1"></span><div class="ready" id="ready"></div></div>
<main><aside><div class="meta" id="meta"></div><h2>Editable fields</h2><div id="fields"></div><details><summary>Excluded from this send</summary><ul id="excl"></ul></details><details><summary>Owner records merged into one email</summary><ul id="merged"></ul></details></aside>
<div class="stage"><div class="meta"><span>Preview renders from the same template and fields the merge tool will use. Edits are held in this page until you export.</span></div><iframe id="frame" title="Email preview"></iframe></div></main>
<div class="toast" id="toast"></div>
<script id="data" type="application/json">""" + data + r"""</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent); const rows = D.rows; const orig = JSON.parse(JSON.stringify(rows));
const EDITABLE = ["subject","preheader","intro_line","occupancy_txt","occupancy_label","collected_txt","collected_label","rent_txt","rent_label","past_due_txt","past_due_label","homes_paragraph","coming_up","company_block","how_you_compare","report_url","closing_line","referral_line","manager_name","manager_phone","first_name","email"];
const LONG = new Set(["intro_line","homes_paragraph","coming_up","company_block","how_you_compare","closing_line","referral_line"]);
const pick = document.getElementById('pick'), fields = document.getElementById('fields'), frame = document.getElementById('frame'), meta = document.getElementById('meta'); let i = 0, plain = false;
document.getElementById('company').textContent = D.company + ' · ' + D.month; 
let filter = 'all';
function matches(r, k){ if (filter === 'confirm') return String(r.coming_up).includes('[CONFIRM'); if (filter === 'call') return r._radar_tier === 'Call this week'; if (filter === 'edited') return EDITABLE.some(f => r[f] !== orig[k][f]); if (filter === 'nosurvey') return r._survey_band === 'no survey'; return true; }
function buildPicker(){ pick.innerHTML = ''; let n = 0; rows.forEach((r, k) => { if (!matches(r, k)) return; n++; const o = document.createElement('option'); o.value = k; o.textContent = (r.owner_name || r.first_name) + ' · ' + r.units + ' units · ' + r.manager_first + (String(r.coming_up).includes('[CONFIRM') ? ' · needs a sentence' : '') + (r._radar_tier === 'Call this week' ? ' · call first' : ''); pick.appendChild(o); });
  if (n && ![...pick.options].some(o => +o.value === i)) { i = +pick.options[0].value; buildFields(); render(); } pick.value = i; document.getElementById('count').textContent = rows.length + ' owners in this send' + (n !== rows.length ? ' · showing ' + n : '') + (rows.some(r => String(r.company_block).includes('[CONFIRM')) ? ' · company update still says [CONFIRM]' : ''); }
function readiness(){ const need = rows.filter(r => String(r.coming_up).includes('[CONFIRM')).length, ok = rows.length - need, cb = rows.some(r => String(r.company_block).includes('[CONFIRM'));
  document.getElementById('ready').innerHTML = '<span><b>' + ok + '</b> ready</span><div class="bar"><i class="ok" style="width:' + (100 * ok / Math.max(rows.length, 1)) + '%"></i><i class="need" style="width:' + (100 * need / Math.max(rows.length, 1)) + '%"></i></div><span><b>' + need + '</b> need a sentence</span>' + (cb ? '<span class="flag">company update missing</span>' : ''); }
document.querySelectorAll('.pill').forEach(b => b.addEventListener('click', () => { document.querySelectorAll('.pill').forEach(x => x.classList.remove('on')); b.classList.add('on'); filter = b.dataset.f; buildPicker(); }));
buildPicker(); readiness();
document.getElementById('excl').innerHTML = D.excluded.map(x => '<li>' + esc(x.owner) + ' (' + esc(x.reason) + ')</li>').join('') || '<li>none</li>';
const mi = document.getElementById('merged'); if (mi) mi.innerHTML = (D.merged_inboxes || []).map(x => '<li>' + esc(x.owners.join(' + ')) + ' &rarr; one email</li>').join('') || '<li>none</li>';
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function fill(t, r){ return t.replace(/\{\{(\w+)\}\}/g, (m, k) => (k in r ? String(r[k]) : '')); }
function render(){ const r = rows[i]; frame.srcdoc = plain ? '<pre style="white-space:pre-wrap;font:14px/1.5 Menlo,monospace;padding:20px">' + esc(fill(D.template_txt, r)) + '</pre>' : fill(D.template_html, r);
  meta.innerHTML = '<span class="pill">' + esc(r.owner_name || r.first_name) + '</span><span>' + esc(r.email) + '</span><span>' + r.properties_count + ' propert' + (r.properties_count == 1 ? 'y' : 'ies') + ' · ' + r.units + ' units</span><span>survey: ' + esc(r._survey_band) + '</span><span>radar: ' + esc(r._radar_tier) + '</span>' + (r._needs_confirm ? '<span class="flag">has [CONFIRM] text</span>' : '') + (isEdited(r) ? '<span class="flag">edited</span>' : ''); }
function isEdited(r){ const o = orig[i]; return EDITABLE.some(k => r[k] !== o[k]); }
function buildFields(){ fields.innerHTML = ''; const r = rows[i], o = orig[i]; EDITABLE.forEach(k => { const w = document.createElement('div'); w.className = 'f' + (r[k] !== o[k] ? ' edited' : ''); const el = LONG.has(k) ? document.createElement('textarea') : document.createElement('input'); el.value = r[k] == null ? '' : r[k]; el.id = 'f_' + k;
  el.addEventListener('input', () => { r[k] = el.value; w.classList.toggle('edited', r[k] !== o[k]); render(); readiness(); }); w.innerHTML = '<label>' + k + '</label>'; w.appendChild(el); fields.appendChild(w); }); }
pick.addEventListener('change', () => { i = +pick.value; buildFields(); render(); });
document.getElementById('txt').addEventListener('click', e => { plain = !plain; e.target.textContent = plain ? 'HTML' : 'Plain text'; render(); });
document.getElementById('reset').addEventListener('click', () => { Object.assign(rows[i], orig[i]); buildFields(); render(); toast('Owner reset'); });
function csv(){ const cols = Object.keys(rows[0]).filter(k => !k.startsWith('_')); const q = v => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"'; return [cols.join(','), ...rows.map(r => cols.map(k => q(r[k])).join(','))].join('\n'); }
function download(name, text, type){ try { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name; document.body.appendChild(a); a.click(); a.remove(); toast('Downloaded ' + name + ' (if nothing happened, it was copied to your clipboard instead)'); } catch (e) {} navigator.clipboard && navigator.clipboard.writeText(text).catch(() => {}); }
document.getElementById('export').addEventListener('click', () => download('merge-' + D.month + '.csv', csv(), 'text/csv'));
document.getElementById('exportjson').addEventListener('click', () => download('merge-' + D.month + '.json', JSON.stringify({month: D.month, rows: rows.map(r => Object.fromEntries(Object.entries(r).filter(([k]) => !k.startsWith('_'))))}, null, 1), 'application/json'));
function toast(m){ const t = document.getElementById('toast'); t.textContent = m; t.classList.add('on'); setTimeout(() => t.classList.remove('on'), 2600); }
if (rows.length) { buildFields(); render(); }
</script></body></html>"""

def pick_previews(rows, n):
    picks = []
    def add(r):
        if r is not None and r not in picks: picks.append(r)
    add(next((r for r in rows if r["properties_count"] == 1 and r["units"] == 1 and not r["_needs_confirm"] and r["coming_up"].startswith("No leases")), None))   # the common case: one quiet home
    add(max(rows, key=lambda r: r["units"], default=None)); add(next((r for r in rows if r["_needs_confirm"]), None)); add(next((r for r in rows if r["_survey_band"] == "promoter"), None))
    add(next((r for r in rows if "lease at your" in r["coming_up"]), None)); add(next((r for r in rows if r["properties_count"] >= 3), None))
    for r in rows:
        if len(picks) >= n: break
        add(r)
    return picks[:n]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--config", required=True); ap.add_argument("--month", required=True)
    ap.add_argument("--benchmarks"); ap.add_argument("--previews", type=int, default=6); ap.add_argument("--render-all", action="store_true"); ap.add_argument("--report-base-url"); ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(); cfg = json.load(open(a.config)); O = a.out; N = os.path.join(O, "newsletter")
    global BENCH, BENCH_OK
    BENCH = load_benchmarks(a.benchmarks) or {}
    BENCH_OK = available(BENCH)
    for d in ("previews", "reports", "rendered"):   # start clean: tokens and eligibility change month to month, stale files must not linger
        shutil.rmtree(os.path.join(N, d), ignore_errors=True)
    for d in ("previews", "reports"): os.makedirs(os.path.join(N, d), exist_ok=True)
    company = json.load(open(os.path.join(O, "company.json"))); owners = json.load(open(os.path.join(O, "owners.json")))
    tpl_html = open(os.path.join(ASSETS, "email-template.html")).read(); tpl_txt = open(os.path.join(ASSETS, "email-template.txt")).read()
    vis_path = os.path.join(ASSETS, "email-template-visual.html"); tpl_vis = open(vis_path).read() if os.path.exists(vis_path) else tpl_html   # visual = bars + chips as HTML tokens; for tools that pass HTML through per recipient
    base = a.report_base_url or cfg.get("newsletter", {}).get("report_base_url", "https://REPLACE-ME/owner-reports/"); salt = cfg.get("newsletter", {}).get("report_salt") or cfg.get("company", {}).get("name", "salt")
    rows, excluded, merged_log = build_rows(company, owners, cfg, a.month, base, salt)
    public = lambda r: {k: v for k, v in r.items() if not k.startswith("_")}
    VISUAL = ("homes_rows", "occupancy_cells", "compare_bars")
    cols = [k for k in public(rows[0]).keys() if k not in VISUAL] if rows else []
    with open(os.path.join(N, "merge.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); [w.writerow(public(r)) for r in rows]
    with open(os.path.join(N, "merge-visual.csv"), "w", newline="") as f:   # same rows plus the HTML snippet columns, for merge tools that pass HTML through
        w = csv.DictWriter(f, fieldnames=cols + list(VISUAL), extrasaction="ignore"); w.writeheader(); [w.writerow(public(r)) for r in rows]
    json.dump({"month": a.month, "rows": [{k: v for k, v in r.items() if k not in ("_properties", "_company_collections")} for r in rows], "excluded": excluded, "merged_inboxes": merged_log}, open(os.path.join(N, "merge.json"), "w"), indent=1)
    shutil.copy(os.path.join(ASSETS, "email-template.html"), os.path.join(N, "email-template.html")); shutil.copy(os.path.join(ASSETS, "email-template.txt"), os.path.join(N, "email-template.txt"))
    if os.path.exists(vis_path): shutil.copy(vis_path, os.path.join(N, "email-template-visual.html"))
    for r in pick_previews(rows, a.previews): open(os.path.join(N, "previews", f"{r['report_token']}-{re.sub(r'[^a-z0-9]+', '-', r['first_name'].lower())}.html"), "w").write(fill(tpl_vis, r))
    link_on = bool(cfg.get("newsletter", {}).get("report_link"))
    if link_on:   # the per-owner report pages only matter when the email links to them
        for r in rows: open(os.path.join(N, "reports", f"{r['report_token']}.html"), "w").write(report_page(r, cfg))
    if a.render_all:
        os.makedirs(os.path.join(N, "rendered"), exist_ok=True)
        for r in rows: open(os.path.join(N, "rendered", f"{r['report_token']}.html"), "w").write(fill(tpl_vis, r))
    open(os.path.join(N, "newsletter-studio.html"), "w").write(studio(rows, excluded, tpl_vis, tpl_txt, cfg, a.month, merged_log))
    kinds = collections.Counter("quiet" if r["coming_up"].startswith("No leases") else "vacancy" if "vacant" in r["coming_up"].split(".")[0] else "balance" if r["coming_up"].startswith("A tenant balance") else "lease" if "lease at your" in r["coming_up"] else "between tenants" for r in rows)
    summary = {"owners_in_send": len(rows), "excluded": len(excluded), "excluded_reasons": dict(collections.Counter(x["reason"] for x in excluded)), "coming_up_kinds": dict(kinds), "report_link": link_on, "report_pages": len(rows) if link_on else 0,
                      "needs_confirm": sum(1 for r in rows if r["_needs_confirm"]), "merged_inboxes": len(merged_log), "owner_records_merged": sum(len(x["owners"]) for x in merged_log), "company_block_placeholder": "[CONFIRM" in cfg.get("newsletter", {}).get("company_block", ""),
                      "previews": sorted(os.listdir(os.path.join(N, "previews"))), "studio": os.path.join(N, "newsletter-studio.html"), "reports_dir": os.path.join(N, "reports"), "report_base_url": base}
    json.dump(summary, open(os.path.join(N, "build-summary.json"), "w"), indent=1)
    if a.json: print(json.dumps(summary, indent=1))
    else: print(f"Owner update built for {a.month}: {len(rows)} inboxes in, {len(excluded)} owner records excluded, {summary['needs_confirm']} rows need a sentence, {summary['merged_inboxes']} inboxes merged" + (", company update still a placeholder" if summary["company_block_placeholder"] else "") + f". Studio: {summary['studio']}")

if __name__ == "__main__": main()
