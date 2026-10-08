#!/usr/bin/env python3
"""Render the Property Owner Retention Radar: the renewal-first retention play as one self-contained HTML page + a CSV for the task system.

Inputs (from appfolio_loader.py features): <out>/company.json, owners.json, inventory.json, data-quality.md
Options: --config client-config.json  --previous radar-run.json (last run)  --title "..."  --json (print machine-readable summary)
Outputs: <out>/radar-dashboard.html, <out>/call-list.csv, <out>/radar-run.json, <out>/radar-summary.json

What the page is: the survey results and the verified-PM benchmarks on top, then THIS WEEK'S FIVE, then two tables, survey detractors
(toggle to passives / promoters) and predictive detractors (owners who did not answer the survey but look like the ones who did,
unhappily). Every row pairs the owner with what is happening on their property today (vacancy) and the next renewal inside 90 days,
and names the play: bring the owner a win, do not reopen the old wound. The page surfaces the work; the manager does it in their
normal workflow. No notes, no statuses, no talk tracks on this page, by design.
"""
import argparse, collections, csv, datetime as dt, html, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pm_benchmarks import available, load as load_benchmarks
e = html.escape
def fmt_money(v): return "n/a" if v is None else f"${v:,.0f}"
def fmt_pct(v, nd=1): return "n/a" if v is None else f"{v:.{nd}f}%"
RED, AMBER, GREEN, GREY, INK = "#B42318", "#B54708", "#067647", "#98A2B3", "#111827"
SIGNAL_LABEL = {"vacancy_60": "unit vacant 60+ days", "vacancy_30": "unit vacant 30+ days", "owner_exit_moveout": "owner-initiated move-out", "management_ending": "management end date set",
                "owner_exit_note": "turn canceled with an owner-exit note", "cost_sig_above": "costs significantly above market", "cost_above": "costs above market", "statements_confusing": "statements confusing",
                "voicemail": "got voicemail", "expiring_no_renewal": "lease ending, no renewal started", "delinquency": "balances over a month of rent", "first_year": "first year with us",
                "payments_on_hold": "owner payments on hold", "no_owner_payment_90d": "no owner payment 90+ days", "turn_open_45d": "turn open 45+ days", "prior_tenant_loss": "former tenant left a balance",
                "new_property": "long-time owner, new property", "detractor": "survey detractor", "passive": "survey passive"}
HORIZON = 90

# ------------------------------------------------------------------ small visuals
def svg_stack(parts, width=200, height=14):
    total = sum(v for v, _, _ in parts) or 1; x = 0.0; out = [f'<svg class="bar" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img">']
    for v, c, t in parts:
        w = width * v / total; out.append(f'<rect x="{x:.1f}" y="3" width="{max(w, 0):.1f}" height="8" rx="2" fill="{c}"><title>{e(t)}: {v}</title></rect>'); x += w
    out.append("</svg>"); return "".join(out)

def unit_status(u):
    if u["status"] == "leased": return "leased" + (f", ends {u['lease_end']}" if u.get("lease_end") else ""), "leased"
    if u["status"] == "notice": return "notice given", "notice"
    if u.get("pre_leased"): return "pre-leased", "pre"
    d = u.get("days_vacant")
    if d is None: return "vacant, age not recorded", "vac"
    return (f"vacant {d:.0f} d" if d else "between tenants"), ("v60" if d > 60 else "v30" if d > 30 else "vac")

def chips(P):
    return "".join(f'<i class="u {unit_status(u)[1]}" title="{e(pd.get("address") or pd.get("city") or "")}: {e(u["unit"])}, {e(unit_status(u)[0])}"></i>' for pd in P for u in pd.get("units_detail", []))

# ------------------------------------------------------------------ the play
def where(pd): return pd.get("address") or f'{(pd.get("type") or "property").lower()} in {pd.get("city", "")}'

def vacancy_now(o):
    vac = [(pd, u) for pd in o["properties_detail"] for u in pd.get("units_detail", []) if u["status"] == "vacant" and not u.get("pre_leased")]
    if not vac: return None
    known = [(pd, u) for pd, u in vac if u.get("days_vacant") is not None]   # an unrecorded age is None, never 0
    days = max(u["days_vacant"] for _, u in known) if known else None; worst = max(known, key=lambda x: x[1]["days_vacant"]) if known else vac[0]
    return {"count": len(vac), "days": days, "address": where(worst[0]), "unit": worst[1]["unit"], "rent_ready": any(u.get("rent_ready") for _, u in vac), "posted": any(u.get("posted") for _, u in vac), "lease_up": all(u.get("never_leased") for _, u in vac)}

def next_renewal(o, today):
    best = None
    for pd in o["properties_detail"]:
        for u in pd.get("units_detail", []):
            if u["status"] == "vacant" or not u.get("lease_end"): continue
            d = dt.date.fromisoformat(u["lease_end"])
            if today <= d <= today + dt.timedelta(days=HORIZON) and (best is None or d < best["date"]):
                best = {"date": d, "address": where(pd), "unit": u["unit"], "rent": u.get("rent"), "rvm": pd.get("rent_vs_market_pct"), "multi": pd["units"] > 1}
    return best

