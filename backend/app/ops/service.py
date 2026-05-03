import os
import platform
import shutil
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import psutil
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.audit_models import ModelCallLog
from app.db.provider_models import DataQualityCheck, ProviderFetchLog
from app.db.push_models import PushLog
from app.db.radar_models import RadarScanBatch
from app.ops.schemas import (
    OpsAlertRead,
    OpsCountSummary,
    OpsFailureSummaryRead,
    OpsHistoryEventRead,
    OpsHistoryRead,
    OpsOverviewRead,
    OpsRadarSummary,
    OpsReadinessCheckRead,
    OpsReadinessRead,
    OpsServerSummary,
)

RADAR_STALE_INTERVAL_MULTIPLIER = 2
RADAR_FAILURE_RATE_ALERT_THRESHOLD = 0.2
PROCESS_STARTED_AT = datetime.now(UTC)


async def get_ops_overview(
    session: AsyncSession,
    *,
    lookback_hours: int = 24,
    now: datetime | None = None,
) -> OpsOverviewRead:
    generated_at = _as_utc(now or datetime.now(UTC))
    since = generated_at - timedelta(hours=lookback_hours)
    settings = get_settings()
    server = _server_summary(
        now=generated_at,
        disk_check_path=settings.ops_disk_check_path,
        disk_free_percent_alert_threshold=(
            settings.ops_disk_free_percent_alert_threshold
        ),
        cpu_usage_percent_alert_threshold=(
            settings.ops_cpu_usage_percent_alert_threshold
        ),
        memory_used_percent_alert_threshold=(
            settings.ops_memory_used_percent_alert_threshold
        ),
    )
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
        server=server,
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
            server=server,
        ),
    )


async def get_ops_history(
    session: AsyncSession,
    *,
    lookback_hours: int = 24,
    limit: int = 30,
    now: datetime | None = None,
) -> OpsHistoryRead:
    generated_at = _as_utc(now or datetime.now(UTC))
    since = generated_at - timedelta(hours=lookback_hours)
    event_groups = await _history_event_groups(session, since=since, limit=limit)
    events = sorted(
        (event for group in event_groups for event in group),
        key=lambda event: (_as_utc(event.occurred_at), event.kind, event.id),
        reverse=True,
    )[:limit]
    failure_summary = sorted(
        await _failure_summary(session, since=since),
        key=lambda item: (-item.count, item.kind, item.key),
    )

    return OpsHistoryRead(
        generated_at=generated_at,
        lookback_hours=lookback_hours,
        limit=limit,
        recent_events=events,
        failure_summary=failure_summary,
    )


async def get_ops_readiness(
    session: AsyncSession,
    *,
    lookback_hours: int = 24,
    now: datetime | None = None,
) -> OpsReadinessRead:
    generated_at = _as_utc(now or datetime.now(UTC))
    overview = await get_ops_overview(
        session,
        lookback_hours=lookback_hours,
        now=generated_at,
    )
    settings = get_settings()
    checks = _readiness_checks(
        overview,
        telegram_push_enabled=settings.telegram_push_enabled,
    )
    return OpsReadinessRead(
        generated_at=generated_at,
        lookback_hours=lookback_hours,
        status=_readiness_status(checks),
        checks=checks,
    )


def _readiness_checks(
    overview: OpsOverviewRead,
    *,
    telegram_push_enabled: bool,
) -> list[OpsReadinessCheckRead]:
    return [
        _server_disk_readiness(overview.server),
        _server_cpu_readiness(overview.server),
        _server_memory_readiness(overview.server),
        _radar_freshness_readiness(overview.radar),
        _radar_failure_readiness(overview.radar),
        _count_summary_readiness(
            "provider_fetch",
            "Provider 拉取",
            overview.provider_fetch,
            empty_status="warning",
        ),
        _count_summary_readiness(
            "data_quality",
            "数据质量",
            overview.data_quality,
            empty_status="warning",
        ),
        _telegram_push_readiness(
            overview.telegram_push,
            telegram_push_enabled=telegram_push_enabled,
        ),
        _count_summary_readiness(
            "model_calls",
            "模型调用",
            overview.model_calls,
            empty_status="ok",
        ),
    ]


