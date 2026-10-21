import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
EXPORTS = FIX / "exports"
CONFIG = FIX / "member-config.json"
BENCHMARKS = FIX / "benchmarks.json"
SURVEY = FIX / "survey.json"
OUT = FIX / "out"


def run(cmd, cwd):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return proc


def test_retention_radar_pipeline(tmp_path_factory):
    out = tmp_path_factory.mktemp("radar-out")
    radar = ROOT / "skills" / "property-owner-retention-radar"
    run(
        [
            sys.executable,
            "scripts/appfolio_loader.py",
            "features",
            str(EXPORTS),
            "--out",
            str(out),
            "--survey",
            str(SURVEY),
            "--config",
            str(CONFIG),
        ],
        cwd=radar,
    )
    run(
        [
            sys.executable,
            "scripts/render_radar.py",
            "--out",
            str(out),
            "--config",
            str(CONFIG),
            "--benchmarks",
            str(BENCHMARKS),
        ],
        cwd=radar,
    )
    assert (out / "radar-dashboard.html").is_file()
    assert (out / "radar-summary.json").is_file()
    summary = json.loads((out / "radar-summary.json").read_text())
    assert "five" in summary


def test_newsletter_pipeline(tmp_path_factory):
    out = tmp_path_factory.mktemp("newsletter-out")
    nl = ROOT / "skills" / "property-owner-newsletter"
    run(
        [
            sys.executable,
            "scripts/appfolio_loader.py",
            "features",
            str(EXPORTS),
            "--out",
            str(out),
            "--survey",
            str(SURVEY),
            "--config",
            str(CONFIG),
        ],
        cwd=nl,
    )
    run(
        [
            sys.executable,
            "scripts/build_newsletter.py",
            "--out",
            str(out),
            "--config",
            str(CONFIG),
            "--benchmarks",
            str(BENCHMARKS),
            "--month",
            "2026-01",
        ],
        cwd=nl,
    )
    assert (out / "newsletter" / "merge.csv").is_file()
    assert (out / "newsletter" / "build-summary.json").is_file()


def test_package_skill_wraps_in_skill_folder_and_excludes_pycache():
    import importlib.util
    import py_compile
    import zipfile

    spec = importlib.util.spec_from_file_location("package", ROOT / "tools" / "package.py")
    pkg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pkg)

    for skill in ("property-owner-retention-radar", "property-owner-newsletter"):
        py_compile.compile(str(ROOT / "skills" / skill / "scripts" / "pm_benchmarks.py"))
        zip_path = pkg.package_skill(skill)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert f"{skill}/SKILL.md" in names
        assert all(n.startswith(f"{skill}/") for n in names), names
        assert not any("__pycache__" in n or n.endswith((".pyc", ".pyo")) for n in names), names

