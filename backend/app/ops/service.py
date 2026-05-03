from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.audit_models import ModelCallLog
from app.db.provider_models import DataQualityCheck, ProviderFetchLog
from app.db.push_models import PushLog
from app.db.radar_models import RadarScanBatch
from app.ops.schemas import OpsAlertRead, OpsCountSummary, OpsOverviewRead, OpsRadarSummary

RADAR_STALE_INTERVAL_MULTIPLIER = 2
RADAR_FAILURE_RATE_ALERT_THRESHOLD = 0.2


async def get_ops_overview(
    session: AsyncSession,
    *,
    lookback_hours: int = 24,
    now: datetime | None = None,
) -> OpsOverviewRead:
    generated_at = _as_utc(now or datetime.now(UTC))
    since = generated_at - timedelta(hours=lookback_hours)
    settings = get_settings()
    radar = await _radar_summary(
        session,
        since=since,
        now=generated_at,
        scan_interval_seconds=settings.radar_scan_interval_seconds,
    )
    provider_fetch = await _status_summary(
        session,
        ProviderFetchLog,
        ProviderFetchLog.status,
        ProviderFetchLog.fetch_finished_at,
        since,
        healthy_statuses={"success"},
    )
    data_quality = await _status_summary(
        session,
        DataQualityCheck,
        DataQualityCheck.status,
        DataQualityCheck.created_at,
        since,
        healthy_statuses={"ok"},
    )
    telegram_push = await _status_summary(
        session,
        PushLog,
        PushLog.status,
        PushLog.created_at,
        since,
        healthy_statuses={"sent", "preview", "skipped"},
    )
    model_calls = await _status_summary(
        session,
        ModelCallLog,
        ModelCallLog.status,
        ModelCallLog.created_at,
        since,
        healthy_statuses={"success"},
    )

    return OpsOverviewRead(
        generated_at=generated_at,
        lookback_hours=lookback_hours,
        radar=radar,
        provider_fetch=provider_fetch,
        data_quality=data_quality,
        telegram_push=telegram_push,
        model_calls=model_calls,
        alerts=_ops_alerts(
            radar=radar,
            provider_fetch=provider_fetch,
            data_quality=data_quality,
            telegram_push=telegram_push,
            model_calls=model_calls,
        ),
    )


async def _radar_summary(
    session: AsyncSession,
    *,
    since: datetime,
    now: datetime,
    scan_interval_seconds: int,
) -> OpsRadarSummary:
    latest_scan = await session.scalar(
        select(RadarScanBatch)
        .order_by(desc(RadarScanBatch.started_at), desc(RadarScanBatch.id))
        .limit(1),
    )
    status_counts = await _status_counts(
        session,
        RadarScanBatch.status,
        RadarScanBatch.started_at,
        since,
    )
    recent_scan_count = sum(status_counts.values())
    failure_count = status_counts.get("failure", 0)
    latest_started_at = _row_datetime(latest_scan, "started_at")
    latest_finished_at = _row_datetime(latest_scan, "finished_at")
    latest_age_seconds = _seconds_between(latest_started_at, now)
    stale_after_seconds = scan_interval_seconds * RADAR_STALE_INTERVAL_MULTIPLIER

    return OpsRadarSummary(
        latest_scan_id=latest_scan.id if latest_scan is not None else None,
        latest_scan_status=str(latest_scan.status) if latest_scan is not None else None,
        latest_scan_started_at=latest_started_at,
        latest_scan_finished_at=latest_finished_at,
        latest_scan_duration_seconds=_seconds_between(latest_started_at, latest_finished_at),
        latest_scan_age_seconds=latest_age_seconds,
        scan_interval_seconds=scan_interval_seconds,
        is_latest_scan_stale=(
            latest_age_seconds is None or latest_age_seconds > stale_after_seconds
        ),
        recent_scan_count=recent_scan_count,
        recent_scan_failure_count=failure_count,
        recent_scan_failure_rate=_rate(failure_count, recent_scan_count),
        status_counts=status_counts,
    )


async def _status_summary(
    session: AsyncSession,
    model: type[Any],
    status_column: Any,
    time_column: Any,
    since: datetime,
    *,
    healthy_statuses: set[str],
) -> OpsCountSummary:
    status_counts = await _status_counts(session, status_column, time_column, since)
    latest_row = await session.scalar(
        select(model).order_by(desc(time_column), desc(model.id)).limit(1),
    )
    latest_status = _row_text(latest_row, "status")
    return OpsCountSummary(
        total_count=sum(status_counts.values()),
        status_counts=status_counts,
        unhealthy_count=sum(
            count
            for status, count in status_counts.items()
            if status not in healthy_statuses
        ),
        latest_status=latest_status,
        latest_at=_row_datetime(latest_row, time_column.key),
    )


def _ops_alerts(
    *,
    radar: OpsRadarSummary,
    provider_fetch: OpsCountSummary,
    data_quality: OpsCountSummary,
    telegram_push: OpsCountSummary,
    model_calls: OpsCountSummary,
) -> list[OpsAlertRead]:
    alerts: list[OpsAlertRead] = []

    if radar.latest_scan_id is None:
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="radar_no_scan",
                message="尚未找到雷达扫描记录。",
            ),
        )
    elif radar.is_latest_scan_stale:
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="radar_stale",
                message="最新雷达扫描已超过预期调度间隔。",
            ),
        )

    if (
        radar.recent_scan_count > 0
        and radar.recent_scan_failure_rate >= RADAR_FAILURE_RATE_ALERT_THRESHOLD
    ):
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="radar_failure_rate_high",
                message="最近雷达扫描失败率偏高。",
            ),
        )

    _append_unhealthy_alert(alerts, provider_fetch, "provider_fetch_unhealthy", "Provider 拉取")
    _append_unhealthy_alert(alerts, data_quality, "data_quality_unhealthy", "数据质量")
    _append_unhealthy_alert(alerts, telegram_push, "telegram_push_unhealthy", "Telegram 推送")
    _append_unhealthy_alert(alerts, model_calls, "model_calls_unhealthy", "模型调用")

    return alerts


def _append_unhealthy_alert(
    alerts: list[OpsAlertRead],
    summary: OpsCountSummary,
    code: str,
    label: str,
) -> None:
    if summary.unhealthy_count <= 0:
        return

    alerts.append(
        OpsAlertRead(
            severity="warning",
            code=code,
            message=f"{label}存在 {summary.unhealthy_count} 条异常记录。",
        ),
    )


async def _status_counts(
    session: AsyncSession,
    status_column: Any,
    time_column: Any,
    since: datetime,
) -> dict[str, int]:
    rows = await session.execute(
        select(status_column, func.count()).where(time_column >= since).group_by(status_column),
    )
    return {str(status): int(count) for status, count in rows.all()}


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0

    return round(numerator / denominator, 4)


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None

    return round((_as_utc(end) - _as_utc(start)).total_seconds(), 3)


def _row_datetime(row: object | None, name: str) -> datetime | None:
    value = getattr(row, name, None)
    if isinstance(value, datetime):
        return _as_utc(value)

    return None


def _row_text(row: object | None, name: str) -> str | None:
    value = getattr(row, name, None)
    if value is None:
        return None

    return str(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
