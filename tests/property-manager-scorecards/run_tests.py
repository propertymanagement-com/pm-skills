#!/usr/bin/env python3
"""Tests for the property-manager-scorecards skill, on fictional data only (Pied Piper Properties, Denver).

Builds a made-up company: properties, property owners, survey responses (some in the connector's own JSON shape,
some as compact rows), a simple CSV roster and an AppFolio-style Property Directory .xlsx. Knows each response's
true manager, runs scripts/build_scorecards.py on both rosters and checks:
  - no response is credited to the wrong manager, and nearly all are matched;
  - company and manager numbers equal an independent computation from the raw answers;
  - the focus rules, the thin-roster stop and the by-exclusion setting behave.
Writes the built pages to out/ (gitignored). Run: python3 run_tests.py
"""
import csv
import json
import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "..", "skills", "property-manager-scorecards")
SCRIPT = os.path.join(SKILL, "scripts", "build_scorecards.py")
OUT = os.path.join(HERE, "out")

OPTIONS = {
    "overall": ["Very satisfied", "Somewhat satisfied", "Neither satisfied nor dissatisfied", "Somewhat dissatisfied", "Very dissatisfied"],
    "leasing": ["Very satisfied", "Somewhat satisfied", "Neither satisfied nor dissatisfied", "Somewhat dissatisfied", "Very dissatisfied"],
    "vacancy": ["0-14 days", "15-30 days", "31-60 days", "61+ days", "Not applicable - no recent vacancy"],
    "speed": ["Under 24 hours", "1-2 days", "3-5 days", "6-7 days", "7+ days", "Not applicable"],
    "cost": ["Significantly below market (excellent value)", "Somewhat below market (good value)", "In line with market (fair value)",
             "Somewhat above market (poor value)", "Significantly above market (very poor value)", "Not applicable"],
    "statements": ["Very easy to understand", "Mostly easy to understand", "Somewhat confusing", "Often confusing", "Very confusing"],
}
VALUES = {
    "overall": [10, 7, 5, 3, 0], "leasing": [10, 7, 5, 3, 0], "vacancy": [10, 8, 5, 2, None], "speed": [10, 8, 5, 3, 0, None],
    "cost": [10, 8, 6, 3, 0, None], "statements": [8, 6, 4, 2, 0],
}
TITLES = {"overall": "Overall Satisfaction", "leasing": "Leasing Performance", "vacancy": "Vacancy Time", "speed": "Maintenance Communication",
          "cost": "Maintenance Cost Value", "statements": "Accounting & Financial Reporting"}
TOP = {"overall": 10, "leasing": 10, "vacancy": 10, "speed": 10, "cost": 10, "statements": 8}
QMAP = {"overall": "Overall satisfaction", "leasing": "Tenant placement", "vacancy": "Vacancy time", "speed": "Maintenance response speed",
        "cost": "Maintenance cost value", "statements": "Financial statements"}
STREETS = ["Tennyson St", "Pearl St", "Lowell Blvd", "Federal Blvd", "Colfax Ave", "York St", "Downing St", "Logan St",
           "Grant St", "Sheridan Blvd", "Yates St", "Zenobia St", "Clay St", "Bryant St", "Decatur St", "Wolff St"]
FIRST = ["Priya", "Avery", "Jordan", "Morgan", "Casey", "Riley", "Quinn", "Rowan", "Harper", "Emerson", "Reese", "Logan",
         "Parker", "Sage", "Skyler", "Dakota", "Hayden", "Kendall", "Marlowe", "Sloane", "Tatum", "Wren", "Blair", "Ellis"]
LAST = ["Shah", "Collins", "Brennan", "Whitaker", "Alvarez", "Nakamura", "Okafor", "Lindqvist", "Moreau", "Castillo",
        "Fitzgerald", "Haddad", "Ivanova", "Kowalski", "Delacroix", "Mbeki", "Sorensen", "Takahashi", "Valdez", "Yilmaz"]
MANAGERS = ["Hannah", "Luis", "Grace", "Theo", "Owen"]
# per manager: share of promoters / detractors, phone pickup chance, detractor voicemail chance, answer offsets
PROFILE = {
    "Hannah": (0.86, 0.00, 0.82, 0.0, {"overall": .4, "leasing": .5, "speed": .3}),
    "Luis": (0.75, 0.08, 0.78, 0.0, {"cost": 1.2, "vacancy": -.3}),
    "Grace": (0.67, 0.11, 0.71, 0.0, {"statements": -1.4}),
    "Theo": (0.70, 0.12, 0.62, 0.0, {"vacancy": 1.0, "speed": -.6}),
    "Owen": (0.47, 0.20, 0.33, 1.0, {"vacancy": -2.4, "leasing": -.7, "overall": -.6, "speed": 1.8}),
}