def market_phrase(rvm):
    if rvm is None or abs(rvm) > 35: return "market comparison to confirm"
    if abs(rvm) < 5: return "rent in line with market"
    return f"rent {abs(rvm):.0f}% {'above' if rvm > 0 else 'below'} market"

def fmt_days(d): return "vacancy age not recorded" if d is None else f"{d:.0f} days"
def fmt_d(d): return "age unknown" if d is None else f"{d:.0f} d"

def band(o):
    s = o.get("survey") or {}; n = s.get("nps")
    if not isinstance(n, (int, float)): return None
    return "detractor" if n <= 6 else "passive" if n <= 8 else "promoter"

def ops_score(o): return sum(s["points"] for s in o["signals"] if s.get("type") == "ops" and s["points"] > 0)

def the_play(b, vac, ren, mgr_short):
    """One sentence the manager can act on. Order: vacancy today beats everything; then the renewal; then hold."""
    if vac:
        if vac["lease_up"]: return f"Lease-up: {vac['count']} unit{'s' if vac['count'] > 1 else ''} never leased. Send the first-showing report this week; the owner has no income yet."
        lead = f"Vacant today ({fmt_days(vac['days'])} at {vac['address']}" + (f", {vac['count']} units" if vac["count"] > 1 else "") + ")."
        tail = " Talk this week with the leasing plan and a lease-by date" + ("; it is rent-ready but not posted, post it first." if vac["rent_ready"] and not vac["posted"] else ".")
        return lead + tail
    if ren:
        return (f"Renewal {ren['date'].strftime('%b %d').replace(' 0', ' ')} at {ren['address']}" + (f" ({ren['unit']})" if ren["multi"] else "") + f", {market_phrase(ren['rvm'])}. "
                "Lock it, then bring the win: tenant kept, rent held or improved, one line of thanks for their patience.")
    return "No vacancy, no renewal inside 90 days. Hold; reach them with the monthly update, and run this play at the next renewal."

def priority(b, pred, vac, ren):
    """Lower is sooner. Actionable rows (a vacancy today or a renewal inside 90 days) come before rows with nothing to act on, so the week's five is always work."""
    if b == "detractor": return 0 if vac else 1 if ren else 4
    if pred: return 2 if vac else 3 if ren else 5
    if b == "passive": return 6 if (vac or ren) else 8
    return 9