def _server_disk_readiness(server: OpsServerSummary) -> OpsReadinessCheckRead:
    if server.disk_error:
        return _readiness_check(
            "server_disk",
            "fail",
            "服务端磁盘空间检查失败。",
            disk_error=server.disk_error,
            disk_path=server.disk_path,
        )

    if server.is_disk_space_low:
        return _readiness_check(
            "server_disk",
            "warning",
            "服务端磁盘可用空间偏低。",
            disk_free_percent=server.disk_free_percent,
            disk_path=server.disk_path,
        )

    return _readiness_check(
        "server_disk",
        "ok",
        "服务端磁盘空间充足。",
        disk_free_percent=server.disk_free_percent,
        disk_path=server.disk_path,
    )


def _server_cpu_readiness(server: OpsServerSummary) -> OpsReadinessCheckRead:
    if server.cpu_error:
        return _readiness_check(
            "server_cpu",
            "warning",
            "服务端 CPU 指标不可用。",
            cpu_error=server.cpu_error,
            cpu_logical_count=server.cpu_logical_count,
        )

    if server.is_cpu_pressure_high:
        return _readiness_check(
            "server_cpu",
            "warning",
            "服务端 CPU 压力偏高。",
            cpu_usage_percent=server.cpu_usage_percent,
            cpu_logical_count=server.cpu_logical_count,
            cpu_load_1m=server.cpu_load_1m,
        )

    return _readiness_check(
        "server_cpu",
        "ok",
        "服务端 CPU 压力正常。",
        cpu_usage_percent=server.cpu_usage_percent,
        cpu_logical_count=server.cpu_logical_count,
        cpu_load_1m=server.cpu_load_1m,
    )


def _server_memory_readiness(server: OpsServerSummary) -> OpsReadinessCheckRead:
    if server.memory_error:
        return _readiness_check(
            "server_memory",
            "warning",
            "服务端内存指标不可用。",
            memory_error=server.memory_error,
        )

    if server.is_memory_pressure_high:
        return _readiness_check(
            "server_memory",
            "warning",
            "服务端内存压力偏高。",
            memory_used_percent=server.memory_used_percent,
            memory_available_bytes=server.memory_available_bytes,
            memory_total_bytes=server.memory_total_bytes,
        )

    return _readiness_check(
        "server_memory",
        "ok",
        "服务端内存余量正常。",
        memory_used_percent=server.memory_used_percent,
        memory_available_bytes=server.memory_available_bytes,
        memory_total_bytes=server.memory_total_bytes,
    )


def _radar_freshness_readiness(radar: OpsRadarSummary) -> OpsReadinessCheckRead:
    if radar.latest_scan_id is None:
        return _readiness_check(
            "radar_freshness",
            "fail",
            "尚未找到雷达扫描记录。",
        )

    if radar.is_latest_scan_stale:
        return _readiness_check(
            "radar_freshness",
            "warning",
            "最新雷达扫描已超过预期调度间隔。",
            latest_scan_id=radar.latest_scan_id,
            latest_scan_age_seconds=radar.latest_scan_age_seconds,
        )

    return _readiness_check(
        "radar_freshness",
        "ok",
        "雷达扫描节奏正常。",
        latest_scan_id=radar.latest_scan_id,
        latest_scan_age_seconds=radar.latest_scan_age_seconds,
    )


def _radar_failure_readiness(radar: OpsRadarSummary) -> OpsReadinessCheckRead:
    if radar.recent_scan_count <= 0:
        return _readiness_check(
            "radar_failure_rate",
            "warning",
            "统计窗口内没有雷达扫描记录。",
        )

    if radar.recent_scan_failure_rate >= 0.5:
        return _readiness_check(
            "radar_failure_rate",
            "fail",
            "最近雷达扫描失败率过高。",
            recent_scan_count=radar.recent_scan_count,
            recent_scan_failure_rate=radar.recent_scan_failure_rate,
        )

    if radar.recent_scan_failure_rate >= RADAR_FAILURE_RATE_ALERT_THRESHOLD:
        return _readiness_check(
            "radar_failure_rate",
            "warning",
            "最近雷达扫描失败率偏高。",
            recent_scan_count=radar.recent_scan_count,
            recent_scan_failure_rate=radar.recent_scan_failure_rate,
        )

    return _readiness_check(
        "radar_failure_rate",
        "ok",
        "最近雷达扫描失败率正常。",
        recent_scan_count=radar.recent_scan_count,
        recent_scan_failure_rate=radar.recent_scan_failure_rate,
    )


