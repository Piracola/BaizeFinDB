from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.provider_models import DataQualityCheck, MarketSnapshot, ProviderFetchLog
from app.providers.akshare import AKSHARE_ENDPOINTS, NORMALIZATION_VERSION, AkshareProvider
from app.providers.schemas import (
    AkshareCollectionResponse,
    DataQualityStatus,
    ProviderEndpointResult,
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