def build_company(seed=11):
    rng = random.Random(seed)
    props, owners, truth_owner_mgr = [], [], {}
    n = 0
    for oi in range(95):
        mgr = MANAGERS[oi % 5]
        first, last = rng.choice(FIRST), rng.choice(LAST)
        couple = rng.random() < 0.2
        entity = rng.random() < 0.12
        name = (f"{last} Holdings LLC" if entity else f"{first} and {rng.choice(FIRST)} {last}" if couple else f"{first} {last}")
        email = f"{first.lower()}.{last.lower()}{oi}@example.com"
        k = 1 if rng.random() < 0.7 else rng.choice([2, 3])
        pids = []
        for j in range(k):
            n += 1
            unit = f" Unit {rng.randint(1, 9)}" if rng.random() < 0.2 else ""
            p = {"id": f"prop-{n:04d}", "address_line1": f"{100 + n * 7} {rng.choice(STREETS)}{unit}", "city": "Denver",
                 "postal_code": rng.choice(["80202", "80205", "80211", "80212", "80219"]), "source_id": str(5000 + n),
                 "name": f"PP-{n:03d}", "mgr": mgr}
            # one in fifteen multi-property owners has one property with another manager
            if k > 1 and j == k - 1 and rng.random() < 0.15:
                p["mgr"] = MANAGERS[(MANAGERS.index(mgr) + 1) % 5]
            props.append(p)
            pids.append(p["id"])
        owners.append({"id": f"owner-{oi:03d}", "display_name": name, "email": email, "pids": pids, "mgr": mgr})
        truth_owner_mgr[f"owner-{oi:03d}"] = mgr
    return rng, props, owners


def answers_for(rng, kind, mgr):
    prof = PROFILE[mgr]
    base = {"p": 9.2, "pa": 7.4, "d": 4.6}[kind]
    out = {}
    for key, labels in OPTIONS.items():
        if key in ("vacancy", "speed", "cost") and rng.random() < 0.12:
            out[key] = labels[-1]
            continue
        target = (base + prof[4].get(key, 0) + rng.uniform(-1.2, 1.2)) * TOP[key] / 10 - (2.0 if key == "cost" else 0)
        vals = [v for v in VALUES[key] if v is not None]
        best = min(range(len(vals)), key=lambda i: abs(vals[i] - target))
        out[key] = labels[best]
    return out


def make_responses(rng, props, owners):
    by_id = {p["id"]: p for p in props}
    resps, truth = [], {}
    rid = 0
    for o in owners:
        if rng.random() > 0.62:
            continue
        mgr = o["mgr"]
        prof = PROFILE[mgr]
        x = rng.random()
        kind = "p" if x < prof[0] else ("d" if x < prof[0] + prof[1] else "pa")
        nps = {"p": rng.choice([9, 10, 10]), "pa": rng.choice([7, 8]), "d": rng.choice([2, 5, 6])}[kind]
        call = None
        if rng.random() < 0.8:
            if kind == "d":
                call = "Voicemail" if rng.random() < prof[3] else "Picked up"
            else:
                call = "Picked up" if rng.random() < prof[2] else "Voicemail"
        rid += 1
        link = rng.random()
        single = len(o["pids"]) == 1
        r = {"id": f"resp-{rid:03d}", "user_email": o["email"] if link > 0.08 else f"someone{rid}@mailinator.example",
             "user_name": o["display_name"], "pm_owner_id": o["id"] if link > 0.15 else None,
             "pm_property_id": o["pids"][0] if (single and link > 0.15) else None,
             "calculated_score": None, "completed_at": f"2026-{rng.randint(4, 10):02d}-{rng.randint(1, 28):02d}T15:00:00Z",
             "nps": nps, "call": call, "ans": answers_for(rng, kind, mgr)}
        # truth: majority manager of the owner's properties
        mg = [by_id[p]["mgr"] for p in o["pids"]]
        counts = {m: mg.count(m) for m in set(mg)}
        top = sorted(counts.items(), key=lambda kv: -kv[1])
        truth[r["id"]] = None if len(top) > 1 and top[0][1] == top[1][1] else top[0][0]
        pts = 23.47 * nps / 10 + (9.39 * (call == "Picked up") if call else 0)
        wsum = 23.47 + (9.39 if call else 0)
        for key, lab in r["ans"].items():
            v = VALUES[key][OPTIONS[key].index(lab)]
            if v is not None:
                pts += 14.08 * v / TOP[key]
                wsum += 14.08
        r["calculated_score"] = min(100.0, round(100 * pts / wsum, 1))
        resps.append(r)
    return resps, truth


