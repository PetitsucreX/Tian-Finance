from __future__ import annotations

import json
import shutil
from pathlib import Path

from vat_ca3.run import run_pipeline


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "2026-01"


def copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def test_jan_2026_regression_values(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)

    result = run_pipeline(period="2026-01", root=str(root), confirm=True)

    assert result["success"] is True

    result_json = root / "Bilan 2026" / "TVA_Codex" / "2026-01" / "output" / "ca3_workflow" / "ca3_result.json"
    payload = json.loads(result_json.read_text(encoding="utf-8"))

    assert payload["rounded"]["line08_base"] == 20900
    assert payload["rounded"]["line08_tax"] == 4180
    assert payload["rounded"]["line20"] == 161
    assert payload["rounded"]["line22"] == 521
    assert payload["rounded"]["line32"] == 3498


def test_exception_stop_on_1n_mismatch(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    matches = root / "Bilan 2026" / "TVA_Codex" / "2026-01" / "input" / "sales_1n_matches.csv"
    bad = matches.read_text(encoding="utf-8").replace("8360.00,6966.67,1393.33", "8000.00,6666.67,1333.33", 1)
    matches.write_text(bad, encoding="utf-8")

    result = run_pipeline(period="2026-01", root=str(root), confirm=True)

    assert result["success"] is False
    assert result["reason"] == "exception_stop"

    mapping_md = root / "Bilan 2026" / "TVA_Codex" / "2026-01" / "output" / "ca3_workflow" / "ca3_mapping.md"
    assert not mapping_md.exists()

    exceptions_csv = root / "Bilan 2026" / "TVA_Codex" / "2026-01" / "output" / "ca3_workflow" / "exceptions.csv"
    content = exceptions_csv.read_text(encoding="utf-8")
    assert "MATCH_SUM_MISMATCH" in content
