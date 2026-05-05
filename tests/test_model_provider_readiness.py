import json

from app.audit.model_provider_readiness import evaluate_model_provider_readiness
from app.core.config import Settings
from infra.scripts import model_provider_readiness


def test_model_provider_readiness_default_disabled_is_ok() -> None:
    report = evaluate_model_provider_readiness(Settings(_env_file=None))

    assert report["status"] == "ok"
    assert report["configuration"]["model_analysis_enabled"] is False
    assert report["configuration"]["model_provider"] == "disabled"
    assert report["summary"]["failure_count"] == 0


def test_model_provider_readiness_openai_enabled_requires_model_and_key() -> None:
    report = evaluate_model_provider_readiness(
        Settings(
            _env_file=None,
            MODEL_ANALYSIS_ENABLED=True,
            MODEL_PROVIDER="openai",
        )
    )

    assert report["status"] == "fail"
    failures = {
        check["name"]: check["detail"]
        for check in report["checks"]
        if check["status"] == "fail"
    }
    assert failures["primary model"] == (
        "MODEL_PRIMARY_MODEL is required when model analysis is enabled"
    )
    assert failures["model credentials"] == (
        "OPENAI_API_KEY is required for MODEL_PROVIDER=openai"
    )


def test_model_provider_readiness_openai_enabled_redacts_key() -> None:
    report = evaluate_model_provider_readiness(
        Settings(
            _env_file=None,
            MODEL_ANALYSIS_ENABLED=True,
            MODEL_PROVIDER="openai",
            MODEL_PRIMARY_MODEL="gpt-primary",
            OPENAI_API_KEY="sk-secret-value",
        )
    )

    serialized = json.dumps(report, ensure_ascii=False)
    assert report["status"] == "warn"
    assert report["configuration"]["credentials"]["openai_api_key_configured"] is True
    assert "sk-secret-value" not in serialized
    assert "gpt-primary" in serialized


def test_model_provider_readiness_custom_provider_rejects_embedded_credentials() -> None:
    report = evaluate_model_provider_readiness(
        Settings(
            _env_file=None,
            MODEL_ANALYSIS_ENABLED=True,
            MODEL_PROVIDER="custom",
            MODEL_PRIMARY_MODEL="custom-primary",
            MODEL_API_BASE_URL="https://user:password@models.example.test/v1",
            MODEL_API_KEY="custom-secret",
        )
    )

    assert report["status"] == "fail"
    base_url_check = next(
        check for check in report["checks"] if check["name"] == "custom model base URL"
    )
    assert base_url_check["detail"] == "MODEL_API_BASE_URL must not embed credentials"
    serialized = json.dumps(report, ensure_ascii=False)
    assert "password" not in serialized
    assert "custom-secret" not in serialized
    assert "models.example.test" in serialized


def test_model_provider_readiness_custom_provider_rejects_invalid_port() -> None:
    report = evaluate_model_provider_readiness(
        Settings(
            _env_file=None,
            MODEL_ANALYSIS_ENABLED=True,
            MODEL_PROVIDER="custom",
            MODEL_PRIMARY_MODEL="custom-primary",
            MODEL_API_BASE_URL="https://models.example.test:bad/v1",
            MODEL_API_KEY="custom-secret",
        )
    )

    assert report["status"] == "fail"
    base_url_check = next(
        check for check in report["checks"] if check["name"] == "custom model base URL"
    )
    assert base_url_check["detail"] == "MODEL_API_BASE_URL has an invalid port"
    assert base_url_check["metadata"]["port"] == "invalid"


def test_model_provider_readiness_raw_prompt_storage_warns() -> None:
    report = evaluate_model_provider_readiness(
        Settings(_env_file=None, MODEL_AUDIT_STORE_RAW_PROMPT=True)
    )

    assert report["status"] == "warn"
    raw_prompt_check = next(
        check for check in report["checks"] if check["name"] == "raw prompt storage"
    )
    assert raw_prompt_check["status"] == "warn"


def test_model_provider_readiness_cli_writes_json_and_honors_warning_exit(
    tmp_path,
    monkeypatch,
) -> None:
    output = tmp_path / "model-readiness.json"
    monkeypatch.setenv("MODEL_AUDIT_STORE_RAW_PROMPT", "true")

    exit_code = model_provider_readiness.main(["--json-output", str(output)])

    assert exit_code == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["report_type"] == "model_provider_readiness"
    assert written["status"] == "warn"

    strict_exit_code = model_provider_readiness.main(
        ["--json-output", str(output), "--fail-on-warning"]
    )

    assert strict_exit_code == 1