def _telegram_push_readiness(
    summary: OpsCountSummary,
    *,
    telegram_push_enabled: bool,
) -> OpsReadinessCheckRead:
    if not telegram_push_enabled:
        return _readiness_check(
            "telegram_push",
            "ok",
            "Telegram 推送未启用，跳过推送就绪判断。",
            push_enabled=False,
        )

    return _count_summary_readiness(
        "telegram_push",
        "Telegram 推送",
        summary,
        empty_status="warning",
    )


def _count_summary_readiness(
    name: str,
    label: str,
    summary: OpsCountSummary,
    *,
    empty_status: str,
) -> OpsReadinessCheckRead:
    if summary.total_count <= 0:
        return _readiness_check(
            name,
            empty_status,
            f"统计窗口内没有{label}记录。",
            total_count=summary.total_count,
            unhealthy_count=summary.unhealthy_count,
        )

    if summary.unhealthy_count >= summary.total_count:
        return _readiness_check(
            name,
            "fail",
            f"{label}最近记录全部异常。",
            total_count=summary.total_count,
            unhealthy_count=summary.unhealthy_count,
        )

    if summary.unhealthy_count > 0:
        return _readiness_check(
            name,
            "warning",
            f"{label}存在异常记录。",
            total_count=summary.total_count,
            unhealthy_count=summary.unhealthy_count,
        )

    return _readiness_check(
        name,
        "ok",
        f"{label}最近记录正常。",
        total_count=summary.total_count,
        unhealthy_count=summary.unhealthy_count,
    )


def _readiness_check(
    name: str,
    status: str,
    message: str,
    **metadata: object,
) -> OpsReadinessCheckRead:
    return OpsReadinessCheckRead(
        name=name,
        status=status,
        message=message,
        metadata=metadata,
    )


def _readiness_status(checks: list[OpsReadinessCheckRead]) -> str:
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "blocked"
    if "warning" in statuses:
        return "warning"

    return "ready"


async def _history_event_groups(
    session: AsyncSession,
    *,
    since: datetime,
    limit: int,
) -> list[list[OpsHistoryEventRead]]:
    return [
        await _radar_history_events(session, since=since, limit=limit),
        await _provider_fetch_history_events(session, since=since, limit=limit),
        await _data_quality_history_events(session, since=since, limit=limit),
        await _telegram_push_history_events(session, since=since, limit=limit),
        await _model_call_history_events(session, since=since, limit=limit),
    ]


async def _radar_history_events(
    session: AsyncSession,
    *,
    since: datetime,
    limit: int,
) -> list[OpsHistoryEventRead]:
    rows = await session.scalars(
        select(RadarScanBatch)
        .where(RadarScanBatch.started_at >= since)
        .order_by(desc(RadarScanBatch.started_at), desc(RadarScanBatch.id))
        .limit(limit),
    )
    return [
        OpsHistoryEventRead(
            id=row.id,
            kind="radar_scan",
            status=str(row.status),
            occurred_at=_row_datetime(row, "started_at") or since,
            duration_seconds=_seconds_between(row.started_at, row.finished_at),
            title=f"雷达扫描 #{row.id}",
            detail=_short_text(row.error_message),
            metadata={
                "signal_count": _summary_value(row.summary, "signal_count"),
                "source_snapshot_count": len(row.source_snapshot_ids or []),
            },
        )
        for row in rows.all()
    ]