def to_raw(r):
    answers = [{"question_title": "Net Promoter Score", "display_value": str(r["nps"]), "numeric_value": r["nps"], "selected_option_label": None}]
    if r["call"]:
        answers.append({"question_title": "Call Response", "display_value": r["call"], "numeric_value": 10 if r["call"] == "Picked up" else 0,
                        "selected_option_label": r["call"]})
    for key, lab in r["ans"].items():
        v = VALUES[key][OPTIONS[key].index(lab)]
        answers.append({"question_title": TITLES[key], "display_value": lab, "numeric_value": 0 if v is None else v, "selected_option_label": lab})
    return {k: r[k] for k in ("id", "user_email", "user_name", "pm_owner_id", "pm_property_id", "calculated_score", "completed_at")} | {
        "counts_toward_ratings": True, "answers": answers}


def to_compact(r):
    c = {"id": r["id"], "owner": r["pm_owner_id"], "property": r["pm_property_id"], "email": r["user_email"], "name": r["user_name"],
         "score": r["calculated_score"], "date": r["completed_at"][:10], "nps": r["nps"], "call": r["call"]}
    c.update(r["ans"])
    return c


def vary(addr, rng):
    a = addr
    x = rng.random()
    if x < 0.25:
        a = a.replace(" St", " Street").replace(" Ave", " Avenue").replace(" Blvd", " Boulevard")
    elif x < 0.45:
        a = a.upper()
    if " Unit " in a and rng.random() < 0.5:
        a = a.replace(" Unit ", " #")
    return a


def write_work(dirpath, resps, owners, props, raw_share=0.5, seed=3):
    rng = random.Random(seed)
    os.makedirs(dirpath, exist_ok=True)
    raw = [to_raw(r) for r in resps if rng.random() < raw_share]
    raw_ids = {r["id"] for r in raw}
    compact = [to_compact(r) for r in resps if r["id"] not in raw_ids]
    json.dump({"pmid": 1, "limit": 25, "offset": 0, "total_count": len(resps), "count": len(raw), "responses": raw},
              open(os.path.join(dirpath, "responses-1.json"), "w"))
    json.dump(compact, open(os.path.join(dirpath, "responses-2.json"), "w"))
    linked_owner_ids = {r["pm_owner_id"] for r in resps if r["pm_owner_id"]}
    json.dump({"owners": [{"id": o["id"], "display_name": o["display_name"], "email": o["email"],
                           "property_links": [{"pm_property_id": p} for p in o["pids"]]} for o in owners if o["id"] in linked_owner_ids]},
              open(os.path.join(dirpath, "owners.json"), "w"))
    linked_pids = {p for o in owners if o["id"] in linked_owner_ids for p in o["pids"]} | {r["pm_property_id"] for r in resps if r["pm_property_id"]}
    json.dump([{"id": p["id"], "address": p["address_line1"], "city": p["city"], "zip": p["postal_code"], "name": p["name"],
                "source_id": p["source_id"]} for p in props if p["id"] in linked_pids],
              open(os.path.join(dirpath, "properties.json"), "w"))


def write_csv_roster(path, props, owners, drop=()):
    rng = random.Random(5)
    by_pid = {pid: o for o in owners for pid in o["pids"]}
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Property address", "City", "ZIP", "Property owner name", "Property owner email", "Property manager"])
        for p in props:
            if p["id"] in drop:
                continue
            o = by_pid[p["id"]]
            w.writerow([vary(p["address_line1"], rng), p["city"], p["postal_code"], o["display_name"],
                        o["email"] if rng.random() < 0.5 else "", p["mgr"]])


def write_appfolio_xlsx(path, props, owners):
    import openpyxl
    by_pid = {pid: o for o in owners for pid in o["pids"]}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Property Directory"])
    ws.append(["Exported On: 11/18/2026"])
    ws.append([])
    ws.append(["Property", "Property ID", "Property Address", "Property City", "Property State", "Property Zip", "Owners", "Site Manager Name", "Units"])
    surname = {"Hannah": "Okoro", "Luis": "Pereira", "Grace": "Lindgren", "Theo": "Marsh", "Owen": "Calloway"}
    for p in props:
        o = by_pid[p["id"]]
        ws.append([f"{p['name']} - {p['address_line1']}", p["source_id"], p["address_line1"], p["city"], "CO", p["postal_code"],
                   o["display_name"], f"{surname[p['mgr']]}, {p['mgr']}", 1])
    ws.append(["Total", "", "", "", "", "", "", "", len(props)])
    wb.save(path)


