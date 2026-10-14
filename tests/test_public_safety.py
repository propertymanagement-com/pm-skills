import importlib.util
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
    # Never put real client names, PMIDs, or domains in this repo, even in tests.
    (bad_dir / "leak.txt").write_text(
        "pmid 123456 owners@acme-realty.test call 312-555-9876\n",
        encoding="utf-8",
    )
    proc = run_check(bad_dir)
    assert proc.returncode != 0
    stderr = proc.stderr.lower()
    assert "email outside" in stderr
    assert "pmid 123456" in stderr
    assert "phone outside" in stderr


def test_denylist_matches_hashed_token():
    spec = importlib.util.spec_from_file_location("check_public_safety", CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.TOKEN_DENY.add(mod.h("zzfakeclientco"))
    errors: list[str] = []
    mod.check_denylist("Report for ZZFakeClientCo owners", "leak.txt", errors)
    assert any("denylisted" in e for e in errors)
