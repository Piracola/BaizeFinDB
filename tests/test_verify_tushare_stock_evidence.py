import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from app.providers.tushare import TUSHARE_ENDPOINTS, normalize_dataframe

ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_script(module_name: str, relative_path: str):
    script_path = ROOT_DIR / relative_path
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify_tushare_stock_basic = _load_script(
    "verify_tushare_stock_basic",
    "infra/scripts/verify_tushare_stock_basic.py",
)
verify_tushare_stock_company = _load_script(
    "verify_tushare_stock_company",
    "infra/scripts/verify_tushare_stock_company.py",
)


def _stock_basic_dataset():
    return normalize_dataframe(
        pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "平安银行 token=secret-token https://example.test/leak",
                    "area": "深圳",
                    "industry": "银行",
                    "market": "主板",
                    "exchange": "SZSE",
                    "list_status": "L",
                    "list_date": "19910403",
                    "is_hs": "S",
                    "source_url": "https://example.test/raw",
                    "access_token": "secret-token",
                }
            ]
        ),
        TUSHARE_ENDPOINTS["stock_basic"],
    )


def _stock_company_dataset():
    return normalize_dataframe(
        pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "exchange": "SZSE",
                    "chairman": "张三",
                    "manager": "李四",
                    "secretary": "secret-token",
                    "reg_capital": 100000,
                    "setup_date": "19871222",
                    "province": "广东",
                    "city": "深圳",
                    "website": "https://example.test/company?token=secret-token",
                    "email": "ir@example.test",
                    "office": "深圳",
                    "employees": 10000,
                    "main_business": "银行业务 token=secret-token",
                    "business_scope": "金融服务",
                }
            ]
        ),
        TUSHARE_ENDPOINTS["stock_company"],
    )


class FakeStockBasicProvider:
    async def fetch(self, endpoint: str, query_params: dict[str, object] | None = None):
        assert endpoint == "stock_basic"
        assert query_params is None
        return _stock_basic_dataset()


class FailingStockBasicProvider:
    async def fetch(self, endpoint: str, query_params: dict[str, object] | None = None):
        raise RuntimeError(
            "TUSHARE_TOKEN secret-token rejected by https://api.example.test/pro"
        )


class FakeStockCompanyProvider:
    async def fetch(self, endpoint: str, query_params: dict[str, object] | None = None):
        assert endpoint == "stock_company"
        assert query_params == {"exchange": "SZSE"}
        return _stock_company_dataset()


class FailingStockCompanyProvider:
    async def fetch(self, endpoint: str, query_params: dict[str, object] | None = None):
        raise RuntimeError(
            "authorization=secret-token rejected by https://api.example.test/pro"
        )


async def test_stock_basic_cli_writes_sanitized_success_report(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    monkeypatch.setattr(verify_tushare_stock_basic, "TushareProvider", FakeStockBasicProvider)
    output_path = tmp_path / "stock-basic.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_tushare_stock_basic.py",
            "--json-output",
            str(output_path),
            "--max-sample-rows",
            "1",
        ],
    )

    await verify_tushare_stock_basic.main()
    captured = capsys.readouterr()
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert json.loads(captured.out)["status"] == "success"
    assert payload["endpoint"] == "stock_basic"
    assert payload["query_params"] == {}
    assert payload["row_count"] == 1
    assert payload["quality_status"] == "ok"
    assert payload["required_fields"] == ["ts_code", "symbol", "name", "market", "list_date"]
    assert payload["missing_fields"] == []
    assert payload["field_presence"] == {
        "ts_code": True,
        "symbol": True,
        "name": True,
        "market": True,
        "list_date": True,
    }
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "example.test" not in encoded
    assert "source_url" not in payload["sample"][0]
    assert "access_token" not in payload["sample"][0]


async def test_stock_basic_success_report_bounds_nested_sample_values(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    dataset = _stock_basic_dataset()
    dataset.normalized_rows[0]["name"] = "长文本 " * 250
    dataset.normalized_rows[0]["metadata"] = {
        "source_url": "https://example.test/raw",
        "safe_note": "备注 " * 250,
        "token": "secret-token",
    }
    dataset.normalized_rows[0]["tags"] = ["标签 " * 250 for _ in range(12)]

    report = verify_tushare_stock_basic.build_success_report(
        endpoint="stock_basic",
        dataset=dataset,
        query_params={},
        max_sample_rows=1,
    )
    output_path = tmp_path / "bounded.json"
    verify_tushare_stock_basic.write_json_report(output_path, report)
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)
    sample = payload["sample"][0]

    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "example.test" not in encoded
    assert sample["name"].endswith("...<truncated>")
    assert len(sample["name"]) < 300
    assert "source_url" not in sample["metadata"]
    assert "token" not in sample["metadata"]
    assert sample["metadata"]["safe_note"].endswith("...<truncated>")
    assert len(sample["tags"]) == 11
    assert sample["tags"][-1] == "<truncated>"


