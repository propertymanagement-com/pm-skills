import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tools" / "check_public_safety.py"


def run_check(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), str(path)],
        capture_output=True,
        text=True,
    )


def test_public_safety_passes_on_repo():
    proc = run_check(ROOT)
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_public_safety_fails_on_bad_fixture(tmp_path):
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    # Synthetic leak content — never committed; exercises the denylist + email rules.
    (bad_dir / "leak.txt").write_text(
        "Landmark Property Management pmid 4192 owners@landmarkrgc.com Adam Sieger\n",
        encoding="utf-8",
    )
    proc = run_check(bad_dir)
    assert proc.returncode != 0
    assert "denylisted" in proc.stderr.lower() or "email" in proc.stderr.lower()
