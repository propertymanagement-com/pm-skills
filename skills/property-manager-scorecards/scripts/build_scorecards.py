#!/usr/bin/env python3
"""Property Manager Scorecards: match each survey response to a property manager, score every manager
against the company, and build the page from the bundled template.

usage:
  python3 build_scorecards.py --work WORKDIR --company "Company name" [--roster ROSTER]
         [--unmatched-to NAME] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--expected N]
         [--allow-thin] [--out property-manager-scorecards.html]

WORKDIR holds the connector pulls: responses*.json, owners*.json, properties*.json
(compact rows or the tools' own JSON; see references/data-files.md).
ROSTER is the member's team roster (.csv, .tsv, .xlsx; see references/roster.md). It can be left out
only when the property records carry a manager field.

Prints one status line. Writes the page, match-report.md and scorecards-summary.json.
Exit codes: 0 built, 2 roster too thin (under half matched; rerun with --allow-thin to build anyway),
3 data short (fewer responses than --expected), 4 roster unreadable, 5 no responses.
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(os.path.dirname(HERE), "assets", "scorecards-template.html")
VERSION = "1.0.0"

# ---------------------------------------------------------------------------------------------
# The survey (one PropertyManagement.com survey, v1.0, for every company; references/survey-questions.md)
QUESTIONS = ["Overall satisfaction", "Tenant placement", "Vacancy time",
             "Maintenance response speed", "Maintenance cost value", "Financial statements"]
TOP = {q: 10 for q in QUESTIONS}
TOP["Financial statements"] = 8
TITLES = {
    "net promoter score": "nps", "call response": "call",
    "overall satisfaction": "Overall satisfaction", "leasing performance": "Tenant placement",
    "vacancy time": "Vacancy time", "maintenance communication": "Maintenance response speed",
    "maintenance cost value": "Maintenance cost value",
    "accounting & financial reporting": "Financial statements", "accounting and financial reporting": "Financial statements",
}
COMPACT = {
    "nps": "nps", "call": "call", "call_response": "call", "phone": "call",
    "overall": "Overall satisfaction", "leasing": "Tenant placement", "tenant_placement": "Tenant placement",
    "vacancy": "Vacancy time", "speed": "Maintenance response speed", "maintenance_speed": "Maintenance response speed",
    "maintenance_comms": "Maintenance response speed", "cost": "Maintenance cost value",
    "maintenance_cost": "Maintenance cost value", "statements": "Financial statements", "accounting": "Financial statements",
}
SATISFIED = {"very satisfied": 10, "somewhat satisfied": 7, "neither satisfied nor dissatisfied": 5,
             "somewhat dissatisfied": 3, "very dissatisfied": 0}
LABELS = {
    "Overall satisfaction": SATISFIED,
    "Tenant placement": SATISFIED,
    "Vacancy time": {"0-14 days": 10, "15-30 days": 8, "31-60 days": 5, "61+ days": 2},
    "Maintenance response speed": {"under 24 hours": 10, "1-2 days": 8, "3-5 days": 5, "6-7 days": 3, "7+ days": 0},
    "Maintenance cost value": {"significantly below market": 10, "somewhat below market": 8, "in line with market": 6,
                               "somewhat above market": 3, "significantly above market": 0},
    "Financial statements": {"very easy to understand": 8, "mostly easy to understand": 6, "somewhat confusing": 4,
                             "often confusing": 2, "very confusing": 0},
}
FIXES = {
    "Overall satisfaction": "Call every passive and detractor property owner before the next statement goes out.",
    "Tenant placement": "Walk property owners through the screening behind every new placement.",
    "Vacancy time": "Shorten vacancies. Price to market on day one and start the turn the day notice comes in.",
    "Maintenance response speed": "Get back to property owners on every maintenance request within 24 hours, even when the fix takes longer.",
    "Maintenance cost value": "Show property owners how each repair bill compares to market before they ask.",
    "Financial statements": "Walk property owners through their monthly statement on a 10-minute call.",
}
NA = "NA"


def rnd(x, d=0):
    """Round half away from zero (what people expect: 26.5 -> 27), returned as float or int."""
    q = Decimal(1).scaleb(-d)
    v = Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP)
    return int(v) if d == 0 else float(v)


def sub(a, b):
    return float(Decimal(str(a)) - Decimal(str(b)))


def norm_label(s):
    s = str(s).strip().lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"\s*\(.*\)$", "", s)  # "in line with market (fair value)" -> "in line with market"


class Unknown(Counter):
    pass


UNKNOWN = Unknown()


def answer_value(q, label=None, numeric=None):
    """Value on the question's own scale, NA for "Not applicable", None for blank or unknown."""
    if label not in (None, ""):
        nl = norm_label(label)
        if nl.startswith("not applicable") or nl in ("n/a", "na"):
            return NA
    if isinstance(numeric, (int, float)) and not isinstance(numeric, bool):
        return float(numeric)
    if label in (None, ""):
        return None
    if isinstance(label, (int, float)):
        return float(label)
    nl = norm_label(label)
    if re.fullmatch(r"-?\d+(\.\d+)?", nl):
        return float(nl)
    table = LABELS[q]
    if nl in table:
        return float(table[nl])
    UNKNOWN[f"{q}: {label}"] += 1
    return None


