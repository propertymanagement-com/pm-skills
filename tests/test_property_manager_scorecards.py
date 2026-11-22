"""Run the property-manager-scorecards suite (fictional data) as part of pytest.

The suite is a standalone script: it builds a fictional company, runs the
skill's build_scorecards.py against two roster formats, and checks matching,
every number against an independent computation, and the edge cases. It needs
openpyxl for the AppFolio-style .xlsx roster.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "property-manager-scorecards" / "run_tests.py"


def test_property_manager_scorecards_skill():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, "scorecards suite failed:\n" + result.stdout + result.stderr
    assert "PASS:" in result.stdout