# ------------------------------------------------------------------ page
CSS = """
:root{--pri:%(primary)s;--acc:%(accent)s;--ink:#111827;--muted:#6B7280;--line:#E5E7EB;--bg:#F4F5F8;--red:#B42318;--amber:#B54708;--green:#067647}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 %(font_body)s}.wrap{max-width:1180px;margin:0 auto;padding:0 20px 70px}
.top{background:var(--pri);color:#fff;padding:22px 0 24px}.top h1{margin:6px 0 4px;font-size:26px;letter-spacing:-.01em}.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.75);font-weight:700}.top p{margin:0;color:#D1D5DB;max-width:860px}
.ctrl{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid var(--line);padding:10px 0}.ctrl .wrap{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding-bottom:0}
.pill{background:#F4F5F8;border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:13px;font-weight:600;color:#374151;cursor:pointer}.pill.on{background:var(--pri);color:#fff;border-color:var(--pri)}.pill b{font-weight:800}
.ctrl input{padding:6px 10px;border:1px solid var(--line);border-radius:8px;min-width:220px;font:inherit}.sp{flex:1}.btn{background:#fff;border:1px solid var(--line);border-radius:8px;padding:6px 11px;font:inherit;font-weight:600;cursor:pointer}.btn.p{background:var(--pri);border-color:var(--pri);color:#fff}
.card{background:#fff;border-radius:14px;padding:16px 20px;box-shadow:0 1px 2px rgba(16,24,40,.06)}h2{margin:34px 0 10px;font-size:19px;letter-spacing:-.01em}h2 .meta{font-size:13px;color:var(--muted);font-weight:400;margin-left:8px}h4{margin:0 0 6px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.strip{display:grid;grid-template-columns:1.1fr 1.4fr;gap:12px;margin-top:16px}@media(max-width:900px){.strip{grid-template-columns:1fr}}
.nps .big{font-size:40px;font-weight:800;letter-spacing:-.02em;line-height:1}.nps .sub{color:var(--muted);font-size:13px;margin-top:4px}.lg{font-size:12px;color:var(--muted);margin-top:8px}.lg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin:0 3px 0 8px;vertical-align:middle}
.bench{border-top:4px solid var(--pri)}table.bt{width:100%;border-collapse:collapse;font-size:13.5px}table.bt td{padding:6px 8px;border-bottom:1px solid #F1F3F7;vertical-align:middle}table.bt td.me{font-size:18px;font-weight:800}table.bt td.gap{font-weight:800;white-space:nowrap}table.bt td.lab{color:#374151}table.bt .n{font-size:11px;color:var(--muted)}
.five{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.f{background:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 1px 2px rgba(16,24,40,.06);border-top:4px solid var(--red)}.f.pred{border-top-color:var(--amber)}.f .nm{font-weight:800;font-size:15px}.f .why{font-size:12.5px;color:var(--muted);margin:2px 0 8px}.f .play{font-size:13.5px}.f .mgr{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-top:8px}
table.tbl{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;font-size:13.5px;box-shadow:0 1px 2px rgba(16,24,40,.06)}table.tbl th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:9px 10px;border-bottom:2px solid var(--line);white-space:nowrap}table.tbl td{padding:9px 10px;border-bottom:1px solid #F1F3F7;vertical-align:top}table.tbl tr:last-child td{border-bottom:0}
.nm b{font-size:14px}.sub{font-size:12px;color:var(--muted)}.chips{display:inline-flex;flex-wrap:wrap;gap:3px;margin-top:4px;max-width:220px}.u{display:inline-block;width:11px;height:11px;border-radius:2px;background:#E5E7EB;border:1px solid #CBD2DC}.u.leased{background:var(--pri);border-color:var(--pri)}.u.notice{background:var(--amber);border-color:var(--amber)}.u.pre{background:var(--green);border-color:var(--green)}.u.v30{background:var(--amber);border-color:var(--amber)}.u.v60{background:var(--red);border-color:var(--red)}
.vac{color:var(--red);font-weight:700}.ok{color:var(--green);font-weight:700}.ren b{font-weight:800}.score{display:inline-block;min-width:26px;text-align:center;border-radius:6px;padding:1px 6px;font-weight:800;font-size:12px;background:#FEE4E2;color:var(--red)}.score.p{background:#D1FADF;color:var(--green)}.score.m{background:#F2F4F7;color:#475467}
.hide{display:none}.empty{color:var(--muted)}.foot{margin-top:40px;font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px}.banner{background:#FFF3D6;border-left:4px solid var(--acc);padding:10px 14px;border-radius:0 10px 10px 0;margin:14px 0;font-size:13.5px}
details{margin-top:8px}details summary{cursor:pointer;font-weight:700;font-size:13px;color:#374151}ul.plain{margin:6px 0 0;padding-left:18px;font-size:13.5px}
.top .wrap{padding-bottom:0;display:flex;justify-content:space-between;align-items:flex-start;gap:24px}.top .wrap>div:first-child{min-width:0}.logo-plate{background:#fff;border-radius:12px;padding:10px 14px;flex:0 0 auto;margin-top:4px}.logo-plate img{height:54px;display:block}
h1,h2,h4,.big{font-family:%(font_display)s}
.pill .pd{display:block;font-size:10.5px;font-weight:500;line-height:1.1;opacity:.75}.pill.none{opacity:.7}
body.owner .detail{display:none}body.owner .five{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}body.owner .f .play{font-size:15px}
@media print{.ctrl{display:none}table.tbl,.f,.card{break-inside:avoid}}
"""