def run(args):
    r = subprocess.run([sys.executable, "-I", SCRIPT] + args, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def independent(resps, ids=None):
    """Company-style numbers straight from the raw answers, written separately from the skill's code."""
    from decimal import Decimal, ROUND_HALF_UP
    rd = lambda x, d: float(Decimal(str(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))
    rs = [r for r in resps if ids is None or r["id"] in ids]
    prom = sum(r["nps"] >= 9 for r in rs)
    det = sum(r["nps"] <= 6 for r in rs)
    calls = [r for r in rs if r["call"]]
    out = {"n": len(rs), "nps": int(rd(100 * (prom - det) / len(rs), 0)),
           "pickup": rd(100 * sum(r["call"] == "Picked up" for r in calls) / len(calls), 0) if calls else None,
           "sat": rd(sum(r["calculated_score"] for r in rs) / len(rs), 1), "q": {}}
    for key in OPTIONS:
        vals = [VALUES[key][OPTIONS[key].index(r["ans"][key])] for r in rs]
        vals = [v * 10 / TOP[key] for v in vals if v is not None]
        out["q"][QMAP[key]] = rd(sum(vals) / len(vals), 1) if vals else None
    return out


def load_page_data(page):
    html = open(page, encoding="utf-8").read()
    start = html.index("const D = ") + len("const D = ")
    end = html.index(";\n(function", start)
    return json.loads(html[start:end].replace("<\\/", "</"))


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    rng, props, owners = build_company()
    resps, truth = make_responses(rng, props, owners)
    work = os.path.join(OUT, "work")
    write_work(work, resps, owners, props)
    fails = []
    check = lambda ok, msg: None if ok else fails.append(msg)

    for label, roster_path, writer in [("csv", os.path.join(OUT, "team-roster.csv"), write_csv_roster),
                                       ("appfolio", os.path.join(OUT, "Property Directory.xlsx"), write_appfolio_xlsx)]:
        writer(roster_path, props, owners)
        page = os.path.join(OUT, label, "property-manager-scorecards.html")
        os.makedirs(os.path.dirname(page), exist_ok=True)
        code, line, err = run(["--work", work, "--company", "Pied Piper Properties, LLC", "--roster", roster_path,
                               "--expected", str(len(resps)), "--pulled", "2026-11-18", "--out", page])
        check(code == 0, f"[{label}] build failed: {line} {err}")
        if code:
            continue
        D = load_page_data(page)
        report = open(os.path.join(os.path.dirname(page), "match-report.md")).read()
        # matching accuracy: rebuild assignments from the per-manager counts is not enough, so re-run the matcher directly
        sys.path.insert(0, os.path.join(SKILL, "scripts"))
        import importlib
        bs = importlib.import_module("build_scorecards")
        roster, _ = bs.read_roster(roster_path)
        P = {p["id"]: p for p in map(bs.parse_property, json.load(open(os.path.join(work, "properties.json"))))}
        O = {o["id"]: o for o in map(bs.parse_owner, json.load(open(os.path.join(work, "owners.json")))["owners"])}
        idx = bs.Index(roster, P)
        rows = json.load(open(os.path.join(work, "responses-1.json")))["responses"] + json.load(open(os.path.join(work, "responses-2.json")))
        wrong, matched, eligible = 0, 0, 0
        for raw in rows:
            r = bs.parse_response(raw)
            m, how, why = bs.match(r, O, P, idx)
            t = truth[r["id"]]
            if label == "appfolio" and m:
                m = m.split()[0]  # "Hannah Okoro" -> "Hannah"
            if t:
                eligible += 1
            if m:
                matched += 1
                if m != t:
                    wrong += 1
        check(wrong == 0, f"[{label}] {wrong} responses credited to the wrong manager")
        check(matched >= 0.85 * eligible, f"[{label}] matched only {matched} of {eligible} matchable responses")
        # numbers: company vs independent
        ind = independent(resps)
        C = D["company"]
        check(C["n"] == ind["n"] and C["nps"] == ind["nps"], f"[{label}] company n/NPS {C['n']}/{C['nps']} vs {ind['n']}/{ind['nps']}")
        check(bs.rnd(C["pickup"]) == ind["pickup"], f"[{label}] company pickup {C['pickup']} vs {ind['pickup']}")
        check(abs(C["sat"] - ind["sat"]) < 1e-9, f"[{label}] company sat {C['sat']} vs {ind['sat']}")
        for q, v in ind["q"].items():
            check(C["q"][q]["v"] == v, f"[{label}] company {q} {C['q'][q]['v']} vs {v}")
        # each manager vs independent on the responses the skill credited to them (truth-based ids)
        for mgr in D["managers"]:
            short = mgr["name"].split()[0]
            ids = {rid for rid, t in truth.items() if t == short}
            ind_m = independent(resps, ids)
            if mgr["n"] == ind_m["n"]:
                check(mgr["nps"] == ind_m["nps"], f"[{label}] {short} NPS {mgr['nps']} vs {ind_m['nps']}")
                for q, v in ind_m["q"].items():
                    check(mgr["q"][q]["v"] == v, f"[{label}] {short} {q} {mgr['q'][q]['v']} vs {v}")
                    if v is not None and C["q"][q]["v"] is not None:
                        check(abs(mgr["q"][q]["gap"] - round(v - C["q"][q]["v"], 1)) < 1e-9, f"[{label}] {short} {q} gap")
        owen = next(m for m in D["managers"] if m["name"].startswith("Owen"))
        check(owen["focus"].startswith("Answer the phone."), f"[{label}] Owen focus: {owen['focus']}")
        check(D["footer"].startswith("Live from the PropertyManagement.com MCP, pulled Nov 18, 2026 · "), f"[{label}] footer {D['footer']}")
        check(D["company_name"] == "Pied Piper Properties", f"[{label}] company name {D['company_name']}")
        print(f"[{label}] {line}  | matched {matched}/{len(rows)}, wrong 0={wrong == 0}")

    # thin roster: drop most properties, expect exit 2 and no page
    thin = os.path.join(OUT, "thin-roster.csv")
    write_csv_roster(thin, props, owners, drop={p["id"] for p in props[: int(len(props) * 0.8)]})
    code, line, _ = run(["--work", work, "--company", "Pied Piper Properties", "--roster", thin, "--out", os.path.join(OUT, "thin", "x.html")])
    check(code == 2 and "roster_thin" in line, f"thin roster: expected exit 2, got {code} {line}")
    code, line, _ = run(["--work", work, "--company", "Pied Piper Properties", "--roster", thin, "--allow-thin", "--out", os.path.join(OUT, "thin", "x.html")])
    check(code == 0 and "Only" in (load_page_data(os.path.join(OUT, "thin", "x.html"))["warning"] or ""), f"thin roster --allow-thin: {code} {line}")
    # by exclusion
    code, line, _ = run(["--work", work, "--company", "Pied Piper Properties", "--roster", thin, "--unmatched-to", "Owen", "--out", os.path.join(OUT, "excl", "x.html")])
    De = load_page_data(os.path.join(OUT, "excl", "x.html")) if code == 0 else {}
    check(code == 0 and De.get("unassigned") is None and "by exclusion" in De.get("footer", ""), f"by exclusion: {code} {line}")
    # missing pages
    code, line, _ = run(["--work", work, "--company", "Pied Piper Properties", "--roster", os.path.join(OUT, "team-roster.csv"),
                         "--expected", str(len(resps) + 20), "--out", os.path.join(OUT, "short", "x.html")])
    check(code == 3, f"data short: expected exit 3, got {code} {line}")

    # building rule: a unit missing from the roster never takes another unit's manager
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import importlib
    bs = importlib.import_module("build_scorecards")
    roster = [{"address": "900 Grant St #1", "zip": "80203", "manager": "Hannah"},
              {"address": "910 Grant St", "zip": "80203", "manager": "Luis"},
              {"address": "920 Grant St Unit 1", "zip": "80203", "manager": "Theo"},
              {"address": "920 Grant St Unit 2", "zip": "80203", "manager": "Theo"}]
    idx = bs.Index(roster, {})
    pm = lambda addr: idx.property_manager({"address": addr, "zip": "80203", "city": "Denver"})[0]
    check(pm("900 Grant Street Apt 1") == "Hannah", "unit listed on the roster should match")
    check(pm("900 Grant St #2") is None, "a unit missing from the roster must not take another unit's manager")
    check(pm("910 Grant St #7") == "Luis", "a unit should match the roster's whole-building row")
    check(pm("920 Grant St") == "Theo", "a whole building should match when every listed unit has one manager")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print(f"PASS: {len(resps)} responses, {len(props)} properties, {len(owners)} property owners, both rosters, 4 edge cases")


if __name__ == "__main__":
    main()
