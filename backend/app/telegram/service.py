from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.redis import check_redis
from app.db.session import check_database
from app.ops.service import get_ops_history, get_ops_overview, get_ops_readiness, get_ops_trends
from app.portfolio.service import list_holdings, list_watchlist_items
from app.providers.service import get_tushare_readiness
from app.providers.tushare import get_tushare_provider_status
from app.radar.service import (
    get_latest_radar_scan,
    get_radar_overview,
    get_radar_signal_analysis,
    get_radar_signal_detail,
    list_radar_signals,
)
from app.reports.schemas import PeriodicReportType
from app.reports.service import generate_periodic_report, list_reports
from app.scores.service import generate_signal_scores
from app.telegram.binding_service import is_telegram_chat_authorized
from app.telegram.client import TelegramClient
from app.telegram.formatter import (
    format_chat_identity,
    format_health,
    format_help,
    format_holdings,
    format_invalid_analysis_signal_id,
    format_invalid_score_signal_id,
    format_invalid_signal_id,
    format_no_text,
    format_ops_history,
    format_ops_overview,
    format_ops_readiness,
    format_ops_trends,
    format_ops_warning_drilldown,
    format_periodic_report,
    format_radar_overview,
    format_reports,
    format_scores,
    format_signal_analysis,
    format_signal_detail,
    format_signal_not_found,
    format_signals,
    format_tushare_readiness,
    format_tushare_status,
    format_unauthorized,
    format_unknown_command,
    format_watchlist_items,
)
from app.telegram.schemas import (
    TelegramStatusRead,
    TelegramUpdate,
    TelegramWebhookResponse,
)

SIGNALS_COMMAND_LIMIT = 10
OPS_COMMAND_LOOKBACK_HOURS = 24
OPS_TRENDS_BUCKET_COUNT = 12
OPS_WARNING_HISTORY_LIMIT = 10


def telegram_status(
    settings: Settings,
    *,
    binding_count: int = 0,
    active_binding_count: int = 0,
) -> TelegramStatusRead:
    return TelegramStatusRead(
        bot_token_configured=settings.telegram_bot_token_configured,
        allowed_chat_count=len(settings.telegram_allowed_chat_id_set),
        binding_count=binding_count,
        active_binding_count=active_binding_count,
        require_binding=settings.telegram_require_binding,
        webhook_secret_enabled=settings.telegram_webhook_secret_enabled,
        push_enabled=settings.telegram_push_enabled,
    )