JS = r"""
const rows=[...document.querySelectorAll('tr[data-mgr]')], cards=[...document.querySelectorAll('.f[data-mgr]')]; let mgr='all', q='', bandSel='detractor';
function vis(el){return (mgr==='all'||el.dataset.mgr===mgr)&&(!q||(el.dataset.q||'').includes(q));}
function apply(){rows.forEach(r=>{const b=r.dataset.band; const bandOk=!b||b===bandSel; r.classList.toggle('hide',!(vis(r)&&bandOk));}); cards.forEach(c=>c.classList.toggle('hide',!vis(c)));
 document.querySelectorAll('.cnt').forEach(el=>{const t=el.dataset.t; el.textContent=[...document.querySelectorAll('tr[data-t="'+t+'"]')].filter(r=>!r.classList.contains('hide')).length;});}
document.querySelectorAll('.pill[data-mgr]').forEach(p=>p.addEventListener('click',()=>{document.querySelectorAll('.pill[data-mgr]').forEach(x=>x.classList.remove('on'));p.classList.add('on');mgr=p.dataset.mgr;apply();}));
document.querySelectorAll('.pill[data-band]').forEach(p=>p.addEventListener('click',()=>{document.querySelectorAll('.pill[data-band]').forEach(x=>x.classList.remove('on'));p.classList.add('on');bandSel=p.dataset.band;apply();}));
document.getElementById('q').addEventListener('input',ev=>{q=ev.target.value.trim().toLowerCase();apply();});
document.getElementById('ownerview').addEventListener('click',ev=>{document.body.classList.toggle('owner');ev.target.textContent=document.body.classList.contains('owner')?'Full view':'Owner view';});
document.getElementById('csv').addEventListener('click',()=>{const h=['table','owner','manager','survey','units','vacant_today','next_renewal','play'];const qq=v=>'"'+String(v==null?'':v).replace(/"/g,'""')+'"';
 const lines=[h.join(',')];rows.forEach(r=>{if(r.classList.contains('hide'))return;lines.push([r.dataset.t,r.dataset.name,r.dataset.mgr,r.dataset.survey,r.dataset.units,r.dataset.vac,r.dataset.ren,r.dataset.play].map(qq).join(','));});
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/csv'}));a.download='retention-radar-'+document.body.dataset.asof+'.csv';document.body.appendChild(a);a.click();a.remove();});
apply();
"""

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--config"); ap.add_argument("--benchmarks"); ap.add_argument("--previous"); ap.add_argument("--title", default="Property Owner Retention Radar"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(); O = a.out
    BENCH = load_benchmarks(a.benchmarks) or {}
    bench_ok = available(BENCH)
    company = json.load(open(os.path.join(O, "company.json"))); owners = json.load(open(os.path.join(O, "owners.json"))); inv = json.load(open(os.path.join(O, "inventory.json")))
    dq = open(os.path.join(O, "data-quality.md")).read() if os.path.exists(os.path.join(O, "data-quality.md")) else ""
    cfg = json.load(open(a.config)) if a.config else {}; co = cfg.get("company", {}); brand = cfg.get("brand", {}); thr = cfg.get("risk_tiers", {"call": 50, "watch": 25})
    FLAG_DAYS = int(thr.get("long_vacancy_flag_days", 100))   # a vacancy this old is a situation, not this week's work; config risk_tiers.long_vacancy_flag_days
    prev = json.load(open(a.previous)) if a.previous and os.path.exists(a.previous) else None
    primary = brand.get("primary", "#0B2545"); accent = brand.get("accent", "#4A5568"); short = co.get("short_name", "the company")
    font_body = brand.get("font_body") or "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"; font_display = brand.get("font_display") or font_body
    logo_src = brand.get("logo_data_uri") or brand.get("logo_url") or co.get("logo_url") or ""   # the member's logo on a white plate; an embedded data URI keeps the page offline
    logo_html = f'<div class="logo-plate"><img src="{e(logo_src)}" alt="{e(co.get("name", ""))}"></div>' if logo_src else ""
    as_of = inv.get("as_of", ""); today = dt.date.fromisoformat(as_of[:10]) if as_of else dt.date.today(); missing = [m for m in inv.get("missing", []) if m != "unit_directory"]
    P, R, V, S, C, D, DQ = company.get("portfolio", {}), company.get("renewals", {}), company.get("vacancy", {}), company.get("survey", {}) or {}, company.get("collections", {}), company.get("departures", {}), company.get("delinquency", {})
    certs = (cfg.get("newsletter", {}) or {}).get("certifications_to_feature", []) or []
    # ---------- rows
    live = [o for o in owners if o["tier"] != "Departed" and o["units"] > 0]
    recs = []
    for o in live:
        b = band(o); osc = ops_score(o); pred = b is None and osc >= thr.get("watch", 25)
        vac = vacancy_now(o); ren = next_renewal(o, today); m = (o["managers"] or ["Unassigned"])[0]
        why = "; ".join(SIGNAL_LABEL.get(s.get("key"), s["signal"]) for s in o["signals"] if s.get("type") == "ops" and s["points"] > 0)[:160]
        # Past the flag threshold a vacancy is a situation with a reason behind it (renovation, owner hold, a sale in progress), not this week's work:
        # it stops being the lever for the play, and an owner with nothing else to act on moves to the flags at the bottom of the page.
        long_vac = bool(vac and vac["days"] is not None and vac["days"] >= FLAG_DAYS); vac_act = None if long_vac else vac
        play = the_play(b, vac_act, ren, m) + (f" Long-standing vacancy ({vac['days']:.0f} d at {vac['address']}) is in the flags below; confirm the reason is on file." if long_vac else "")
        pri = priority(b, pred, vac_act, ren); flag = long_vac and b != "detractor" and not ren
        if flag: pri = 7
        recs.append({"o": o, "band": b, "pred": pred, "ops": osc, "vac": vac, "ren": ren, "mgr": m, "why": why, "play": play, "pri": pri, "flag": flag, "long_vac": long_vac,
                     "name": o.get("display_name") or o["name"], "nps": (o.get("survey") or {}).get("nps")})
    def sort_key(r): return (r["pri"], -((r["vac"]["days"] or 0) if r["vac"] else 0), r["ren"]["date"].toordinal() if r["ren"] else 10**9, -(r["ops"]))
    recs.sort(key=sort_key)
    surveyed = [r for r in recs if r["band"]]; predictive = [r for r in recs if r["pred"] and not r["flag"]]
    flags = sorted([r for r in recs if r["flag"]], key=lambda r: -(r["vac"]["days"] or 0))
    five = [r for r in recs if r["pri"] <= 5][:5]
    # ---------- survey + benchmark strip
    bench_nps = f' · verified PMs +{BENCH["nps_all"]}, median PM +{BENCH["nps_median_pm"]}' if bench_ok and BENCH.get("nps_all") is not None else ""
    nps_html = (f'<div class="card nps"><h4>Owner survey</h4><div class="big">{"+" if S["nps"] >= 0 else ""}{S["nps"]:.0f}</div><div class="sub">NPS on {S.get("responses", 0)} responses{bench_nps}</div>'
                f'{svg_stack([(S.get("promoters", 0), GREEN, "promoters"), (S.get("passives", 0), "#D0D5DD", "passives"), (S.get("detractors", 0), RED, "detractors")], 260, 14)}'
                f'<div class="lg"><i style="background:{GREEN}"></i>{S.get("promoters", 0)} promoters <i style="background:#D0D5DD"></i>{S.get("passives", 0)} passives <i style="background:{RED}"></i>{S.get("detractors", 0)} detractors</div>'
                f'<div class="sub" style="margin-top:8px">{len(surveyed)} respondents matched to a live owner; {len(predictive)} non-respondents look like detractors on their data.</div></div>') if S.get("nps") is not None else '<div class="card nps"><h4>Owner survey</h4><div class="empty">No survey responses loaded (connector or survey.json).</div></div>'
    def bench_row(label, mine, median, n=None, unit="%", higher_better=True, nps=False):
        if mine is None: return f'<tr><td class="lab">{e(label)}</td><td class="me" style="color:{GREY}">n/a</td><td>{median}{unit}</td><td></td></tr>'
        gap = mine - median; good = gap >= 0 if higher_better else gap <= 0; col = GREEN if good else RED
        show = (lambda v: f"{v:+.0f}") if nps else (lambda v: f"{v:.1f}" if unit == "%" else f"{v:g}")
        return f'<tr><td class="lab">{e(label)}</td><td class="me" style="color:{col}">{show(mine)}{unit}</td><td>{show(median)}{unit}{f" <span class=n>n={n}</span>" if n else ""}</td><td class="gap" style="color:{col}">{gap:+.1f}{" pts" if unit == "%" or nps else unit}</td></tr>'
    rows_b = []
    if bench_ok:
        rows_b = [bench_row("Lease renewal rate", R.get("rate_pct"), BENCH.get("renewal_median"), BENCH.get("renewal_n")), bench_row("Occupancy, leasable units", P.get("occupancy_pct_leasable"), BENCH.get("occupancy_median"), BENCH.get("occupancy_n")),
                  bench_row("Rent collected, 90 days", C.get("rate_pct"), BENCH.get("rent_collection_median"), BENCH.get("rent_collection_n")), bench_row("Owner NPS", S.get("nps"), BENCH.get("nps_all"), None, unit="", nps=True)]
    for c in certs:
        try:
            mv = float(re.match(r"[\d.]+", str(c["value"])).group()); bv = float(re.match(r"[\d.]+", str(c["benchmark"])).group()); unit = " " + str(c["value"]).split(" ", 1)[1] if " " in str(c["value"]) else ""
            rows_b.append(bench_row(c.get("metric", c.get("name", "")).capitalize(), mv, bv, None, unit=unit, higher_better=False))
        except Exception: pass
    bench_html = (f'<div class="card bench"><h4>Against verified property managers</h4><table class="bt"><tbody>{"".join(rows_b)}</tbody></table><div class="sub" style="margin-top:8px;color:var(--muted);font-size:12px">PropertyManagement.com verified-PM medians as of {BENCH["as_of"]}. Green = {e(short)} is on the right side of the median.</div></div>' if bench_ok else '<div class="card bench"><h4>Against verified property managers</h4><div class="empty">Benchmarks not loaded — call pm_benchmarks_get and pass --benchmarks.</div></div>')
    # ---------- this week's five
    def five_card(r):
        whyline = ("Detractor" + (f", rated {r['nps']:.0f}/10" if isinstance(r["nps"], (int, float)) else "")) if r["band"] == "detractor" else ("Likely detractor: " + (r["why"] or "pattern match")) if r["pred"] else (r["band"] or "").capitalize()
        return f'<div class="f {"pred" if r["pred"] else ""}" data-mgr="{e(r["mgr"])}" data-q="{e((r["name"] + " " + r["mgr"]).lower())}"><div class="nm">{e(r["name"])}</div><div class="why">{e(whyline)}</div><div class="play">{e(r["play"])}</div><div class="mgr">{e(r["mgr"])} · {r["o"]["units"]} unit{"s" if r["o"]["units"] != 1 else ""}</div></div>'
    five_html = "".join(five_card(r) for r in five) or '<div class="card empty">No detractor or likely detractor has a vacancy or a renewal inside 90 days. Run the renewal play on this month\'s renewals anyway.</div>'
    # ---------- tables
    def tr(r, t):
        o = r["o"]; vac = r["vac"]; ren = r["ren"]
        vac_attr = f"{vac['count']} vacant, {fmt_d(vac['days'])}" if vac else ""
        vac_td = (f'<span class="vac">{vac["count"]} vacant · {fmt_d(vac["days"])}</span><div class="sub">{e(vac["address"])}{"" if vac["posted"] else " · not posted" if vac["rent_ready"] else " · not rent-ready"}</div>') if vac else '<span class="ok">All leased</span>'
        ren_td = (f'<span class="ren"><b>{ren["date"].strftime("%b %d").replace(" 0", " ")}</b></span><div class="sub">{e(ren["address"])}{(" · " + e(ren["unit"])) if ren["multi"] else ""} · {e(market_phrase(ren["rvm"]))}</div>') if ren else '<span class="sub">none inside 90 days</span>'
        sc = (f'<span class="score {"p" if r["band"] == "promoter" else "m" if r["band"] == "passive" else ""}">{r["nps"]:.0f}</span>' if isinstance(r["nps"], (int, float)) else f'<span class="score m" title="pattern score">{r["ops"]}</span>')
        why = f'<div class="sub">{e(r["why"])}</div>' if (t == "predictive" and r["why"]) else ""
        return (f'<tr data-t="{t}" data-mgr="{e(r["mgr"])}" data-band="{e(r["band"] or "")}" data-name="{e(r["name"])}" data-survey="{r["nps"] if r["nps"] is not None else ""}" data-units="{o["units"]}" data-vac="{e(vac_attr)}" data-ren="{e(ren["date"].isoformat() + " " + ren["address"] if ren else "")}" data-play="{e(r["play"])}" data-q="{e((r["name"] + " " + r["mgr"] + " " + " ".join(where(pd) for pd in o["properties_detail"])).lower())}">'
                f'<td class="nm"><b>{e(r["name"])}</b><div class="sub">{o["properties"]} propert{"y" if o["properties"] == 1 else "ies"} · {o["units"]} units · {fmt_money(o["rent_month"])}/mo</div><div class="chips">{chips(o["properties_detail"])}</div></td>'
                f'<td>{e(r["mgr"])}</td><td>{sc}{why}</td><td>{vac_td}</td><td>{ren_td}</td><td>{e(r["play"])}</td></tr>')
    t1 = "".join(tr(r, "survey") for r in surveyed); t2 = "".join(tr(r, "predictive") for r in predictive)
    head = '<thead><tr><th>Owner</th><th>Manager</th><th>Score</th><th>Today</th><th>Next renewal (90 d)</th><th>The play</th></tr></thead>'
    counts = collections.Counter(r["band"] for r in surveyed)
    cfg_mgrs = [m.get("first_name") for m in (cfg.get("team", {}) or {}).get("managers", []) if m.get("first_name")]
    doors = collections.Counter(); owners_by_mgr = collections.Counter()
    for o in live:
        seen = set()
        for pd in o["properties_detail"]:
            mg = pd.get("manager") or "Unassigned"; doors[mg] += pd.get("units", 0); seen.add(mg)
        for mg in seen: owners_by_mgr[mg] += 1
    mgr_names = list(dict.fromkeys(cfg_mgrs + [m for m, _ in doors.most_common() if m != "Unassigned"] + (["Unassigned"] if doors.get("Unassigned") else [])))
    mgr_rows = [{"name": m, "doors": doors.get(m, 0), "owners": owners_by_mgr.get(m, 0), "listed": sum(1 for r in recs if r["mgr"] == m and r["pri"] <= 5), "five": sum(1 for r in five if r["mgr"] == m), "flags": sum(1 for r in flags if r["mgr"] == m)} for m in mgr_names]
    def pill(m):   # a manager with no doors still shows: as the ops lead you want to know nobody's properties carry that name in the Site Manager field
        if not m["doors"]: return f'<button class="pill none" data-mgr="{e(m["name"])}" title="No property carries this name in the Site Manager field">{e(m["name"])} <b>0</b><span class="pd">no doors assigned</span></button>'
        return f'<button class="pill" data-mgr="{e(m["name"])}" title="{m["owners"]} owners · {m["doors"]} doors · {m["listed"]} on the list · {m["flags"]} flagged">{e(m["name"])} <b>{m["listed"]}</b><span class="pd">{m["doors"]} door{"s" if m["doors"] != 1 else ""} · {m["owners"]} owner{"s" if m["owners"] != 1 else ""}</span></button>'
    mgr_pills = "".join(pill(m) for m in mgr_rows)
    # ---------- flags: long-standing vacancies, no action this week
    def flag_note(r): return f'{"Likely detractor by pattern, " if r["pred"] else ""}vacant past {FLAG_DAYS} days ({r["vac"]["days"]:.0f} d at {r["vac"]["address"]}). Usually a known situation (renovation, owner hold, a sale in progress). No call this week; confirm the reason is on file and that the listing status is right.'
    def flag_tr(r):
        v = r["vac"]
        return (f'<tr data-t="flag" data-mgr="{e(r["mgr"])}" data-name="{e(r["name"])}"><td class="nm"><b>{e(r["name"])}</b><div class="sub">{r["o"]["properties"]} propert{"y" if r["o"]["properties"] == 1 else "ies"} · {r["o"]["units"]} units</div></td><td>{e(r["mgr"])}</td>'
                f'<td><span class="vac">{v["count"]} vacant · {v["days"]:.0f} d</span><div class="sub">{e(v["address"])}{"" if v["posted"] else " · not posted" if v["rent_ready"] else " · not rent-ready"}</div></td>'
                f'<td>{e(flag_note(r))}</td></tr>')
    flags_html = (f'<section class="detail"><h2>Flags<span class="meta">vacancies of {FLAG_DAYS}+ days, pulled out of the lists above: <span class="cnt" data-t="flag">{len(flags)}</span> owners, no action needed this week</span></h2>'
                  f'<table class="tbl"><thead><tr><th>Owner</th><th>Manager</th><th>Vacancy</th><th>Why it is here</th></tr></thead><tbody>{"".join(flag_tr(r) for r in flags)}</tbody></table></section>') if flags else ""
    # ---------- movers, patterns, data quality
    mv_html = ""
    if prev:
        pmap = {p["owner_id"]: p for p in prev}; cur = {r["o"]["owner_id"]: r for r in recs if r["pri"] <= 5}
        new = [r["name"] for oid, r in cur.items() if oid not in pmap or not pmap[oid].get("listed")]; gone = [p.get("name", "?") for oid, p in pmap.items() if p.get("listed") and oid not in cur]
        mv_html = f'<div class="card detail" style="margin-top:12px"><h4>Since last run</h4><div style="font-size:13.5px"><b>New on the list:</b> {e(", ".join(new) or "none")}<br><b>Off the list:</b> {e(", ".join(gone) or "none")}</div></div>'
    pat = []
    if R.get("rate_pct") is not None and bench_ok: pat.append(f'Renewal rate {R["rate_pct"]:.1f}% on {R.get("cohort", 0)} lease ends against a {BENCH.get("renewal_median")}% median' + (": " + ", ".join(f'{k} {v["rate_pct"]:.0f}%' for k, v in (R.get("by_region") or {}).items() if v.get("rate_pct") is not None) if R.get("by_region") else "") + ". Every renewal inside 90 days is a chance to run this play.")
    if R.get("expiring_120d"): pat.append(f'{R["expiring_120d"]} leases end in the next 120 days' + (f', {R["standing_m2m"]} tenancies are month to month' if R.get("standing_m2m") else "") + ".")
    if V.get("vacant_units") is not None: pat.append(f'{V["vacant_units"]} vacant units, {V.get("rent_ready", 0)} rent-ready, {V.get("posted_to_website", 0)} posted. A rent-ready home that is not posted is the first thing a detractor will mention.')
    if D.get("move_outs"): pat.append(f'{D["owner_initiated"]} of {D["move_outs"]} move-outs since {D.get("window_start", "")} were the owner selling or terminating; {(D.get("reasons") or {}).get("No reason recorded", 0)} carry no reason.')
    if S.get("above_market_maintenance") and bench_ok and BENCH.get("cliff_in_line") is not None: pat.append(f'{S["above_market_maintenance"]} of {S.get("responses", 0)} respondents rate maintenance costs above market. On PropertyManagement.com\'s owner data that one notch takes NPS from {BENCH["cliff_in_line"]} to {BENCH.get("cliff_somewhat_above")}; show the invoice, the bid and the comp before they ask.')
    pat_html = "".join(f"<li>{p}</li>" for p in pat)
    miss_html = "".join(f"<li><b>{e(m.replace('_', ' '))}</b> not uploaded (see appfolio-exports.md).</li>" for m in missing); dq_html = "".join(f"<li>{e(l[2:])}</li>" for l in dq.splitlines() if l.startswith("- "))
    banner = f'<div class="banner"><b>Gaps in this run:</b> {", ".join(m.replace("_", " ") for m in missing)} not uploaded.</div>' if missing else ""
    html_out = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(a.title)} · {e(co.get('name', ''))}</title><style>{CSS.replace('%(primary)s', primary).replace('%(accent)s', accent).replace('%(font_body)s', font_body).replace('%(font_display)s', font_display)}</style></head><body data-asof="{e(as_of)}">
