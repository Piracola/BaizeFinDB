from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.push_models import PushLog
from app.governance.review import review_radar_signal
from app.portfolio.service import get_or_create_user
from app.radar.schemas import RadarPriority, RadarReviewStatus, RadarSignalRead
from app.radar.service import get_latest_radar_scan
from app.reports.schemas import CreatableReportType
from app.reports.service import ReportBlockedError, ensure_signal_report
from app.telegram.binding_service import resolve_telegram_recipients
from app.telegram.client import TelegramClient
from app.telegram.formatter import format_radar_push
from app.telegram.schemas import (
    TelegramPushDeliveryRead,
    TelegramPushLogRead,
    TelegramPushRunRead,
    TelegramPushStatus,
)

TELEGRAM_PUSH_CHANNEL = "telegram"
RADAR_SCAN_SOURCE_KIND = "radar_scan"
PUSH_TITLE = "雷达折叠推送"
P0_STANDARD_REPORT_TRIGGER = "telegram_p0_push"


async def send_latest_radar_push(
    session: AsyncSession,
    settings: Settings,
    client: TelegramClient | None = None,
    chat_ids: list[int] | None = None,
    dry_run: bool = False,
    respect_enabled: bool = True,
) -> TelegramPushRunRead:
    push_enabled = settings.telegram_push_enabled
    if respect_enabled and not push_enabled and not dry_run:
        return _empty_push_result(push_enabled=push_enabled, dry_run=dry_run)

    recipients = await resolve_telegram_recipients(session, settings, chat_ids)
    if not recipients and not dry_run:
        return _empty_push_result(push_enabled=push_enabled, dry_run=dry_run)

    scan = await get_latest_radar_scan(session)
    if scan is None:
        return _empty_push_result(
            push_enabled=push_enabled,
            dry_run=dry_run,
            recipient_count=len(recipients),
        )

    reviewed_signals, blocked_signal_ids, needs_human_review_signal_ids = await _review_signals(
        session,
        scan.signals,
    )
    included_signals = _included_push_signals(reviewed_signals, dry_run=dry_run)
    included_signal_ids = [signal.id for signal in included_signals]
    priority_counts = _priority_counts(included_signals)

    if not recipients or (not included_signals and not dry_run):
        return TelegramPushRunRead(
            source_scan_id=scan.id,
            push_enabled=push_enabled,
            dry_run=dry_run,
            recipient_count=len(recipients),
            included_signal_ids=included_signal_ids,
            blocked_signal_ids=blocked_signal_ids,
            needs_human_review_signal_ids=needs_human_review_signal_ids,
            priority_counts=priority_counts,
            deliveries=[],
        )

    message = format_radar_push(
        scan_id=scan.id,
        signals=included_signals,
        blocked_signal_ids=blocked_signal_ids,
        needs_human_review_signal_ids=needs_human_review_signal_ids,
        priority_counts=priority_counts,
    )
    telegram_client = client or TelegramClient(settings.telegram_bot_token)
    deliveries: list[TelegramPushDeliveryRead] = []

    for chat_id in recipients:
        user_key = _telegram_user_key(chat_id)
        user = await get_or_create_user(session, user_key)

        duplicate_log = None
        if not dry_run:
            duplicate_log = await _existing_successful_push_log(
                session=session,
                user_id=user.id,
                chat_id=chat_id,
                scan_id=scan.id,
            )

        if duplicate_log is not None:
            deliveries.append(
                TelegramPushDeliveryRead(
                    chat_id=chat_id,
                    user_key=user_key,
                    delivery=TelegramPushStatus.SKIPPED,
                    sent=False,
                    preview=duplicate_log.message_text,
                    push_log_id=duplicate_log.id,
                    error="duplicate_radar_scan_push",
                ),
            )
            continue

        if dry_run:
            deliveries.append(
                TelegramPushDeliveryRead(
                    chat_id=chat_id,
                    user_key=user_key,
                    delivery=TelegramPushStatus.PREVIEW,
                    sent=False,
                    preview=message,
                ),
            )
            continue

        if telegram_client.configured:
            send_result = await telegram_client.send_message(chat_id, message)
            status = TelegramPushStatus.SENT if send_result.ok else TelegramPushStatus.FAILED
            error = send_result.error
            sent = send_result.ok
            delivery_details = {
                "telegram_status_code": send_result.status_code,
                "error": send_result.error,
            }
        else:
            status = TelegramPushStatus.PREVIEW
            error = None
            sent = False
            delivery_details = {"mode": "preview", "reason": "bot token is not configured"}

        push_log = PushLog(
            user_id=user.id,
            channel=TELEGRAM_PUSH_CHANNEL,
            target_ref=str(chat_id),
            source_kind=RADAR_SCAN_SOURCE_KIND,
            source_id=scan.id,
            status=status.value,
            title=PUSH_TITLE,
            message_text=message,
            included_signal_ids=included_signal_ids,
            blocked_signal_ids=blocked_signal_ids,
            needs_human_review_signal_ids=needs_human_review_signal_ids,
            delivery_details=delivery_details,
        )
        session.add(push_log)
        await session.flush()
        generated_report_ids = await _ensure_p0_standard_reports(
            session=session,
            user_key=user_key,
            signals=included_signals,
            delivery_status=status,
        )
        deliveries.append(
            TelegramPushDeliveryRead(
                chat_id=chat_id,
                user_key=user_key,
                delivery=status,
                sent=sent,
                preview=message,
                push_log_id=push_log.id,
                generated_report_ids=generated_report_ids,
                error=error,
            ),
        )

    await session.commit()
    return TelegramPushRunRead(
        source_scan_id=scan.id,
        push_enabled=push_enabled,
        dry_run=dry_run,
        recipient_count=len(recipients),
        included_signal_ids=included_signal_ids,
        blocked_signal_ids=blocked_signal_ids,
        needs_human_review_signal_ids=needs_human_review_signal_ids,
        priority_counts=priority_counts,
        deliveries=deliveries,
    )