async def test_stock_basic_default_output_keeps_legacy_shape_and_sanitizes(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    monkeypatch.setattr(verify_tushare_stock_basic, "TushareProvider", FakeStockBasicProvider)
    monkeypatch.setattr(sys, "argv", ["verify_tushare_stock_basic.py"])

    await verify_tushare_stock_basic.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert set(payload) == {"endpoint", "status", "row_count", "quality", "sample"}
    assert payload["endpoint"] == "stock_basic"
    assert payload["status"] == "success"
    assert payload["row_count"] == 1
    assert "secret-token" not in captured.out
    assert "https://" not in captured.out
    assert "example.test" not in captured.out


async def test_stock_basic_cli_writes_sanitized_failure_report(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    monkeypatch.setattr(verify_tushare_stock_basic, "TushareProvider", FailingStockBasicProvider)
    output_path = tmp_path / "stock-basic-failure.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_tushare_stock_basic.py",
            "--json-output",
            str(output_path),
        ],
    )

    await verify_tushare_stock_basic.main()
    captured = capsys.readouterr()
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert json.loads(captured.out)["status"] == "failure"
    assert payload["status"] == "failure"
    assert payload["quality_status"] == "failed"
    assert payload["query_params"] == {}
    assert "RuntimeError" in payload["error"]
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "api.example.test" not in encoded


async def test_stock_company_cli_writes_sanitized_success_report(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    monkeypatch.setattr(verify_tushare_stock_company, "TushareProvider", FakeStockCompanyProvider)
    output_path = tmp_path / "stock-company.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_tushare_stock_company.py",
            "--exchange",
            "SZSE",
            "--json-output",
            str(output_path),
            "--max-sample-rows",
            "1",
        ],
    )

    await verify_tushare_stock_company.main()
    captured = capsys.readouterr()
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert json.loads(captured.out)["status"] == "success"
    assert payload["endpoint"] == "stock_company"
    assert payload["exchange"] == "SZSE"
    assert payload["query_params"] == {"exchange": "SZSE"}
    assert payload["row_count"] == 1
    assert payload["quality_status"] == "ok"
    assert payload["required_fields"] == ["ts_code", "chairman", "manager", "main_business"]
    assert payload["missing_fields"] == []
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "example.test" not in encoded
    assert "website" not in payload["sample"][0]
    assert payload["sample"][0]["secretary"] == "<redacted>"


async def test_stock_company_default_output_keeps_legacy_shape_and_sanitizes(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    monkeypatch.setattr(verify_tushare_stock_company, "TushareProvider", FakeStockCompanyProvider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_tushare_stock_company.py",
            "--exchange",
            "SZSE",
        ],
    )

    await verify_tushare_stock_company.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert set(payload) == {"endpoint", "status", "exchange", "row_count", "quality", "sample"}
    assert payload["endpoint"] == "stock_company"
    assert payload["exchange"] == "SZSE"
    assert payload["status"] == "success"
    assert payload["row_count"] == 1
    assert "secret-token" not in captured.out
    assert "https://" not in captured.out
    assert "example.test" not in captured.out


async def test_stock_company_cli_writes_sanitized_failure_report(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-token")
    monkeypatch.setattr(
        verify_tushare_stock_company,
        "TushareProvider",
        FailingStockCompanyProvider,
    )
    output_path = tmp_path / "stock-company-failure.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_tushare_stock_company.py",
            "--exchange",
            "SZSE",
            "--json-output",
            str(output_path),
        ],
    )

    await verify_tushare_stock_company.main()
    captured = capsys.readouterr()
    encoded = output_path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert json.loads(captured.out)["status"] == "failure"
    assert payload["status"] == "failure"
    assert payload["quality_status"] == "failed"
    assert payload["query_params"] == {"exchange": "SZSE"}
    assert payload["exchange"] == "SZSE"
    assert "RuntimeError" in payload["error"]
    assert "secret-token" not in encoded
    assert "https://" not in encoded
    assert "api.example.test" not in encoded
