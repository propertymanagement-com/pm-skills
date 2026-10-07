#!/usr/bin/env python3
"""First-run setup for the member skills: find what the client config still needs, apply answers, mark setup complete.

The packaged config (assets/client-config.json) is read-only inside a member's Claude, so the member's working copy lives in the
folder they keep their monthly exports in (<exports>/client-config.json). The skills read that copy first and fall back to the package.

  python3 setup_config.py init   --from assets/client-config.json --to <exports>/client-config.json    copy the packaged config (no-op if exports copy exists)
  python3 setup_config.py seed   --config <exports>/client-config.json --org-json org.json               merge pm_org_get fields, then ensure report_salt
  python3 setup_config.py status --config <exports>/client-config.json                                 what is still unconfirmed, as JSON
  python3 setup_config.py checklist --config <exports>/client-config.json                              questions grouped with current values
  python3 setup_config.py apply  --config <exports>/client-config.json --answers answers.json          deep-merge answers, stamp setup.completed_at
"""
import argparse
import datetime as dt
import json
import os
import re
import secrets
import shutil
import sys

PLACEHOLDER = re.compile(r"\[CONFIRM|REPLACE-ME|CONFIRM\]|_confirm", re.I)

QUESTIONS = [
    ("Company", "company.short_name", "What do owners call you in a sentence (the short company name)?", "used in every email and talk track"),
    ("Company", "company.phone", "Main phone number owners should call?", "the closing line of every email falls back to it"),
    ("Company", "company.pmcom_profile_url", "Your PropertyManagement.com profile URL?", "the 'See our verified profile' link"),
    ("Team", "team.managers", "Your property managers: first name as it appears in AppFolio's Site Manager field, full name, direct phone (one line each)?", "owners are routed to their manager; the closing line uses the direct phone"),
    ("Brand", "brand.primary", "Brand primary colour (hex), accent colour (hex), display font, body font, and a logo URL?", "the emails, the report pages and the dashboard use them"),
    ("Regions", "regions.core_cities", "Which cities count as your core market (the rest are 'suburbs')?", "renewals and departures are sliced by region"),
    ("Newsletter", "newsletter.report_base_url", "Where will the per-owner report pages be hosted (a URL ending in /)?", "the 'See your portfolio report' button links there"),
    ("Newsletter", "newsletter.referral_line", "One soft referral line for the end of the owner email (or keep the default)?", "the only ask in the email"),
    ("Newsletter", "newsletter.company_block", "Two or three sentences on what changed this month (you will update this monthly)?", "the 'What we're changing' section; the send is held while it is a placeholder"),
    ("Newsletter", "newsletter.certifications_to_feature", "Which PropertyManagement.com certifications to feature, with the value and the verified-PM median from your profile?", "the 'How you compare' sentence; refresh quarterly"),
    ("Fees", "fees", "Management fee (% or flat), leasing fee, renewal fee?", "only used to size what a departure costs; skip if you prefer"),
    ("Risk model", "risk_tiers", "Keep the defaults (call at 50 points, watch at 25, cap 10 calls / 5 per manager)?", "the call list size on a Monday"),
]


def get(d, path):
    cur = d
    for k in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(k)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
        if cur is None:
            return None
    return cur


def set_path(d, path, value):
    keys = path.split(".")
    cur = d
    for k in keys[:-1]:
        if isinstance(cur, list):
            cur = cur[int(k)]
        else:
            cur = cur.setdefault(k, {})
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def ensure_report_salt(cfg):
    nl = cfg.setdefault("newsletter", {})
    if not nl.get("report_salt"):
        nl["report_salt"] = secrets.token_hex(16)


def seed_from_org(cfg, org):
    """Merge pm_org_get (or compatible) JSON into company fields when placeholders remain."""
    co = cfg.setdefault("company", {})
    mapping = {
        "name": org.get("name") or org.get("company_name"),
        "pmid": org.get("pmid") or org.get("pmidAllowlist", [None])[0] if isinstance(org.get("pmidAllowlist"), list) else org.get("pmid"),
        "website": org.get("website") or org.get("url"),
        "logo_url": org.get("logo_url") or org.get("logoUrl"),
    }
    for key, val in mapping.items():
        if val in (None, ""):
            continue
        cur = co.get(key)
        if cur is None or (isinstance(cur, str) and (cur.startswith("<") or PLACEHOLDER.search(cur))):
            co[key] = val
    if co.get("name") and (not co.get("short_name") or str(co.get("short_name", "")).startswith("<")):
        co["short_name"] = co["name"]
    if co.get("name") and cfg.get("sender", {}).get("from_name", "").startswith("<"):
        cfg.setdefault("sender", {})["from_name"] = co["name"]


