import json
from pathlib import Path

from app.radar.rules import classify_sector_movement

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_radar_sector_rule_golden_cases() -> None:
    case_path = ROOT_DIR / "golden_cases" / "radar_m3_2_sector_rules.json"
    cases = json.loads(case_path.read_text(encoding="utf-8"))

    for case in cases:
        result = classify_sector_movement(case["metrics"])

        assert result is not None, case["name"]
        assert result.priority == case["expected_priority"], case["name"]
        assert result.lifecycle_stage == case["expected_lifecycle_stage"], case["name"]