def nps_value(label=None, numeric=None):
    for v in (numeric, label):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
        if isinstance(v, str) and re.fullmatch(r"\s*\d{1,2}\s*", v):
            return int(v)
    return None


def call_value(label=None, numeric=None):
    if label not in (None, ""):
        nl = norm_label(label)
        if "voice" in nl:
            return "voicemail"
        if "pick" in nl or "answer" in nl:
            return "picked"
        if nl in ("10", "0"):
            return "picked" if nl == "10" else "voicemail"
    if isinstance(numeric, (int, float)) and not isinstance(numeric, bool):
        return "picked" if numeric >= 5 else "voicemail"
    return None


# ---------------------------------------------------------------------------------------------
# Loading the connector pulls

def load_rows(workdir, prefix, keys):
    rows = []
    for path in sorted(glob.glob(os.path.join(workdir, prefix + "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in keys:
                if isinstance(data.get(k), list):
                    data = data[k]
                    break
            else:
                data = [data]
        rows.extend(r for r in data if isinstance(r, dict))
    return rows


def split_emails(v):
    if not v:
        return set()
    if isinstance(v, list):
        v = ",".join(str(x) for x in v)
    return {e.strip().lower() for e in re.split(r"[,;\s]+", str(v)) if "@" in e}


def parse_response(r):
    g = lambda *ks: next((r[k] for k in ks if k in r and r[k] not in (None, "")), None)
    out = {
        "id": g("id", "response_id"),
        "owner": g("pm_owner_id", "owner", "owner_id"),
        "property": g("pm_property_id", "property", "property_id"),
        "emails": split_emails(g("user_email", "email")),
        "name": g("user_name", "name") or "",
        "score": g("calculated_score", "score"),
        "date": str(g("completed_at", "date") or "")[:10],
        "counts": r.get("counts_toward_ratings", True) is not False,
        "nps": None, "call": None, "q": {q: None for q in QUESTIONS},
    }
    if isinstance(r.get("answers"), list):
        for a in r["answers"]:
            key = TITLES.get(str(a.get("question_title", "")).strip().lower())
            if not key:
                continue
            label = a.get("selected_option_label") or a.get("display_value")
            num = a.get("numeric_value")
            if key == "nps":
                out["nps"] = nps_value(a.get("display_value"), num)
            elif key == "call":
                out["call"] = call_value(label, num)
            else:
                out["q"][key] = answer_value(key, label, num)
    else:
        for ck, key in COMPACT.items():
            if ck not in r:
                continue
            v = r[ck]
            if key == "nps":
                out["nps"] = nps_value(v if isinstance(v, str) else None, v if not isinstance(v, str) else None)
            elif key == "call":
                out["call"] = call_value(v if isinstance(v, str) else None, v if not isinstance(v, str) else None)
            else:
                out["q"][key] = answer_value(key, v if isinstance(v, str) else None, v if not isinstance(v, str) else None)
    try:
        out["score"] = float(out["score"]) if out["score"] is not None else None
    except (TypeError, ValueError):
        out["score"] = None
    return out


def parse_owner(o):
    links = o.get("property_links") or []
    pids = [l.get("pm_property_id") for l in links if isinstance(l, dict) and l.get("pm_property_id")]
    pids += [p for p in (o.get("properties") or []) if isinstance(p, str)]
    name = o.get("display_name") or o.get("name") or " ".join(x for x in (o.get("first_name"), o.get("last_name")) if x) or o.get("company_name") or ""
    return {"id": o.get("id"), "name": name, "emails": split_emails(o.get("email") or o.get("emails")), "properties": pids}


MANAGER_FIELDS = ("site_manager_name", "property_manager", "manager_name", "manager", "assigned_manager")


def parse_property(p):
    return {
        "id": p.get("id"),
        "address": p.get("address_line1") or p.get("address") or "",
        "city": p.get("city") or "",
        "zip": p.get("postal_code") or p.get("zip") or "",
        "name": p.get("name") or "",
        "source_id": str(p.get("source_id") or ""),
        "manager": next((p[k] for k in MANAGER_FIELDS if p.get(k)), None),
    }


# ---------------------------------------------------------------------------------------------
# Normalizing addresses and names

ADDR_SYN = {"street": "st", "str": "st", "avenue": "ave", "av": "ave", "road": "rd", "drive": "dr", "lane": "ln",
            "boulevard": "blvd", "circle": "cir", "court": "ct", "place": "pl", "parkway": "pkwy", "highway": "hwy",
            "terrace": "ter", "trail": "trl", "north": "n", "south": "s", "east": "e", "west": "w",
            "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
            "apartment": "#", "apt": "#", "unit": "#", "suite": "#", "ste": "#", "no": "#", "number": "#"}


def norm_addr(a):
    if not a:
        return ""
    s = str(a).lower().replace("#", " # ")
    s = re.sub(r"[.,'\"]", " ", s)
    s = re.sub(r"\s-\s|\s-|-\s", " ", s)
    toks = [ADDR_SYN.get(t, t) for t in s.split()]
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "#":
            if i + 1 < len(toks) and toks[i + 1] != "#":
                unit = "#" + toks[i + 1]
                if not out or out[-1] != unit:
                    out.append(unit)
                i += 2
                continue
            i += 1
            continue
        out.append(t)
        i += 1
    return " ".join(out)


def strip_unit(a):
    return " ".join(t for t in a.split() if not t.startswith("#"))


def zip5(z):
    m = re.search(r"\d{5}", str(z or ""))
    return m.group(0) if m else ""


def norm_city(c):
    return re.sub(r"[^a-z]", "", str(c or "").lower())


ENTITY = re.compile(r"\b(llc|l\.l\.c|inc|corp|corporation|company|co|trust|trustee|trustees|holdings|properties|property|"
                    r"investments|investment|partners|partnership|group|lp|llp|ltd|rentals|rental|enterprises|management|"
                    r"capital|estate|ventures|realty|series|fund|foundation|homes)\b", re.I)


def person_keys(name):
    """first|last keys for a person or couple; entity|name for companies and trusts."""
    if not name:
        return set()
    raw = str(name).strip()
    if ENTITY.search(raw):
        n = re.sub(r"[^a-z0-9 ]", " ", raw.lower())
        n = re.sub(r"\b(llc|inc|corp|co|lp|ltd|the)\b", " ", n)
        n = re.sub(r"\s+", " ", n).strip()
        return {"entity|" + n} if n else set()
    s = raw.lower().replace("&", " and ")
    s = re.sub(r"[^a-z, ]", " ", s)
    keys = set()
    if s.count(",") == 1:
        last, rest = s.split(",")
        lasts = last.split()
        firsts = [t for t in rest.split() if t != "and" and len(t) > 1]
        if lasts:
            for f in firsts:
                keys.add(f + "|" + lasts[-1])
        return keys
    toks = [t for t in s.replace(",", " ").split() if len(t) > 1 or t == "and"]
    toks = [t for t in toks if t not in ("jr", "sr", "ii", "iii", "iv", "mr", "mrs", "ms", "dr")]
    if len(toks) < 2:
        return keys
    if "and" in toks:
        last = toks[-1]
        for f in toks[:-1]:
            if f != "and":
                keys.add(f + "|" + last)
        return keys
    keys.add(toks[0] + "|" + toks[-1])
    return keys


def display_manager(m):
    m = re.sub(r"\s+", " ", str(m or "")).strip()
    if m.count(",") == 1:
        last, first = [x.strip() for x in m.split(",")]
        if first and last and re.fullmatch(r"[A-Za-z.' -]+", first + last):
            m = first + " " + last
    return m


# ---------------------------------------------------------------------------------------------
# The roster

class RosterError(Exception):
    pass


ROLE_HEADERS = OrderedDict([
    ("manager", ["sitemanagername", "sitemanager", "propertymanager", "propertymanagername", "portfoliomanager",
                 "portfoliomanagername", "manager", "managername", "assignedmanager", "assignedto", "assigneduser",
                 "accountmanager", "rentalmanager", "managedby", "teammember", "pm", "pmname"]),
    ("address", ["propertyaddress", "propertystreetaddress1", "propertystreetaddress", "propertyaddress1", "address",
                 "streetaddress", "address1", "addressline1", "street", "addr"]),
    ("city", ["propertycity", "city"]),
    ("zip", ["propertyzip", "propertyzipcode", "zip", "zipcode", "postalcode", "postal", "zip5"]),
    ("prop_id", ["propertyid", "propid", "propertynumber", "propertyno", "propertycode"]),
    ("prop_name", ["propertyname", "property", "building", "buildingname"]),
    ("owner_name", ["propertyownername", "propertyowner", "propertyowners", "ownername", "ownernames", "owner", "owners",
                    "ownerfullname", "landlord"]),
    ("owner_email", ["propertyowneremail", "owneremail", "owneremails", "owneremailaddress", "email", "emails",
                     "emailaddress"]),
])


def header_role(cell):
    h = re.sub(r"[^a-z0-9]", "", str(cell or "").lower())
    if not h:
        return None, 99
    for role, names in ROLE_HEADERS.items():
        if h in names:
            return role, names.index(h)
    if "manager" in h and not any(x in h for x in ("company", "phone", "email", "fee")):
        return "manager", 50
    if "email" in h:
        return "owner_email", 50
    if "owner" in h and not any(x in h for x in ("phone", "id", "address", "since", "percent")):
        return "owner_name", 50
    if "address" in h and "email" not in h and "owner" not in h:
        return "address", 50
    return None, 99


def read_table(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            raise RosterError("reading .xlsx needs openpyxl (pip install openpyxl), or save the roster as .csv")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        best = []
        for ws in wb.worksheets:
            rows = [["" if v is None else str(v).strip() for v in row] for row in ws.iter_rows(values_only=True)]
            rows = [r for r in rows if any(r)]
            if len(rows) > len(best):
                best = rows
        return best
    if ext == ".xls":
        raise RosterError("old .xls files can't be read here; save the roster as .xlsx or .csv")
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        text = f.read()
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel_tab if ext == ".tsv" else csv.excel
    return [[c.strip() for c in row] for row in csv.reader(text.splitlines(), dialect) if any(c.strip() for c in row)]


def read_roster(path):
    rows = read_table(path)
    best = None
    for i, row in enumerate(rows[:30]):
        roles = {}
        for j, cell in enumerate(row):
            role, rank = header_role(cell)
            if role and (role not in roles or rank < roles[role][1]):
                roles[role] = (j, rank, cell)
        if "manager" in roles and len(roles) >= 2 and (best is None or len(roles) > len(best[1])):
            best = (i, roles)
    if not best:
        raise RosterError("couldn't find a header row with a manager column (for example 'Property manager' or 'Site Manager Name')")
    hi, roles = best
    cols = {role: v[0] for role, v in roles.items()}
    out = []
    for row in rows[hi + 1:]:
        cell = lambda role: row[cols[role]].strip() if role in cols and cols[role] < len(row) else ""
        rec = {role: cell(role) for role in cols}
        if not any(rec.values()) or re.fullmatch(r"(?i)total.*", next(iter(rec.values()), "")):
            continue
        if not rec.get("address") and rec.get("prop_name"):
            m = re.search(r"\b(\d+[A-Za-z]?\s+[^,]+?)(?:,|$)", rec["prop_name"])
            if m:
                rec["address"] = m.group(1)
            z = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", rec["prop_name"])
            if z and not rec.get("zip"):
                rec["zip"] = z.group(1)
        rec["manager"] = display_manager(rec.get("manager"))
        out.append(rec)
    used = {role: roles[role][2] for role in roles}
    return out, used


# ---------------------------------------------------------------------------------------------
# Matching

class Index:
    def __init__(self, roster, props):
        self.pid, self.addr, self.addr_city, self.addr_only, self.base, self.name = {}, {}, {}, {}, {}, {}
        self.building = {}
        self.email, self.person = {}, {}
        add = lambda d, k, m: d.setdefault(k, set()).add(m)
        self.managers = []
        for r in roster:
            m = r.get("manager")
            if not m:
                continue
            if m not in self.managers:
                self.managers.append(m)
            if r.get("prop_id"):
                add(self.pid, r["prop_id"].strip().lower(), m)
            a = norm_addr(r.get("address"))
            if a:
                add(self.addr_only, a, m)
                if zip5(r.get("zip")):
                    add(self.addr, (a, zip5(r.get("zip"))), m)
                if norm_city(r.get("city")):
                    add(self.addr_city, (a, norm_city(r.get("city"))), m)
                add(self.base, strip_unit(a), m)
                if strip_unit(a) == a:
                    add(self.building, a, m)  # a roster row for the whole building (no unit)
            if r.get("prop_name"):
                add(self.name, norm_addr(r["prop_name"]), m)
            for e in split_emails(r.get("owner_email")):
                add(self.email, e, m)
            for part in re.split(r";|\n|\s/\s", r.get("owner_name") or ""):
                for k in person_keys(part):
                    add(self.person, k, m)
        self.has_zip = bool(self.addr)
        self.has_city = bool(self.addr_city)
        for p in props.values():
            if p.get("manager"):
                m = display_manager(p["manager"])
                if m not in self.managers:
                    self.managers.append(m)

    @staticmethod
    def one(s):
        return next(iter(s)) if s and len(s) == 1 else None

    def property_manager(self, p):
        """(manager, how) for one property record, or (None, reason)."""
        if p.get("manager"):
            return display_manager(p["manager"]), "property"
        if p.get("source_id") and p["source_id"].strip().lower() in self.pid:
            m = self.one(self.pid[p["source_id"].strip().lower()])
            if m:
                return m, "property"
        a = norm_addr(p.get("address"))
        if a:
            hits = []
            if self.has_zip and zip5(p.get("zip")):
                hits.append(self.addr.get((a, zip5(p.get("zip")))))
            if self.has_city and norm_city(p.get("city")):
                hits.append(self.addr_city.get((a, norm_city(p.get("city")))))
            if not (self.has_zip or self.has_city):
                hits.append(self.addr_only.get(a))
            for h in hits:
                if h:
                    m = self.one(h)
                    return (m, "property") if m else (None, "conflict")
            if self.has_zip or self.has_city:
                h = self.addr_only.get(a)
                if h and self.one(h):
                    return self.one(h), "property"
            # building-level fallback, never a guess between units:
            # a unit counts for the roster's row for its whole building; a whole-building property counts
            # only when every unit the roster lists for that building has the same manager
            b = strip_unit(a)
            h = self.building.get(b) if b != a else self.base.get(b)
            if h and self.one(h):
                return self.one(h), "property"
        if p.get("name"):
            h = self.name.get(norm_addr(p["name"]))
            if h and self.one(h):
                return self.one(h), "property"
        return None, "not_on_roster"


REASONS = {
    "no_link": "not linked to a property owner, and no email or name match in the roster",
    "not_on_roster": "linked to a property that isn't on the roster (or its roster row has no manager)",
    "missing_property": "linked property record didn't come back from the connector",
    "split": "the property owner's properties are split evenly between managers",
    "conflict": "the roster gives the same address to more than one manager",
    "ambiguous": "the email or name matches more than one manager",
}


def match(resp, owners, props, idx):
    reason = "no_link"
    p = props.get(resp["property"]) if resp["property"] else None
    if resp["property"] and not p:
        reason = "missing_property"
    if p:
        m, how = idx.property_manager(p)
        if m:
            return m, "property", None
        reason = how
    o = owners.get(resp["owner"]) if resp["owner"] else None
    if o:
        counts = Counter()
        found = 0
        for pid in o["properties"]:
            pp = props.get(pid)
            if not pp:
                continue
            found += 1
            m, _ = idx.property_manager(pp)
            if m:
                counts[m] += 1
        if counts:
            top = counts.most_common()
            if len(top) > 1 and top[0][1] == top[1][1]:
                return None, None, "split"
            return top[0][0], "owner", None
        if reason == "no_link" and o["properties"]:
            reason = "not_on_roster" if found else "missing_property"
    emails = set(resp["emails"]) | (o["emails"] if o else set())
    hit = set()
    for e in emails:
        hit |= idx.email.get(e, set())
    if len(hit) == 1:
        return next(iter(hit)), "email", None
    if len(hit) > 1:
        reason = "ambiguous"
    keys = person_keys(resp["name"]) | (person_keys(o["name"]) if o else set())
    hit = set()
    for k in keys:
        hit |= idx.person.get(k, set())
    if len(hit) == 1:
        return next(iter(hit)), "name", None
    if len(hit) > 1:
        reason = "ambiguous"
    return None, None, reason


# ---------------------------------------------------------------------------------------------
# Scoring

def aggregate(rs, name):
    with_nps = [r for r in rs if r["nps"] is not None]
    prom = sum(r["nps"] >= 9 for r in with_nps)
    det = sum(r["nps"] <= 6 for r in with_nps)
    pas = len(with_nps) - prom - det
    calls = [r for r in rs if r["call"]]
    picked = sum(r["call"] == "picked" for r in calls)
    dets = [r for r in with_nps if r["nps"] <= 6 and r["call"]]
    scores = [r["score"] for r in rs if r["score"] is not None]
    q = {}
    for k in QUESTIONS:
        vals = [r["q"][k] * 10 / TOP[k] for r in rs if r["q"][k] not in (None, NA)]
        q[k] = {"v": rnd(sum(vals) / len(vals), 1) if vals else None, "n": len(vals)}
    return {
        "name": name, "n": len(rs), "prom": prom, "pas": pas, "det": det,
        "nps": rnd(100 * (prom - det) / len(with_nps)) if with_nps else 0,
        "picked": picked, "answered": len(calls), "pickup": (100 * picked / len(calls)) if calls else 0,
        "sat": rnd(sum(scores) / len(scores), 1) if scores else 0.0,
        "vm": sum(r["call"] == "voicemail" for r in dets), "vmd": len(dets), "q": q,
    }


def score_manager(m, c):
    m["scored"] = m["n"] >= 5
    m["small"] = m["n"] < 30
    for k in QUESTIONS:
        v, cv = m["q"][k]["v"], c["q"][k]["v"]
        m["q"][k]["c"] = cv
        m["q"][k]["gap"] = rnd(sub(v, cv), 1) if v is not None and cv is not None else None
    ok = [k for k in QUESTIONS if m["q"][k]["n"] >= 3 and m["q"][k]["gap"] is not None]
    pos = [k for k in ok if m["q"][k]["gap"] > 0]
    neg = [k for k in ok if m["q"][k]["gap"] < 0]
    m["strength"] = max(pos, key=lambda k: m["q"][k]["gap"]) if pos else None
    m["biggap"] = min(neg, key=lambda k: m["q"][k]["gap"]) if neg else None
    m["focus"] = focus_line(m, c) if m["scored"] else ""
    return m


def focus_line(m, c):
    pick, cpick = rnd(m["pickup"]), rnd(c["pickup"])
    below = cpick - pick if m["answered"] and c["answered"] else 0
    if (m["vmd"] and m["vm"] * 2 >= m["vmd"]) or (m["answered"] and below >= 10):
        s = f"Answer the phone. Their property owners reach a person {pick}% of the time"
        if below > 0:
            s += f" ({below} points below the company)"
        if m["vmd"]:
            if m["vm"] == m["vmd"] == 1:
                s += ", and their one detractor got voicemail"
            elif m["vm"] == m["vmd"]:
                s += f", and all {m['vmd']} of their detractors got voicemail"
            else:
                s += f", and {m['vm']} of their {m['vmd']} detractors got voicemail"
        return s + ". Nothing else on this card moves faster."
    if m["biggap"] and m["q"][m["biggap"]]["gap"] <= -0.5:
        k = m["biggap"]
        return (f"{FIXES[k]} Their property owners rate it {m['q'][k]['v']:.1f} out of 10, against "
                f"{m['q'][k]['c']:.1f} company-wide. Nothing else on this card moves faster.")
    if m["strength"]:
        g = m["q"][m["strength"]]["gap"]
        return (f"Protect the lead on {m['strength'].lower()}. They're +{g:.1f} above the company there. "
                "Ask them to show the team how.")
    return ("Hold the line. Every question sits within half a point of the company. "
            "Use this one-on-one to pick the next thing to improve together.")


def fmt_date(s):
    try:
        d = dt.date.fromisoformat(s[:10])
        return d.strftime("%b ") + str(d.day) + d.strftime(", %Y")
    except (ValueError, TypeError):
        return s


def clean_company(name):
    n = re.sub(r",?\s+(llc|l\.l\.c\.|inc\.?|incorporated|ltd\.?|lp|llp|pllc|corp\.?)$", "", str(name).strip(), flags=re.I)
    return n.strip(" ,")


# ---------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--roster")
    ap.add_argument("--unmatched-to")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--expected", type=int)
    ap.add_argument("--allow-thin", action="store_true")
    ap.add_argument("--pulled", default=dt.date.today().isoformat())
    ap.add_argument("--out", default="property-manager-scorecards.html")
    a = ap.parse_args()
    outdir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(outdir, exist_ok=True)
    report_path = os.path.join(outdir, "match-report.md")
    summary_path = os.path.join(outdir, "scorecards-summary.json")

    def stop(code, status, line, **extra):
        json.dump({"status": status, **extra}, open(summary_path, "w"), indent=1)
        print(line)
        sys.exit(code)

    raw = load_rows(a.work, "responses", ("responses", "rows"))
    seen, resps = set(), []
    for r in map(parse_response, raw):
        if r["id"] and r["id"] in seen:
            continue
        seen.add(r["id"])
        if not r["counts"]:
            continue
        if a.date_from and r["date"] and r["date"] < a.date_from:
            continue
        if a.date_to and r["date"] and r["date"] > a.date_to:
            continue
        resps.append(r)
    if not resps:
        stop(5, "no_responses", f"stopped: no counted responses in {a.work}")
    if a.expected and len(resps) < a.expected and not (a.date_from or a.date_to):
        stop(3, "data_short", f"stopped: data_short, {len(resps)} responses loaded but the connector reports {a.expected}; pull the missing pages",
             loaded=len(resps), expected=a.expected)
    owners = {o["id"]: o for o in map(parse_owner, load_rows(a.work, "owners", ("owners", "rows"))) if o["id"]}
    props = {p["id"]: p for p in map(parse_property, load_rows(a.work, "properties", ("properties", "rows"))) if p["id"]}

    roster, used, roster_name = [], {}, None
    if a.roster:
        try:
            roster, used = read_roster(a.roster)
        except RosterError as e:
            stop(4, "roster_unreadable", f"stopped: roster_unreadable, {e}")
        roster_name = os.path.basename(a.roster)
    elif not any(p.get("manager") for p in props.values()):
        stop(4, "roster_missing", "stopped: roster_missing, no roster given and the property records carry no manager field")
    idx = Index(roster, props)
    if a.unmatched_to and display_manager(a.unmatched_to) not in idx.managers:
        idx.managers.append(display_manager(a.unmatched_to))
    if not idx.managers:
        stop(4, "roster_unreadable", "stopped: roster_unreadable, the roster has no names in its manager column")

    per = OrderedDict((m, []) for m in idx.managers)
    how = {m: Counter() for m in idx.managers}
    unassigned, reasons = [], Counter()
    for r in resps:
        m, h, why = match(r, owners, props, idx)
        if m:
            per.setdefault(m, []).append(r)
            how.setdefault(m, Counter())[h] += 1
        else:
            reasons[why] += 1
            if a.unmatched_to:
                mm = display_manager(a.unmatched_to)
                per[mm].append(r)
                how[mm]["by exclusion"] += 1
            else:
                unassigned.append(r)
    matched = len(resps) - sum(reasons.values())
    share = matched / len(resps)

    company = aggregate(resps, clean_company(a.company))
    managers = [score_manager(aggregate(rs, m), company) for m, rs in per.items()]
    managers.sort(key=lambda m: (not m["scored"], -(m["nps"] if m["scored"] else 0), -m["n"], m["name"]))
    dates = sorted(r["date"] for r in resps if r["date"])
    first, last = (fmt_date(dates[0]), fmt_date(dates[-1])) if dates else ("", "")
    source = f"through {roster_name}" if roster_name else "through the manager field in your software"
    tail = (f"the rest attributed to {display_manager(a.unmatched_to)} by exclusion" if a.unmatched_to
            else f"{len(unassigned)} unassigned")
    footer = (f"Live from the PropertyManagement.com MCP, pulled {fmt_date(a.pulled)} · {len(resps)} completed property owner "
              f"survey responses, {first} to {last} · {matched} matched to a property manager {source}; {tail}.")
    warning = None
    thin = share < 0.5 and not a.unmatched_to
    if thin:
        warning = (f"Only {matched} of {len(resps)} responses matched a property manager. The roster may be missing "
                   "addresses or property owners, so read these scorecards with care.")

    # report
    lines = ["# Matching report", ""]
    if roster_name:
        cols = ", ".join(f"{k.replace('_', ' ')} = \"{v}\"" for k, v in used.items())
        lines += [f"Roster: {roster_name} ({len(roster)} rows, {sum(1 for r in roster if r.get('manager'))} with a manager). Columns used: {cols}.", ""]
    lines += [f"Responses: {len(resps)} counted ({first} to {last}). Matched {matched} ({round(100 * share)}%).", "",
              "| Manager | Responses | Property | Owner's properties | Email | Name | Scored |",
              "|---|---|---|---|---|---|---|"]
    for m in managers:
        c = how.get(m["name"], Counter())
        excl = f" (+{c['by exclusion']} by exclusion)" if c.get("by exclusion") else ""
        lines.append(f"| {m['name']} | {m['n']}{excl} | {c['property']} | {c['owner']} | {c['email']} | {c['name']} | {'yes' if m['scored'] else 'needs 5'} |")
    if not a.unmatched_to:
        lines.append(f"| Unassigned | {len(unassigned)} | | | | | |")
    if reasons:
        lines += ["", "Not matched, by reason:"] + [f"- {n}: {REASONS.get(k, k)}" for k, n in reasons.most_common()]
    if UNKNOWN:
        lines += ["", "Answers the script didn't recognize (skipped; the survey may have changed):"] + [f"- {n}: {k}" for k, n in UNKNOWN.most_common()]
    open(report_path, "w").write("\n".join(lines) + "\n")

    scored = [m for m in managers if m["scored"]]
    above = max(scored, key=lambda m: m["nps"]) if scored else None
    below = min(scored, key=lambda m: m["nps"]) if scored else None
    summary = {
        "status": "roster_thin" if thin and not a.allow_thin else "built",
        "company": {"name": company["name"], "responses": len(resps), "nps": company["nps"],
                    "pickup": rnd(company["pickup"]) if company["answered"] else None},
        "matched": matched, "unassigned": len(unassigned) if not a.unmatched_to else 0,
        "reasons": {REASONS.get(k, k): n for k, n in reasons.most_common()},
        "managers": len(managers), "scored": len(scored),
        "furthest_above": {"name": above["name"], "nps": above["nps"], "vs_company": above["nps"] - company["nps"]} if above else None,
        "furthest_below": {"name": below["name"], "nps": below["nps"], "vs_company": below["nps"] - company["nps"]} if below else None,
        "unrecognized_answers": sum(UNKNOWN.values()), "page": os.path.abspath(a.out), "report": report_path,
    }
    if thin and not a.allow_thin:
        stop(2, "roster_thin", f"stopped: roster_thin, only {matched} of {len(resps)} responses matched; see match-report.md",
             **{k: v for k, v in summary.items() if k != "status"})

    data = {"version": VERSION, "company_name": company["name"], "company": company, "managers": managers,
            "unassigned": aggregate(unassigned, "Unassigned") if unassigned else None,
            "questions": QUESTIONS, "footer": footer, "warning": warning}
    tpl = open(TEMPLATE, encoding="utf-8").read()
    token = "/*__SCORECARD_DATA__*/null"
    if token not in tpl:
        sys.exit("template is missing its data placeholder")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    open(a.out, "w", encoding="utf-8").write(tpl.replace(token, blob, 1))
    json.dump(summary, open(summary_path, "w"), indent=1)
    print(f"built: {len(resps)} responses, {matched} matched to {sum(1 for m in managers if m['n'])} managers, "
          f"{summary['unassigned']} unassigned -> {os.path.basename(a.out)}")


if __name__ == "__main__":
    main()
