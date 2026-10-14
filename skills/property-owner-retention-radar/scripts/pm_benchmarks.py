"""Load pm_benchmarks_get snapshot JSON for render/build scripts (stdlib only)."""
import json
import os
import re


def _parse_nps(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    m = re.search(r"\+?(-?\d+(?:\.\d+)?)", str(value))
    return float(m.group(1)) if m else None


def _metric(raw, key):
    for row in raw.get("certified_metrics") or []:
        if row.get("key") == key:
            return row
    return None


def _survey(raw, key):
    for row in raw.get("owner_survey") or []:
        if row.get("key") == key:
            return row
    return None


def normalize(raw: dict) -> dict:
    """Map pm_benchmarks_get payload to the flat dict the skills expect."""
    if raw.get("renewal_median") is not None:
        return raw
    out = {"as_of": raw.get("as_of"), "source": raw.get("source")}
    m = _metric(raw, "lease_renewal_rate")
    if m:
        out["renewal_median"] = m.get("median")
        out["renewal_n"] = m.get("n_pms")
    m = _metric(raw, "occupancy_rate")
    if m:
        out["occupancy_median"] = m.get("median")
        out["occupancy_n"] = m.get("n_pms")
    m = _metric(raw, "rent_collection_rate")
    if m:
        out["rent_collection_median"] = m.get("median")
        out["rent_collection_n"] = m.get("n_pms")
    m = _metric(raw, "repair_completion_median_days")
    if m:
        out["repair_median"] = m.get("median")
    s = _survey(raw, "nps_all_responses")
    if s:
        out["nps_all"] = _parse_nps(s.get("value"))
    s = _survey(raw, "median_pm_nps")
    if s:
        out["nps_median_pm"] = _parse_nps(s.get("value"))
    s = _survey(raw, "top_quartile_pm_nps")
    if s:
        out["nps_top_quartile"] = _parse_nps(s.get("value"))
    s = _survey(raw, "nps_maintenance_costs_in_line")
    if s:
        out["cliff_in_line"] = s.get("value")
    s = _survey(raw, "nps_maintenance_costs_somewhat_above")
    if s:
        out["cliff_somewhat_above"] = s.get("value")
    return out


def load(path: str | None) -> dict | None:
    if not path or not os.path.isfile(path):
        return None
    return normalize(json.load(open(path)))


def available(bench: dict | None) -> bool:
    return bool(bench and bench.get("as_of") and bench.get("renewal_median") is not None)
