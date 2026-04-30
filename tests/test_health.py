from fastapi.testclient import TestClient

from app.main import create_app


def test_app_can_be_created() -> None:
    app = create_app()

    assert app.title == "BaizeFinDB"


def test_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_endpoint_reports_ready(monkeypatch) -> None:
    async def ok_check() -> dict[str, str]:
        return {"status": "ok"}

    monkeypatch.setattr("app.api.routes.health.check_database", ok_check)
    monkeypatch.setattr("app.api.routes.health.check_redis", ok_check)

    client = TestClient(create_app())
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_endpoint_reports_dependency_failure(monkeypatch) -> None:
    async def db_down() -> dict[str, str]:
        return {"status": "down", "error": "ConnectionError"}

    async def redis_ok() -> dict[str, str]:
        return {"status": "ok"}

    monkeypatch.setattr("app.api.routes.health.check_database", db_down)
    monkeypatch.setattr("app.api.routes.health.check_redis", redis_ok)

    client = TestClient(create_app())
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