<header class="top"><div class="wrap"><div><div class="eyebrow">Internal · {e(co.get('name', ''))} · data as of {e(as_of)}</div><h1>{e(a.title)}</h1><p>The renewal play: find the owners who are unhappy or about to be, pair each with what is happening on their property, and reach them with a win in hand. This page surfaces the work; your team does it in its normal tools. Survey answers stay inside the company.</p></div>{logo_html}</div></header>
<div class="ctrl"><div class="wrap"><button class="pill on" data-mgr="all">All managers</button>{mgr_pills}<span style="width:8px"></span><input id="q" type="search" placeholder="Search owner, address, manager"><span class="sp"></span><button class="btn" id="ownerview">Owner view</button><button class="btn p" id="csv">Export list</button></div></div>
<main class="wrap"><div class="strip">{nps_html}{bench_html}</div>{banner}
<h2>This week's five<span class="meta">detractors with a vacancy today first, then detractors with a renewal inside 90 days, then likely detractors with the same; nothing on this list is a courtesy call</span></h2><div class="five">{five_html}</div>
<section class="detail"><h2>Survey respondents<span class="meta">{counts.get("detractor", 0)} detractors · {counts.get("passive", 0)} passives · {counts.get("promoter", 0)} promoters</span></h2>
<div style="margin:0 0 10px;display:flex;gap:8px"><button class="pill on" data-band="detractor">Detractors <b>{counts.get("detractor", 0)}</b></button><button class="pill" data-band="passive">Passives <b>{counts.get("passive", 0)}</b></button><button class="pill" data-band="promoter">Promoters <b>{counts.get("promoter", 0)}</b></button></div>
{f'<table class="tbl">{head}<tbody>{t1}</tbody></table>' if t1 else '<p class="empty">No survey respondent matched a live owner.</p>'}</section>
<section class="detail"><h2>Likely detractors<span class="meta">no survey answer, but the data looks like the detractors': <span class="cnt" data-t="predictive">{len(predictive)}</span> owners, pattern score {thr.get("watch", 25)}+</span></h2>
{f'<table class="tbl">{head}<tbody>{t2}</tbody></table>' if t2 else '<p class="empty">Nobody without a survey answer crosses the pattern threshold.</p>'}
<p class="sub" style="margin-top:8px">Pattern-based for now (owner-initiated move-outs, long vacancies, payments on hold, failed tenancies, cost signals). It gets calibrated against each new survey cycle.</p></section>
{flags_html}
{mv_html}
<section class="detail"><h2>Patterns</h2><div class="card"><ul class="plain">{pat_html}</ul></div>
<details><summary>Data quality and gaps</summary><ul class="plain">{miss_html}{dq_html}</ul></details></section>
<div class="foot">Built from AppFolio exports ({", ".join(sorted(inv.get("found", {}).keys()))}) and PropertyManagement.com owner survey responses. Benchmarks: {"PropertyManagement.com verified-PM data as of " + BENCH["as_of"] if bench_ok else "not loaded"}. Chips: filled = leased, grey = between tenants, amber = vacant 30+ days, red = 60+, green = pre-leased.</div></main>
<script>{JS}</script></body></html>"""
    open(os.path.join(O, "radar-dashboard.html"), "w").write(html_out)
    with open(os.path.join(O, "call-list.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["table", "priority", "owner", "manager", "survey_score", "pattern_score", "properties", "units", "vacant_today", "next_renewal", "play", "email"])
        for r in recs:
            if r["pri"] > 5 and not r["flag"]: continue
            w.writerow(["flag" if r["flag"] else "survey" if r["band"] else "predictive", r["pri"], r["name"], r["mgr"], r["nps"] if r["nps"] is not None else "", r["ops"], r["o"]["properties"], r["o"]["units"], f'{r["vac"]["count"]} vacant, {fmt_d(r["vac"]["days"])} at {r["vac"]["address"]}' if r["vac"] else "", f'{r["ren"]["date"].isoformat()} {r["ren"]["address"]}' if r["ren"] else "", flag_note(r) if r["flag"] else r["play"], (r["o"]["emails"] or [""])[0]])
    json.dump([{"owner_id": r["o"]["owner_id"], "name": r["name"], "listed": r["pri"] <= 5, "priority": r["pri"], "band": r["band"], "pattern_score": r["ops"], "as_of": as_of} for r in recs], open(os.path.join(O, "radar-run.json"), "w"), indent=1)
    summary = {"as_of": as_of, "five": [{"owner": r["name"], "manager": r["mgr"], "why": ("detractor" if r["band"] == "detractor" else "likely detractor"), "play": r["play"]} for r in five],
               "survey": {"detractors": counts.get("detractor", 0), "passives": counts.get("passive", 0), "promoters": counts.get("promoter", 0), "nps": S.get("nps"), "responses": S.get("responses")},
               "predictive": len(predictive), "flags": len(flags), "flag_days": FLAG_DAYS, "managers": mgr_rows, "five_per_manager": dict(collections.Counter(r["mgr"] for r in five)), "listed": sum(1 for r in recs if r["pri"] <= 5), "per_manager": dict(collections.Counter(r["mgr"] for r in recs if r["pri"] <= 5)), "html": os.path.join(O, "radar-dashboard.html"), "csv": os.path.join(O, "call-list.csv")}
    json.dump(summary, open(os.path.join(O, "radar-summary.json"), "w"), indent=1)
    if a.json: print(json.dumps(summary, indent=1))
    else: print(f"Radar built: this week's {len(five)} ({', '.join(f'{m} {n}' for m, n in summary['five_per_manager'].items())}); on the list {summary['listed']} ({counts.get('detractor', 0)} survey detractors, {len(predictive)} likely detractors); {len(flags)} flagged for long vacancies. Open {summary['html']}")

if __name__ == "__main__": main()
