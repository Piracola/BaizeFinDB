from fastapi import APIRouter

from app.core.config import get_settings
from app.settings.schemas import SettingsStatusRead
from app.settings.service import build_settings_status

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/status", response_model=SettingsStatusRead)
async def settings_status() -> SettingsStatusRead:
    return build_settings_status(get_settings())
