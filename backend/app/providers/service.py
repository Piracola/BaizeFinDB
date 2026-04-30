from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.provider_models import DataQualityCheck, MarketSnapshot, ProviderFetchLog
from app.providers.akshare import AKSHARE_ENDPOINTS, NORMALIZATION_VERSION, AkshareProvider
from app.providers.schemas import (
    AkshareCollectionResponse,
    DataQualityStatus,
    ProviderCollectionStatusResponse,
    ProviderEndpointCollectionStatus,
    ProviderEndpointResult,
    ProviderFetchLogRead,
    ProviderSnapshotSummary,
    ProviderStatus,
)


async def collect_minimal_akshare(
    session: AsyncSession,
    provider: AkshareProvider | None = None,
) -> AkshareCollectionResponse:
    akshare_provider = provider or AkshareProvider()
    results: list[ProviderEndpointResult] = []

    for endpoint in AKSHARE_ENDPOINTS:
        result = await collect_akshare_endpoint(session, akshare_provider, endpoint)
        results.append(result)

    return AkshareCollectionResponse(results=results)


async def collect_akshare_endpoint(
    session: AsyncSession,
    provider: AkshareProvider,
    endpoint: str,
) -> ProviderEndpointResult:
    started_at = datetime.now(UTC)

    try:
        dataset = await provider.fetch(endpoint)
    except Exception as exc:
        return await _record_failure(session, endpoint, started_at, exc)

    snapshot = MarketSnapshot(
        provider_name=dataset.provider_name,
        endpoint=dataset.endpoint,
        market=dataset.market,
        snapshot_type=dataset.snapshot_type,
        source_time=dataset.source_time,
        row_count=dataset.row_count,
        raw_summary=dataset.raw_summary,
        normalized_rows=dataset.normalized_rows,
        normalization_version=dataset.normalization_version,
    )
    session.add(snapshot)
    await session.flush()

    fetch_log = ProviderFetchLog(
        provider_name=dataset.provider_name,
        endpoint=dataset.endpoint,
        status=ProviderStatus.SUCCESS.value,
        fetch_started_at=started_at,
        fetch_finished_at=datetime.now(UTC),
        source_time=dataset.source_time,
        row_count=dataset.row_count,
        freshness=dataset.quality.freshness,
        confidence=dataset.quality.confidence,
        missing_fields=dataset.quality.missing_fields,
        raw_snapshot_id=snapshot.id,
        normalization_version=dataset.normalization_version,
    )
    session.add(fetch_log)
    await session.flush()

    quality_check = DataQualityCheck(
        provider_name=dataset.provider_name,
        endpoint=dataset.endpoint,
        check_name="required_fields_and_row_count",
        status=dataset.quality.status.value,
        confidence=dataset.quality.confidence,
        missing_fields=dataset.quality.missing_fields,
        details={
            "row_count": dataset.row_count,
            "snapshot_type": dataset.snapshot_type,
            "freshness": dataset.quality.freshness,
        },
        fetch_log_id=fetch_log.id,
        snapshot_id=snapshot.id,
    )
    session.add(quality_check)
    await session.commit()

    return ProviderEndpointResult(
        endpoint=dataset.endpoint,
        status=ProviderStatus.SUCCESS,
        row_count=dataset.row_count,
        quality_status=dataset.quality.status,
        confidence=dataset.quality.confidence,
        missing_fields=dataset.quality.missing_fields,
        fetch_log_id=fetch_log.id,
        snapshot_id=snapshot.id,
    )


async def list_provider_fetch_logs(
    session: AsyncSession,
    provider_name: str = "akshare",
    endpoint: str | None = None,
    limit: int = 20,
) -> list[ProviderFetchLogRead]:
    statement = select(ProviderFetchLog).where(ProviderFetchLog.provider_name == provider_name)

    if endpoint is not None:
        statement = statement.where(ProviderFetchLog.endpoint == endpoint)

    statement = statement.order_by(
        desc(ProviderFetchLog.fetch_finished_at),
        desc(ProviderFetchLog.id),
    ).limit(limit)

    logs = (await session.scalars(statement)).all()
    return [ProviderFetchLogRead.model_validate(log) for log in logs]


async def list_latest_provider_snapshots(
    session: AsyncSession,
    provider_name: str = "akshare",
    endpoint: str | None = None,
) -> list[ProviderSnapshotSummary]:
    endpoints = [endpoint] if endpoint is not None else list(AKSHARE_ENDPOINTS)
    snapshots: list[ProviderSnapshotSummary] = []

    for current_endpoint in endpoints:
        statement = (
            select(MarketSnapshot)
            .where(
                MarketSnapshot.provider_name == provider_name,
                MarketSnapshot.endpoint == current_endpoint,
            )
            .order_by(desc(MarketSnapshot.collected_at), desc(MarketSnapshot.id))
            .limit(1)
        )
        snapshot = await session.scalar(statement)

        if snapshot is not None:
            snapshots.append(_snapshot_summary(snapshot))

    return snapshots


