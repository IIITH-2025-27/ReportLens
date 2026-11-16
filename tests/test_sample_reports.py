"""The real-world sample reports (sample_reports/real_world, run_log J) through the whole pipeline with the v5 config (the lite web app's):
no sentence may get a harmful verdict. Stand-in readers return the true chart values, so no model is loaded; the
real OCR+pixel reader runs. Two of the seven reports keep this test short; `scripts/real/check_samples.py` runs all."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "sample_reports" / "real_world"


@pytest.mark.skipif(not (SAMPLES / "03_tricky_language" / "expected.json").exists(),
                    reason="run scripts/real/make_sample_reports.py first")
def test_no_harmful_verdict_on_the_sample_reports(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "real" / "check_samples.py"), "--reports", "03,04",
                        "--work", str(tmp_path)], capture_output=True, text=True, cwd=ROOT, timeout=900)
    assert "0 WRONG" in r.stdout, r.stdout[-4000:] + r.stderr[-2000:]
    assert r.returncode == 0