async def _provider_fetch_history_events(
    session: AsyncSession,
    *,
    since: datetime,
    limit: int,
) -> list[OpsHistoryEventRead]:
    rows = await session.scalars(
        select(ProviderFetchLog)
        .where(
            ProviderFetchLog.fetch_finished_at >= since,
            ProviderFetchLog.status != "success",
        )
        .order_by(desc(ProviderFetchLog.fetch_finished_at), desc(ProviderFetchLog.id))
        .limit(limit),
    )
    return [
        OpsHistoryEventRead(
            id=row.id,
            kind="provider_fetch",
            status=str(row.status),
            occurred_at=_row_datetime(row, "fetch_finished_at") or since,
            duration_seconds=_seconds_between(row.fetch_started_at, row.fetch_finished_at),
            title=f"Provider {row.provider_name}/{row.endpoint}",
            detail=_short_text(row.error_message),
            metadata={
                "provider_name": row.provider_name,
                "endpoint": row.endpoint,
                "row_count": row.row_count,
                "freshness": row.freshness,
                "confidence": row.confidence,
            },
        )
        for row in rows.all()
    ]


async def _data_quality_history_events(
    session: AsyncSession,
    *,
    since: datetime,
    limit: int,
) -> list[OpsHistoryEventRead]:
    rows = await session.scalars(
        select(DataQualityCheck)
        .where(
            DataQualityCheck.created_at >= since,
            DataQualityCheck.status != "ok",
        )
        .order_by(desc(DataQualityCheck.created_at), desc(DataQualityCheck.id))
        .limit(limit),
    )
    return [
        OpsHistoryEventRead(
            id=row.id,
            kind="data_quality",
            status=str(row.status),
            occurred_at=_row_datetime(row, "created_at") or since,
            title=f"数据质量 {row.provider_name}/{row.endpoint}",
            detail=_short_text(", ".join(row.missing_fields or [])),
            metadata={
                "provider_name": row.provider_name,
                "endpoint": row.endpoint,
                "check_name": row.check_name,
                "confidence": row.confidence,
            },
        )
        for row in rows.all()
    ]


async def _telegram_push_history_events(
    session: AsyncSession,
    *,
    since: datetime,
    limit: int,
) -> list[OpsHistoryEventRead]:
    rows = await session.scalars(
        select(PushLog)
        .where(
            PushLog.created_at >= since,
            PushLog.status.notin_(("sent", "preview", "skipped")),
        )
        .order_by(desc(PushLog.created_at), desc(PushLog.id))
        .limit(limit),
    )
    return [
        OpsHistoryEventRead(
            id=row.id,
            kind="telegram_push",
            status=str(row.status),
            occurred_at=_row_datetime(row, "created_at") or since,
            title=f"{row.channel} 推送 {row.source_kind} #{row.source_id}",
            detail=_short_text(row.title),
            metadata={
                "channel": row.channel,
                "source_kind": row.source_kind,
                "source_id": row.source_id,
                "included_signal_count": len(row.included_signal_ids or []),
                "blocked_signal_count": len(row.blocked_signal_ids or []),
            },
        )
        for row in rows.all()
    ]


async def _model_call_history_events(
    session: AsyncSession,
    *,
    since: datetime,
    limit: int,
) -> list[OpsHistoryEventRead]:
    rows = await session.scalars(
        select(ModelCallLog)
        .where(
            ModelCallLog.created_at >= since,
            ModelCallLog.status != "success",
        )
        .order_by(desc(ModelCallLog.created_at), desc(ModelCallLog.id))
        .limit(limit),
    )
    return [
        OpsHistoryEventRead(
            id=row.id,
            kind="model_call",
            status=str(row.status),
            occurred_at=_row_datetime(row, "created_at") or since,
            title=f"模型调用 {row.call_site}",
            detail=_short_text(row.error_type or row.error_message),
            metadata={
                "call_site": row.call_site,
                "primary_model": row.primary_model,
                "fallback_model": row.fallback_model,
                "error_type": row.error_type,
            },
        )
        for row in rows.all()
    ]


