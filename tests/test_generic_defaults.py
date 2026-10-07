"""Pin the generic (non-client) defaults the public skills must ship with.

Both skills carry identical copies of appfolio_loader.py and setup_config.py,
so every test runs against both copies.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ["property-owner-retention-radar", "property-owner-newsletter"]


def load_script(skill: str, script: str):
    path = ROOT / "skills" / skill / "scripts" / script
    name = f"{script[:-3]}_{skill.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("skill", SKILLS)
def test_region_default_is_not_a_specific_city(skill):
    """With no config, no real-world city may be treated as the core market."""
    mod = load_script(skill, "appfolio_loader.py")
    for city in ("Chicago", "Testville", "New York"):
        assert mod.region_of(city, {}) == "Suburbs"
        assert mod.region_of(city, {"regions": {}}) == "Suburbs"


@pytest.mark.parametrize("skill", SKILLS)
def test_region_config_still_applies(skill):
    mod = load_script(skill, "appfolio_loader.py")
    cfg = {"regions": {"core_cities": ["Testville"], "core_label": "Core", "other_label": "Outer"}}
    assert mod.region_of("Testville", cfg) == "Core"
    assert mod.region_of("testville", cfg) == "Core"
    assert mod.region_of("Elsewhere", cfg) == "Outer"
    assert mod.region_of("", cfg) == "Unknown"


def run_setup(skill: str, *argv):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "skills" / skill / "scripts" / "setup_config.py"), *argv],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return proc


@pytest.mark.parametrize("skill", SKILLS)
def test_setup_status_flags_angle_bracket_placeholders(skill, tmp_path):
    """'<company name>' style placeholders must count as open items, even after
    setup.completed_at was stamped, or SKILL.md's 'placeholders still open' rule is a lie."""
    cfg = {
        "company": {"name": "<company name>", "short_name": "Example PM"},
        "setup": {"completed_at": "2026-01-01T00:00:00"},
    }
    cfg_path = tmp_path / "client-config.json"
    cfg_path.write_text(json.dumps(cfg))
    out = json.loads(run_setup(skill, "status", "--config", str(cfg_path)).stdout)
    assert out["setup_needed"] is True
    assert any(it["path"] == "company.name" for it in out["open_items"])


@pytest.mark.parametrize("skill", SKILLS)
def test_setup_status_clean_when_filled(skill, tmp_path):
    cfg = {
        "company": {"name": "Example PM", "short_name": "Example PM"},
        "setup": {"completed_at": "2026-01-01T00:00:00"},
    }
    cfg_path = tmp_path / "client-config.json"
    cfg_path.write_text(json.dumps(cfg))
    out = json.loads(run_setup(skill, "status", "--config", str(cfg_path)).stdout)
    assert out["setup_needed"] is False
    assert out["open_items"] == []