def open_items(cfg):
    items = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else k
                if k.startswith("_") and ("confirm" in k.lower()):
                    items.append({"path": path or k, "kind": "confirm-note", "note": str(v)})
                    continue
                walk(v, p)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}.{i}")
        elif isinstance(node, str) and PLACEHOLDER.search(node):
            items.append({"path": path, "kind": "placeholder", "value": node[:80]})
        elif node is None and re.search(r"\.(phone|full_name)$|report_base_url|logo_url", path):
            items.append({"path": path, "kind": "missing", "value": None})

    walk(cfg, "")
    seen = set()
    out = []
    mgrs = cfg.get("team", {}).get("managers") or []
    for it in items:
        m = re.match(r"team\.managers\.(\d+)(\..*)?$", it["path"])
        if m and int(m.group(1)) < len(mgrs):
            it["path"] = f"team.managers[{mgrs[int(m.group(1))].get('first_name', m.group(1))}]{m.group(2) or ''}"
        if it["path"] in seen:
            continue
        seen.add(it["path"])
        out.append(it)
    return out


def coerce(v):
    if isinstance(v, str):
        if v.lower() in ("true", "yes"):
            return True
        if v.lower() in ("false", "no"):
            return False
        if v.lower() in ("null", "none", ""):
            return None
        try:
            return json.loads(v) if v[:1] in "[{" else (int(v) if re.fullmatch(r"-?\d+", v) else float(v) if re.fullmatch(r"-?\d+\.\d+", v) else v)
        except Exception:
            return v
    return v


def deep_merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def drop_resolved_confirms(cfg):
    def walk(node):
        if isinstance(node, dict):
            for k in list(node.keys()):
                if k.startswith("_") and "confirm" in k.lower():
                    siblings = [v for kk, v in node.items() if not kk.startswith("_")]
                    if siblings and not any((isinstance(v, str) and PLACEHOLDER.search(v)) or v is None for v in siblings):
                        node.pop(k)
                else:
                    walk(node[k])
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(cfg)


def write_config(path, cfg):
    ensure_report_salt(cfg)
    json.dump(cfg, open(path, "w"), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("init")
    a.add_argument("--from", dest="src", required=True)
    a.add_argument("--to", dest="dst", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--config", required=True)
    s.add_argument("--org-json", required=True)
    b = sub.add_parser("status")
    b.add_argument("--config", required=True)
    c = sub.add_parser("checklist")
    c.add_argument("--config", required=True)
    d = sub.add_parser("apply")
    d.add_argument("--config", required=True)
    d.add_argument("--answers")
    d.add_argument("--set", action="append", default=[])
    d.add_argument("--by", default="")
    args = ap.parse_args()

    if args.cmd == "init":
        if os.path.exists(args.dst):
            print(json.dumps({"ok": True, "config": args.dst, "note": "already exists, left untouched (existing member config preserved)"}))
            return
        os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
        shutil.copy(args.src, args.dst)
        cfg = json.load(open(args.dst))
        ensure_report_salt(cfg)
        write_config(args.dst, cfg)
        print(json.dumps({"ok": True, "config": args.dst, "note": "copied from the package; report_salt generated locally"}))
        return

    cfg = json.load(open(args.config))

    if args.cmd == "seed":
        org = json.load(open(args.org_json))
        seed_from_org(cfg, org)
        ensure_report_salt(cfg)
        write_config(args.config, cfg)
        print(json.dumps({"ok": True, "config": args.config, "note": "org fields merged; report_salt ensured (not printed)"}))
        return

    if args.cmd == "status":
        items = open_items(cfg)
        print(
            json.dumps(
                {
                    "config": args.config,
                    "completed_at": (cfg.get("setup") or {}).get("completed_at"),
                    "open_items": items,
                    "setup_needed": bool(items) or not (cfg.get("setup") or {}).get("completed_at"),
                },
                indent=1,
            )
        )
        return

    if args.cmd == "checklist":
        opens = {it["path"] for it in open_items(cfg)}
        print(
            f"Setup checklist for {cfg.get('company', {}).get('name', 'the company')} (current value in brackets; answer what you can, skip the rest):\n"
        )
        grp = None
        for g, path, q, why in QUESTIONS:
            if g != grp:
                print(f"## {g}")
                grp = g
            cur = get(cfg, path)
            flag = " **needs an answer**" if (path in opens or any(o.startswith(path) for o in opens) or cur is None) else ""
            shown = json.dumps(cur)[:140] if not isinstance(cur, str) else cur[:140]
            print(f"- {q}{flag}\n  why: {why}\n  now: {shown}")
        print("\n## Exports\n- Where is the folder with this month's AppFolio exports?")
        print("- Is the PropertyManagement.com connector added? (survey + benchmarks + pm_org_get)")
        return

    if args.cmd == "apply":
        before = len(open_items(cfg))
        if args.answers:
            deep_merge(cfg, json.load(open(args.answers)))
        for kv in args.set:
            k, _, v = kv.partition("=")
            set_path(cfg, k, coerce(v))
        drop_resolved_confirms(cfg)
        items = open_items(cfg)
        cfg.setdefault("setup", {})
        cfg["setup"]["completed_at"] = cfg["setup"].get("completed_at") or dt.datetime.now().isoformat(timespec="seconds")
        cfg["setup"]["last_updated"] = dt.datetime.now().isoformat(timespec="seconds")
        if args.by:
            cfg["setup"]["completed_by"] = args.by
        write_config(args.config, cfg)
        print(json.dumps({"ok": True, "config": args.config, "resolved": before - len(items), "still_open": items}, indent=1))


if __name__ == "__main__":
    main()
