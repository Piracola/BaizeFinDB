import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from app.providers.tushare import TUSHARE_ENDPOINTS, normalize_dataframe

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "infra" / "scripts" / "verify_tushare_announcements.py"
SPEC = importlib.util.spec_from_file_location("verify_tushare_announcements", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
verify_tushare_announcements = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify_tushare_announcements
SPEC.loader.exec_module(verify_tushare_announcements)


def _announcements_dataset():
    return normalize_dataframe(
        pd.DataFrame(
            [
                {
                    "ann_date": "20260503",
                    "ts_code": "600000.SH",
                    "name": "浦发银行",
                    "title": "董事会决议公告",
                    "url": "https://example.test/notice.pdf?token=secret-token",
                    "rec_time": "2026-05-03 20:00:00",
                }
            ]
        ),
        TUSHARE_ENDPOINTS["anns_d"],
    )


class FakeTushareProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    async def fetch(self, endpoint: str, query_params: dict[str, object] | None = None):
        self.calls.append((endpoint, query_params))
        return _announcements_dataset()


class FailingTushareProvider:
    async def fetch(self, endpoint: str, query_params: dict[str, object] | None = None):
        raise RuntimeError(
            "TUSHARE_TOKEN secret-token rejected by https://api.example.test/pro"
        )


def test_success_report_redacts_url_and_keeps_field_summary(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    dataset = _announcements_dataset()

    report = verify_tushare_announcements.build_success_report(
        dataset=dataset,
        ann_date="20260503",
        max_sample_rows=1,
    )
    output_path = tmp_path / "evidence" / "tushare-anns.json"
    verify_tushare_announcements.write_json_report(output_path, report)
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert payload["status"] == "success"
    assert payload["endpoint"] == "anns_d"
    assert payload["ann_date"] == "20260503"
    assert payload["row_count"] == 1
    assert payload["quality_status"] == "ok"
    assert payload["required_fields"] == ["ann_date", "ts_code", "title"]
    assert payload["missing_fields"] == []
    assert payload["field_presence"] == {
        "ann_date": True,
        "ts_code": True,
        "title": True,
    }
    assert payload["sample"] == [
        {
            "ann_date": "20260503",
            "ts_code": "600000.SH",
            "name": "浦发银行",
            "title": "董事会决议公告",
            "rec_time": "2026-05-03 20:00:00",
        }
    ]
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "example.test" not in encoded
    assert "notice.pdf" not in encoded
    assert "url" not in payload["sample"][0]


async def test_cli_writes_success_report_from_mocked_provider(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    monkeypatch.setattr(verify_tushare_announcements, "TushareProvider", FakeTushareProvider)
    output_path = tmp_path / "cli-success.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_tushare_announcements.py",
            "--ann-date",
            "20260503",
            "--json-output",
            str(output_path),
            "--max-sample-rows",
            "1",
        ],
    )

    await verify_tushare_announcements.main()
    captured = capsys.readouterr()
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert json.loads(captured.out)["status"] == "success"
    assert payload["status"] == "success"
    assert payload["row_count"] == 1
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "example.test" not in encoded
    assert "url" not in payload["sample"][0]


def test_failure_report_redacts_token_url_and_domain(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    exc = RuntimeError(
        "TUSHARE_TOKEN secret-token rejected by https://api.example.test/pro for example.test"
    )

    report = verify_tushare_announcements.build_failure_report(
        exc=exc,
        ann_date="20260503",
    )
    output_path = tmp_path / "failed.json"
    verify_tushare_announcements.write_json_report(output_path, report)
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert payload["status"] == "failure"
    assert payload["endpoint"] == "anns_d"
    assert payload["ann_date"] == "20260503"
    assert payload["row_count"] == 0
    assert payload["quality_status"] == "failed"
    assert payload["required_fields"] == ["ann_date", "ts_code", "title"]
    assert payload["missing_fields"] == ["ann_date", "ts_code", "title"]
    assert payload["sample"] == []
    assert "RuntimeError" in payload["error"]
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "api.example.test" not in encoded
    assert "example.test" not in encoded


async def test_cli_writes_failure_report_from_mocked_provider(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    monkeypatch.setattr(verify_tushare_announcements, "TushareProvider", FailingTushareProvider)
    output_path = tmp_path / "cli-failure.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_tushare_announcements.py",
            "--ann-date",
            "20260503",
            "--json-output",
            str(output_path),
        ],
    )

    await verify_tushare_announcements.main()
    captured = capsys.readouterr()
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert json.loads(captured.out)["status"] == "failure"
    assert payload["status"] == "failure"
    assert payload["quality_status"] == "failed"
    assert "RuntimeError" in payload["error"]
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "api.example.test" not in encoded