async def _failure_summary(
    session: AsyncSession,
    *,
    since: datetime,
) -> list[OpsFailureSummaryRead]:
    summary: list[OpsFailureSummaryRead] = []

    radar_rows = await session.execute(
        select(RadarScanBatch.status, func.count())
        .where(
            RadarScanBatch.started_at >= since,
            RadarScanBatch.status == "failure",
        )
        .group_by(RadarScanBatch.status),
    )
    summary.extend(
        OpsFailureSummaryRead(kind="radar_scan", key=str(status), count=int(count))
        for status, count in radar_rows.all()
    )

    provider_rows = await session.execute(
        select(
            ProviderFetchLog.provider_name,
            ProviderFetchLog.endpoint,
            ProviderFetchLog.status,
            func.count(),
        )
        .where(
            ProviderFetchLog.fetch_finished_at >= since,
            ProviderFetchLog.status != "success",
        )
        .group_by(
            ProviderFetchLog.provider_name,
            ProviderFetchLog.endpoint,
            ProviderFetchLog.status,
        ),
    )
    summary.extend(
        OpsFailureSummaryRead(
            kind="provider_fetch",
            key=_join_key(provider_name, endpoint, status),
            count=int(count),
        )
        for provider_name, endpoint, status, count in provider_rows.all()
    )

    quality_rows = await session.execute(
        select(
            DataQualityCheck.provider_name,
            DataQualityCheck.endpoint,
            DataQualityCheck.status,
            func.count(),
        )
        .where(
            DataQualityCheck.created_at >= since,
            DataQualityCheck.status != "ok",
        )
        .group_by(
            DataQualityCheck.provider_name,
            DataQualityCheck.endpoint,
            DataQualityCheck.status,
        ),
    )
    summary.extend(
        OpsFailureSummaryRead(
            kind="data_quality",
            key=_join_key(provider_name, endpoint, status),
            count=int(count),
        )
        for provider_name, endpoint, status, count in quality_rows.all()
    )

    push_rows = await session.execute(
        select(PushLog.channel, PushLog.status, func.count())
        .where(
            PushLog.created_at >= since,
            PushLog.status.notin_(("sent", "preview", "skipped")),
        )
        .group_by(PushLog.channel, PushLog.status),
    )
    summary.extend(
        OpsFailureSummaryRead(
            kind="telegram_push",
            key=_join_key(channel, status),
            count=int(count),
        )
        for channel, status, count in push_rows.all()
    )

    model_rows = await session.execute(
        select(
            ModelCallLog.call_site,
            ModelCallLog.status,
            ModelCallLog.error_type,
            func.count(),
        )
        .where(
            ModelCallLog.created_at >= since,
            ModelCallLog.status != "success",
        )
        .group_by(
            ModelCallLog.call_site,
            ModelCallLog.status,
            ModelCallLog.error_type,
        ),
    )
    summary.extend(
        OpsFailureSummaryRead(
            kind="model_call",
            key=_join_key(call_site, status, error_type),
            count=int(count),
        )
        for call_site, status, error_type, count in model_rows.all()
    )

    return summary


def _server_summary(
    *,
    now: datetime,
    disk_check_path: str,
    disk_free_percent_alert_threshold: float,
    cpu_usage_percent_alert_threshold: float,
    memory_used_percent_alert_threshold: float,
) -> OpsServerSummary:
    disk_path = disk_check_path.strip() or "."
    payload: dict[str, Any] = {
        "process_id": os.getpid(),
        "process_started_at": PROCESS_STARTED_AT,
        "process_uptime_seconds": _seconds_between(PROCESS_STARTED_AT, now) or 0.0,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "disk_path": disk_path,
    }

    payload.update(
        _disk_summary(
            disk_path=disk_path,
            disk_free_percent_alert_threshold=disk_free_percent_alert_threshold,
        ),
    )
    payload.update(
        _cpu_summary(
            cpu_usage_percent_alert_threshold=cpu_usage_percent_alert_threshold,
        ),
    )
    payload.update(
        _memory_summary(
            memory_used_percent_alert_threshold=memory_used_percent_alert_threshold,
        ),
    )

    return OpsServerSummary(**payload)