async def list_telegram_push_logs(
    session: AsyncSession,
    user_key: str,
    limit: int = 50,
) -> list[TelegramPushLogRead]:
    user = await get_or_create_user(session, user_key)
    statement = (
        select(PushLog)
        .where(
            PushLog.user_id == user.id,
            PushLog.channel == TELEGRAM_PUSH_CHANNEL,
        )
        .order_by(desc(PushLog.created_at), desc(PushLog.id))
        .limit(limit)
    )
    logs = (await session.scalars(statement)).all()
    return [_push_log_read(log, user.user_key) for log in logs]


async def _review_signals(
    session: AsyncSession,
    signals: list[RadarSignalRead],
) -> tuple[list[RadarSignalRead], list[int], list[int]]:
    reviewed_signals: list[RadarSignalRead] = []
    blocked_signal_ids: list[int] = []
    needs_human_review_signal_ids: list[int] = []

    for signal in signals:
        review = await review_radar_signal(session, signal.id)
        if review is None:
            continue

        if review.review_status == RadarReviewStatus.BLOCKED:
            blocked_signal_ids.append(signal.id)
            continue

        if review.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW:
            needs_human_review_signal_ids.append(signal.id)

        reviewed_signals.append(signal.model_copy(update={"review_status": review.review_status}))

    return reviewed_signals, blocked_signal_ids, needs_human_review_signal_ids


def _included_push_signals(
    reviewed_signals: list[RadarSignalRead],
    dry_run: bool,
) -> list[RadarSignalRead]:
    attention_signals = [
        signal
        for signal in reviewed_signals
        if signal.priority in {RadarPriority.P0, RadarPriority.P1}
        or signal.review_status == RadarReviewStatus.NEEDS_HUMAN_REVIEW
    ]
    if attention_signals or dry_run:
        return reviewed_signals

    return []


async def _existing_successful_push_log(
    session: AsyncSession,
    user_id: int,
    chat_id: int,
    scan_id: int,
) -> PushLog | None:
    statement = (
        select(PushLog)
        .where(
            PushLog.user_id == user_id,
            PushLog.channel == TELEGRAM_PUSH_CHANNEL,
            PushLog.target_ref == str(chat_id),
            PushLog.source_kind == RADAR_SCAN_SOURCE_KIND,
            PushLog.source_id == scan_id,
            PushLog.status.in_(
                [TelegramPushStatus.SENT.value, TelegramPushStatus.PREVIEW.value],
            ),
        )
        .order_by(desc(PushLog.created_at), desc(PushLog.id))
        .limit(1)
    )
    return await session.scalar(statement)


def _priority_counts(signals: list[RadarSignalRead]) -> dict[str, int]:
    counts = {priority.value: 0 for priority in RadarPriority}
    for signal in signals:
        counts[signal.priority.value] += 1
    return counts


async def _ensure_p0_standard_reports(
    session: AsyncSession,
    user_key: str,
    signals: list[RadarSignalRead],
    delivery_status: TelegramPushStatus,
) -> list[int]:
    if delivery_status not in {TelegramPushStatus.SENT, TelegramPushStatus.PREVIEW}:
        return []

    report_ids: list[int] = []
    for signal in signals:
        if signal.priority != RadarPriority.P0:
            continue

        try:
            report = await ensure_signal_report(
                session=session,
                signal_id=signal.id,
                report_type=CreatableReportType.STANDARD,
                user_key=user_key,
                details_update={"generation_trigger": P0_STANDARD_REPORT_TRIGGER},
                commit=False,
            )
        except ReportBlockedError:
            continue

        if report is not None:
            report_ids.append(report.id)

    return report_ids


def _push_log_read(log: PushLog, user_key: str) -> TelegramPushLogRead:
    try:
        chat_id = int(log.target_ref)
    except ValueError:
        chat_id = None

    return TelegramPushLogRead(
        id=log.id,
        user_key=user_key,
        channel=log.channel,
        chat_id=chat_id,
        source_kind=log.source_kind,
        source_id=log.source_id,
        status=log.status,
        title=log.title,
        message_text=log.message_text,
        included_signal_ids=log.included_signal_ids,
        blocked_signal_ids=log.blocked_signal_ids,
        needs_human_review_signal_ids=log.needs_human_review_signal_ids,
        delivery_details=log.delivery_details,
        created_at=log.created_at,
    )


def _empty_push_result(
    push_enabled: bool,
    dry_run: bool,
    recipient_count: int = 0,
) -> TelegramPushRunRead:
    return TelegramPushRunRead(
        push_enabled=push_enabled,
        dry_run=dry_run,
        recipient_count=recipient_count,
        included_signal_ids=[],
        blocked_signal_ids=[],
        needs_human_review_signal_ids=[],
        priority_counts={priority.value: 0 for priority in RadarPriority},
        deliveries=[],
    )


def _telegram_user_key(chat_id: int) -> str:
    return f"telegram-{chat_id}"