class TelegramCommandService:
    def __init__(self, settings: Settings, client: TelegramClient | None = None) -> None:
        self._settings = settings
        self._client = client or TelegramClient(settings.telegram_bot_token)

    async def handle_update(
        self,
        session: AsyncSession,
        update: TelegramUpdate,
    ) -> TelegramWebhookResponse:
        message = update.message
        if message is None:
            return _preview_response(
                accepted=False,
                authorized=False,
                command=None,
                text=format_no_text(),
                delivery="skipped",
            )

        chat_id = message.chat.id
        text = message.text.strip() if message.text else ""
        command, arguments = _parse_command(text) if text else (None, [])

        if command in {"/id", "/chatid"}:
            return await self._deliver(
                chat_id=chat_id,
                command=command,
                text=format_chat_identity(chat_id),
                accepted=True,
                authorized=False,
            )

        if not await is_telegram_chat_authorized(session, self._settings, chat_id):
            return _preview_response(
                accepted=False,
                authorized=False,
                command=command,
                text=format_unauthorized(),
                delivery="skipped",
            )

        if not text:
            return await self._deliver(
                chat_id=chat_id,
                command=None,
                text=format_no_text(),
                accepted=False,
            )

        response_text = await self._command_response(session, chat_id, command, arguments)
        return await self._deliver(
            chat_id=chat_id,
            command=command,
            text=response_text,
            accepted=True,
        )

    async def _command_response(
        self,
        session: AsyncSession,
        chat_id: int,
        command: str,
        arguments: list[str],
    ) -> str:
        try:
            if command in {"/start", "/help"}:
                return format_help()

            if command == "/health":
                latest_scan = await get_latest_radar_scan(session)
                return format_health(
                    {
                        "database": await check_database(),
                        "redis": await check_redis(),
                    },
                    latest_scan=latest_scan,
                )

            if command == "/ops":
                overview = await get_ops_overview(
                    session,
                    lookback_hours=OPS_COMMAND_LOOKBACK_HOURS,
                )
                return format_ops_overview(overview)

            if command == "/ops_history":
                history = await get_ops_history(
                    session,
                    lookback_hours=OPS_COMMAND_LOOKBACK_HOURS,
                    limit=OPS_WARNING_HISTORY_LIMIT,
                )
                return format_ops_history(history)

            if command == "/ops_trends":
                trends = await get_ops_trends(
                    session,
                    lookback_hours=OPS_COMMAND_LOOKBACK_HOURS,
                    bucket_count=OPS_TRENDS_BUCKET_COUNT,
                )
                return format_ops_trends(trends)

            if command == "/ops_ready":
                readiness = await get_ops_readiness(
                    session,
                    lookback_hours=OPS_COMMAND_LOOKBACK_HOURS,
                )
                return format_ops_readiness(readiness)

            if command == "/ops_warn":
                readiness = await get_ops_readiness(
                    session,
                    lookback_hours=OPS_COMMAND_LOOKBACK_HOURS,
                )
                overview = await get_ops_overview(
                    session,
                    lookback_hours=OPS_COMMAND_LOOKBACK_HOURS,
                )
                history = await get_ops_history(
                    session,
                    lookback_hours=OPS_COMMAND_LOOKBACK_HOURS,
                    limit=OPS_WARNING_HISTORY_LIMIT,
                )
                return format_ops_warning_drilldown(
                    readiness=readiness,
                    overview=overview,
                    history=history,
                )

            if command == "/tushare":
                return format_tushare_status(get_tushare_provider_status(self._settings))

            if command == "/tushare_ready":
                readiness = await get_tushare_readiness(session, settings=self._settings)
                return format_tushare_readiness(readiness)

            if command == "/radar":
                overview = await get_radar_overview(session, limit=50)
                return format_radar_overview(overview)

            if command == "/signals":
                signals = await list_radar_signals(session, limit=SIGNALS_COMMAND_LIMIT)
                return format_signals(signals)

            if command == "/signal":
                return await self._signal_detail_response(session, arguments)

            if command == "/analysis":
                return await self._signal_analysis_response(session, arguments)

            if command in {"/holding", "/holdings"}:
                holdings = await list_holdings(session, user_key=_telegram_user_key(chat_id))
                return format_holdings(holdings)

            if command == "/watchlist":
                items = await list_watchlist_items(session, user_key=_telegram_user_key(chat_id))
                return format_watchlist_items(items)

            if command == "/reports":
                reports = await list_reports(session, user_key=_telegram_user_key(chat_id))
                return format_reports(reports)

            if command == "/daily":
                report = await generate_periodic_report(
                    session,
                    report_type=PeriodicReportType.DAILY,
                    user_key=_telegram_user_key(chat_id),
                )
                return format_periodic_report(report)

            if command == "/weekly":
                report = await generate_periodic_report(
                    session,
                    report_type=PeriodicReportType.WEEKLY,
                    user_key=_telegram_user_key(chat_id),
                )
                return format_periodic_report(report)

            if command == "/score":
                return await self._score_response(session, arguments)
        except SQLAlchemyError:
            return "数据库暂不可用，稍后再观察和复盘。"

        return format_unknown_command()

    async def _signal_detail_response(
        self,
        session: AsyncSession,
        arguments: list[str],
    ) -> str:
        if not arguments:
            return format_invalid_signal_id()

        try:
            signal_id = int(arguments[0])
        except ValueError:
            return format_invalid_signal_id()

        signal = await get_radar_signal_detail(session, signal_id)
        if signal is None:
            return format_signal_not_found(signal_id)

        return format_signal_detail(signal)

    async def _signal_analysis_response(
        self,
        session: AsyncSession,
        arguments: list[str],
    ) -> str:
        if not arguments:
            return format_invalid_analysis_signal_id()

        try:
            signal_id = int(arguments[0])
        except ValueError:
            return format_invalid_analysis_signal_id()

        analysis = await get_radar_signal_analysis(session, signal_id)
        if analysis is None:
            return format_signal_not_found(signal_id)

        return format_signal_analysis(analysis)

    async def _score_response(
        self,
        session: AsyncSession,
        arguments: list[str],
    ) -> str:
        if not arguments:
            return format_invalid_score_signal_id()

        try:
            signal_id = int(arguments[0])
        except ValueError:
            return format_invalid_score_signal_id()

        score_run = await generate_signal_scores(session, signal_id)
        if score_run is None:
            return format_signal_not_found(signal_id)

        return format_scores(score_run)

    async def _deliver(
        self,
        chat_id: int,
        command: str | None,
        text: str,
        accepted: bool,
        authorized: bool = True,
    ) -> TelegramWebhookResponse:
        if not self._client.configured:
            return _preview_response(
                accepted=accepted,
                authorized=authorized,
                command=command,
                text=text,
                delivery="preview",
            )

        send_result = await self._client.send_message(chat_id, text)
        if send_result.ok:
            return TelegramWebhookResponse(
                accepted=accepted,
                authorized=authorized,
                command=command,
                delivery="sent",
                sent=True,
                preview=text,
            )

        return TelegramWebhookResponse(
            accepted=accepted,
            authorized=authorized,
            command=command,
            delivery="failed",
            sent=False,
            preview=text,
            error=send_result.error,
        )


def _parse_command(text: str) -> tuple[str, list[str]]:
    parts = text.split()
    command = parts[0].split("@", maxsplit=1)[0].lower()
    return command, parts[1:]


def _telegram_user_key(chat_id: int) -> str:
    return f"telegram-{chat_id}"


def _preview_response(
    accepted: bool,
    authorized: bool,
    command: str | None,
    text: str,
    delivery: str,
) -> TelegramWebhookResponse:
    return TelegramWebhookResponse(
        accepted=accepted,
        authorized=authorized,
        command=command,
        delivery=delivery,
        sent=False,
        preview=text,
    )