def _disk_summary(
    *,
    disk_path: str,
    disk_free_percent_alert_threshold: float,
) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(disk_path)
    except OSError as exc:
        return {
            "is_disk_space_low": False,
            "disk_error": f"{exc.__class__.__name__}: {exc}",
        }

    total = int(usage.total)
    used = int(usage.used)
    free = int(usage.free)
    free_percent = _percent(free, total)
    used_percent = _percent(used, total)

    return {
        "disk_total_bytes": total,
        "disk_used_bytes": used,
        "disk_free_bytes": free,
        "disk_used_percent": used_percent,
        "disk_free_percent": free_percent,
        "is_disk_space_low": (
            free_percent is not None
            and free_percent <= disk_free_percent_alert_threshold
        ),
    }


def _cpu_summary(*, cpu_usage_percent_alert_threshold: float) -> dict[str, Any]:
    payload: dict[str, Any] = {"is_cpu_pressure_high": False}

    try:
        payload["cpu_logical_count"] = psutil.cpu_count(logical=True)
        cpu_usage_percent = _bounded_percent(psutil.cpu_percent(interval=None))
    except (OSError, RuntimeError, ValueError) as exc:
        payload["cpu_error"] = f"{exc.__class__.__name__}: {exc}"
        return payload

    payload["cpu_usage_percent"] = cpu_usage_percent
    payload["is_cpu_pressure_high"] = (
        cpu_usage_percent is not None
        and cpu_usage_percent >= cpu_usage_percent_alert_threshold
    )
    payload.update(_cpu_load_summary())
    return payload


def _cpu_load_summary() -> dict[str, Any]:
    try:
        load_1m, load_5m, load_15m = psutil.getloadavg()
    except (AttributeError, OSError, RuntimeError):
        return {}

    return {
        "cpu_load_1m": round(float(load_1m), 3),
        "cpu_load_5m": round(float(load_5m), 3),
        "cpu_load_15m": round(float(load_15m), 3),
    }


def _memory_summary(*, memory_used_percent_alert_threshold: float) -> dict[str, Any]:
    try:
        memory = psutil.virtual_memory()
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "is_memory_pressure_high": False,
            "memory_error": f"{exc.__class__.__name__}: {exc}",
        }

    total = int(memory.total)
    available = int(memory.available)
    used = int(memory.used)
    used_percent = _bounded_percent(memory.percent)

    return {
        "memory_total_bytes": total,
        "memory_available_bytes": available,
        "memory_used_bytes": used,
        "memory_used_percent": used_percent,
        "memory_available_percent": _percent(available, total),
        "is_memory_pressure_high": (
            used_percent is not None
            and used_percent >= memory_used_percent_alert_threshold
        ),
    }


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
    server: OpsServerSummary,
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

    if server.disk_error:
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="server_disk_check_failed",
                message="服务器磁盘空间检查失败。",
            ),
        )
    elif server.is_disk_space_low:
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="server_disk_space_low",
                message="服务器磁盘可用空间偏低。",
            ),
        )

    if server.cpu_error:
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="server_cpu_check_failed",
                message="服务器 CPU 指标不可用。",
            ),
        )
    elif server.is_cpu_pressure_high:
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="server_cpu_pressure_high",
                message="服务器 CPU 压力偏高。",
            ),
        )

    if server.memory_error:
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="server_memory_check_failed",
                message="服务器内存指标不可用。",
            ),
        )
    elif server.is_memory_pressure_high:
        alerts.append(
            OpsAlertRead(
                severity="warning",
                code="server_memory_pressure_high",
                message="服务器内存压力偏高。",
            ),
        )

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


def _percent(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None

    return round((numerator / denominator) * 100, 2)


def _bounded_percent(value: object) -> float | None:
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return None

    return round(max(0.0, min(100.0, percent)), 2)


def _summary_value(summary: dict[str, object], key: str) -> object:
    if not isinstance(summary, dict):
        return None

    return summary.get(key)


def _short_text(value: object | None, *, max_length: int = 180) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None
    if len(text) <= max_length:
        return text

    return f"{text[: max_length - 3]}..."


def _join_key(*parts: object | None) -> str:
    values = [str(part) for part in parts if part is not None and str(part).strip()]
    return "/".join(values) if values else "unknown"


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