async def get_akshare_collection_status(
    session: AsyncSession,
) -> ProviderCollectionStatusResponse:
    endpoint_statuses: list[ProviderEndpointCollectionStatus] = []

    for spec in AKSHARE_ENDPOINTS.values():
        latest_log = await _latest_fetch_log(session, spec.endpoint)
        latest_quality_check = (
            await _latest_quality_check(session, latest_log.id) if latest_log is not None else None
        )
        last_success = await _latest_fetch_log(
            session,
            spec.endpoint,
            status=ProviderStatus.SUCCESS.value,
        )
        last_failure = await _latest_fetch_log(
            session,
            spec.endpoint,
            status=ProviderStatus.FAILURE.value,
        )

        endpoint_statuses.append(
            ProviderEndpointCollectionStatus(
                endpoint=spec.endpoint,
                title=spec.title,
                latest_status=latest_log.status if latest_log is not None else None,
                latest_quality_status=(
                    latest_quality_check.status if latest_quality_check is not None else None
                ),
                latest_fetch_log_id=latest_log.id if latest_log is not None else None,
                latest_snapshot_id=(
                    latest_log.raw_snapshot_id if latest_log is not None else None
                ),
                latest_checked_at=(
                    latest_log.fetch_finished_at if latest_log is not None else None
                ),
                last_success_at=(
                    last_success.fetch_finished_at if last_success is not None else None
                ),
                last_failure_at=(
                    last_failure.fetch_finished_at if last_failure is not None else None
                ),
                row_count=latest_log.row_count if latest_log is not None else None,
                freshness=latest_log.freshness if latest_log is not None else None,
                confidence=latest_log.confidence if latest_log is not None else None,
                missing_fields=latest_log.missing_fields if latest_log is not None else [],
                error_message=latest_log.error_message if latest_log is not None else None,
            )
        )

    return ProviderCollectionStatusResponse(
        provider_name="akshare",
        endpoints=endpoint_statuses,
    )


async def _record_failure(
    session: AsyncSession,
    endpoint: str,
    started_at: datetime,
    exc: Exception,
) -> ProviderEndpointResult:
    await session.rollback()
    error_message = f"{exc.__class__.__name__}: {str(exc)[:800]}"

    fetch_log = ProviderFetchLog(
        provider_name="akshare",
        endpoint=endpoint,
        status=ProviderStatus.FAILURE.value,
        fetch_started_at=started_at,
        fetch_finished_at=datetime.now(UTC),
        row_count=0,
        error_message=error_message,
        freshness="unavailable",
        confidence=0.0,
        missing_fields=[],
        normalization_version=NORMALIZATION_VERSION,
    )
    session.add(fetch_log)
    await session.flush()

    quality_check = DataQualityCheck(
        provider_name="akshare",
        endpoint=endpoint,
        check_name="provider_fetch",
        status=DataQualityStatus.FAILED.value,
        confidence=0.0,
        missing_fields=[],
        details={"error_message": error_message},
        fetch_log_id=fetch_log.id,
    )
    session.add(quality_check)
    await session.commit()

    return ProviderEndpointResult(
        endpoint=endpoint,
        status=ProviderStatus.FAILURE,
        quality_status=DataQualityStatus.FAILED,
        confidence=0.0,
        fetch_log_id=fetch_log.id,
        error_message=error_message,
    )


def _snapshot_summary(snapshot: MarketSnapshot) -> ProviderSnapshotSummary:
    return ProviderSnapshotSummary(
        id=snapshot.id,
        provider_name=snapshot.provider_name,
        endpoint=snapshot.endpoint,
        market=snapshot.market,
        snapshot_type=snapshot.snapshot_type,
        source_time=snapshot.source_time,
        collected_at=snapshot.collected_at,
        row_count=snapshot.row_count,
        normalization_version=snapshot.normalization_version,
        raw_summary=snapshot.raw_summary,
        preview_rows=snapshot.normalized_rows[:5],
    )


async def _latest_fetch_log(
    session: AsyncSession,
    endpoint: str,
    status: str | None = None,
) -> ProviderFetchLog | None:
    statement = select(ProviderFetchLog).where(
        ProviderFetchLog.provider_name == "akshare",
        ProviderFetchLog.endpoint == endpoint,
    )

    if status is not None:
        statement = statement.where(ProviderFetchLog.status == status)

    statement = statement.order_by(
        desc(ProviderFetchLog.fetch_finished_at),
        desc(ProviderFetchLog.id),
    ).limit(1)
    return await session.scalar(statement)


async def _latest_quality_check(
    session: AsyncSession,
    fetch_log_id: int,
) -> DataQualityCheck | None:
    statement = (
        select(DataQualityCheck)
        .where(DataQualityCheck.fetch_log_id == fetch_log_id)
        .order_by(desc(DataQualityCheck.created_at), desc(DataQualityCheck.id))
        .limit(1)
    )
    return await session.scalar(statement)
