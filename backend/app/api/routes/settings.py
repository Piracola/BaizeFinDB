import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import Settings, get_settings
from app.settings.schemas import (
    EditableSettingsRead,
    EditableSettingsSaveResult,
    EditableSettingsUpdate,
    SettingsConnectionTestRequest,
    SettingsConnectionTestResult,
    SettingsStatusRead,
)
from app.settings.service import (
    build_editable_settings,
    build_settings_status,
    run_settings_connection_test,
    save_editable_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/status", response_model=SettingsStatusRead)
async def settings_status() -> SettingsStatusRead:
    return build_settings_status(get_settings())


@router.get("/editable", response_model=EditableSettingsRead)
async def settings_editable() -> EditableSettingsRead:
    return build_editable_settings(get_settings())


@router.put("/editable", response_model=EditableSettingsSaveResult)
async def update_settings_editable(
    payload: EditableSettingsUpdate,
    request: Request,
    settings_token: str | None = Header(
        default=None,
        alias="X-BaizeFinDB-Settings-Token",
    ),
) -> EditableSettingsSaveResult:
    settings = get_settings()
    _authorize_settings_write(request, settings, settings_token)
    try:
        return save_editable_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/connection-test", response_model=SettingsConnectionTestResult)
async def settings_connection_test(
    payload: SettingsConnectionTestRequest,
    request: Request,
    settings_token: str | None = Header(
        default=None,
        alias="X-BaizeFinDB-Settings-Token",
    ),
) -> SettingsConnectionTestResult:
    settings = get_settings()
    _authorize_settings_write(request, settings, settings_token)
    return await run_settings_connection_test(payload, settings=settings)


def _authorize_settings_write(
    request: Request,
    settings: Settings,
    settings_token: str | None,
) -> None:
    expected_token = settings.settings_admin_token
    if expected_token and expected_token.strip():
        if settings_token and hmac.compare_digest(settings_token, expected_token.strip()):
            return
        raise HTTPException(
            status_code=403,
            detail="Settings admin token is required to write local configuration.",
        )

    client_host = request.client.host if request.client else ""
    if client_host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return

    raise HTTPException(
        status_code=403,
        detail=(
            "Settings writes without SETTINGS_ADMIN_TOKEN are allowed only from "
            "localhost."
        ),
    )
