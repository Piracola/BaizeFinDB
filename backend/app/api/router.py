from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.providers import router as providers_router
from app.api.routes.radar import router as radar_router
from app.api.routes.reports import router as reports_router
from app.api.routes.telegram import router as telegram_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(portfolio_router)
api_router.include_router(providers_router)
api_router.include_router(radar_router)
api_router.include_router(reports_router)
api_router.include_router(telegram_router)
