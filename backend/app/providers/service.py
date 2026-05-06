from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.provider_models import DataQualityCheck, MarketSnapshot, ProviderFetchLog
from app.providers.akshare import AKSHARE_ENDPOINTS, NORMALIZATION_VERSION, AkshareProvider
from app.providers.schemas import (
    AkshareCollectionResponse,
    DataQualityStatus,
    ProviderCollectionStatusResponse,
    ProviderDataset,
    ProviderEndpointCollectionStatus,
    ProviderEndpointResult,
    ProviderFetchLogRead,
    ProviderSnapshotSummary,
    ProviderStatus,
    TushareEndpointReadiness,
    TushareReadinessCheck,
    TushareReadinessResponse,
)
from app.providers.tushare import (
    NORMALIZATION_VERSION as TUSHARE_NORMALIZATION_VERSION,
)
from app.providers.tushare import (
    TUSHARE_ENDPOINTS,
    TushareEndpointSpec,
    TushareProvider,
    get_tushare_provider_status,
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


async def collect_tushare_stock_basic(
    session: AsyncSession,
    provider: TushareProvider | None = None,
) -> ProviderEndpointResult:
    tushare_provider = provider or TushareProvider()
    return await collect_tushare_endpoint(session, tushare_provider, "stock_basic")


async def collect_tushare_daily(
    session: AsyncSession,
    *,
    trade_date: str | None = None,
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    provider: TushareProvider | None = None,
) -> ProviderEndpointResult:
    tushare_provider = provider or TushareProvider()
    return await collect_tushare_endpoint(
        session,
        tushare_provider,
        "daily",
        query_params=_tushare_daily_query_params(
            trade_date=trade_date,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        ),
    )


async def collect_tushare_announcements(
    session: AsyncSession,
    ann_date: str | None = None,
    provider: TushareProvider | None = None,
) -> ProviderEndpointResult:
    tushare_provider = provider or TushareProvider()
    query_params = {"ann_date": ann_date} if ann_date is not None else None
    return await collect_tushare_endpoint(
        session,
        tushare_provider,
        "anns_d",
        query_params=query_params,
    )


async def collect_tushare_stock_company(
    session: AsyncSession,
    exchange: str = "SZSE",
    provider: TushareProvider | None = None,
) -> ProviderEndpointResult:
    tushare_provider = provider or TushareProvider()
    return await collect_tushare_endpoint(
        session,
        tushare_provider,
        "stock_company",
        query_params={"exchange": exchange},
    )


async def collect_akshare_endpoint(
    session: AsyncSession,
    provider: AkshareProvider,
    endpoint: str,
) -> ProviderEndpointResult:
    started_at = datetime.now(UTC)

    try:
        dataset = await provider.fetch(endpoint)
    except Exception as exc:
        return await _record_failure(
            session,
            "akshare",
            endpoint,
            started_at,
            exc,
            NORMALIZATION_VERSION,
        )

    return await _record_success(session, dataset, started_at)


async def collect_tushare_endpoint(
    session: AsyncSession,
    provider: TushareProvider,
    endpoint: str,
    query_params: dict[str, object] | None = None,
) -> ProviderEndpointResult:
    started_at = datetime.now(UTC)

    try:
        dataset = await provider.fetch(endpoint, query_params=query_params)
    except Exception as exc:
        return await _record_failure(
            session,
            "tushare",
            endpoint,
            started_at,
            exc,
            TUSHARE_NORMALIZATION_VERSION,
        )

    return await _record_success(session, dataset, started_at)


async def _record_success(
    session: AsyncSession,
    dataset: ProviderDataset,
    started_at: datetime,
) -> ProviderEndpointResult:

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
    endpoints = (
        [endpoint] if endpoint is not None else list(_known_provider_endpoints(provider_name))
    )
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


async def get_tushare_readiness(
    session: AsyncSession,
    settings: Settings | None = None,
) -> TushareReadinessResponse:
    active_settings = settings or get_settings()
    provider_status = get_tushare_provider_status(active_settings)
    endpoint_readiness: list[TushareEndpointReadiness] = []

    for spec in TUSHARE_ENDPOINTS.values():
        latest_log = await _latest_fetch_log(session, spec.endpoint, provider_name="tushare")
        latest_quality_check = (
            await _latest_quality_check(session, latest_log.id) if latest_log is not None else None
        )
        last_success = await _latest_fetch_log(
            session,
            spec.endpoint,
            provider_name="tushare",
            status=ProviderStatus.SUCCESS.value,
        )
        last_failure = await _latest_fetch_log(
            session,
            spec.endpoint,
            provider_name="tushare",
            status=ProviderStatus.FAILURE.value,
        )
        checks = _tushare_endpoint_readiness_checks(
            spec,
            token_configured=provider_status.token_configured,
            latest_log=latest_log,
            latest_quality_check=latest_quality_check,
        )
        endpoint_status = _provider_readiness_status(checks)
        manual_fetch_eligible = spec.implemented and provider_status.token_configured
        scheduler_eligible = (
            spec.endpoint == "anns_d"
            and manual_fetch_eligible
            and latest_log is not None
            and latest_log.status == ProviderStatus.SUCCESS.value
            and latest_log.row_count > 0
            and latest_quality_check is not None
            and latest_quality_check.status == DataQualityStatus.OK.value
        )

        endpoint_readiness.append(
            TushareEndpointReadiness(
                endpoint=spec.endpoint,
                title=spec.title,
                implemented=spec.implemented,
                manual_fetch_eligible=manual_fetch_eligible,
                scheduler_eligible=scheduler_eligible,
                status=endpoint_status,
                latest_status=latest_log.status if latest_log is not None else None,
                latest_quality_status=(
                    latest_quality_check.status if latest_quality_check is not None else None
                ),
                latest_fetch_log_id=latest_log.id if latest_log is not None else None,
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
                checks=checks,
            )
        )

    scheduler_ready_count = sum(1 for item in endpoint_readiness if item.scheduler_eligible)

    return TushareReadinessResponse(
        generated_at=datetime.now(UTC),
        status=_tushare_overall_readiness_status(
            provider_status.token_configured,
            endpoint_readiness,
        ),
        token_configured=provider_status.token_configured,
        fetch_enabled=provider_status.fetch_enabled,
        endpoint_count=provider_status.endpoint_count,
        implemented_endpoint_count=provider_status.implemented_endpoint_count,
        scheduler_enabled=active_settings.tushare_anns_d_beat_enabled,
        scheduler_ready_endpoint_count=scheduler_ready_count,
        scheduler_policy=_tushare_scheduler_policy(active_settings),
        message=_tushare_readiness_message(
            provider_status.token_configured,
            provider_status.implemented_endpoint_count,
            scheduler_ready_count,
            active_settings.tushare_anns_d_beat_enabled,
        ),
        endpoints=endpoint_readiness,
    )


def _tushare_endpoint_readiness_checks(
    spec: TushareEndpointSpec,
    *,
    token_configured: bool,
    latest_log: ProviderFetchLog | None,
    latest_quality_check: DataQualityCheck | None,
) -> list[TushareReadinessCheck]:
    checks = [
        _tushare_readiness_check(
            name="token",
            status="ok" if token_configured else "fail",
            message=(
                "TUSHARE_TOKEN 已配置。"
                if token_configured
                else "TUSHARE_TOKEN 未配置，不能手动抓取或评估调度准入。"
            ),
        ),
        _tushare_readiness_check(
            name="implementation",
            status="ok" if spec.implemented else "fail",
            message=(
                "端点已实现手动抓取。"
                if spec.implemented
                else "端点尚未实现真实抓取。"
            ),
            metadata={"snapshot_type": spec.snapshot_type},
        ),
        _tushare_readiness_check(
            name="required_fields",
            status="ok" if spec.required_fields else "fail",
            message=(
                f"已声明必需字段：{', '.join(spec.required_fields)}。"
                if spec.required_fields
                else "未声明标准化必需字段。"
            ),
        ),
        _tushare_query_readiness(spec),
        _tushare_latest_fetch_readiness(latest_log),
        _tushare_quality_readiness(latest_quality_check),
    ]

    if spec.endpoint == "anns_d":
        checks.append(
            _tushare_readiness_check(
                name="radar_mapping",
                status="ok",
                message="重大风险公告标题已接入雷达 risk P0 轻量映射；普通公告不会直接成信号。",
            )
        )

    return checks


def _tushare_query_readiness(spec: TushareEndpointSpec) -> TushareReadinessCheck:
    if spec.query_params:
        return _tushare_readiness_check(
            name="default_query",
            status="ok",
            message="已声明默认查询参数。",
            metadata={"query_params": spec.query_params},
        )

    if spec.endpoint == "anns_d":
        return _tushare_readiness_check(
            name="default_query",
            status="ok",
            message="未传公告日期时会使用当天日期，适合手动验证最新公告。",
            metadata={"query_params": {"ann_date": "dynamic_today_utc"}},
        )

    if spec.endpoint == "daily":
        return _tushare_readiness_check(
            name="default_query",
            status="ok",
            message="未传交易日期或股票代码时会使用当天日期，适合先手动验证最新日线行情。",
            metadata={"query_params": {"trade_date": "dynamic_today_utc"}},
        )

    return _tushare_readiness_check(
        name="default_query",
        status="warning",
        message="未声明默认查询参数，进入调度前需要确认不会产生过大请求范围。",
    )


def _tushare_latest_fetch_readiness(
    latest_log: ProviderFetchLog | None,
) -> TushareReadinessCheck:
    if latest_log is None:
        return _tushare_readiness_check(
            name="latest_fetch",
            status="warning",
            message="暂无真实抓取记录，进入调度前需要至少一次成功样例。",
        )

    if latest_log.status == ProviderStatus.SUCCESS.value and latest_log.row_count > 0:
        return _tushare_readiness_check(
            name="latest_fetch",
            status="ok",
            message=f"最近抓取成功，行数 {latest_log.row_count}。",
            metadata={"fetch_log_id": latest_log.id},
        )

    if latest_log.status == ProviderStatus.SUCCESS.value:
        return _tushare_readiness_check(
            name="latest_fetch",
            status="warning",
            message="最近抓取成功但没有返回数据，进入调度前需要确认接口权限和查询范围。",
            metadata={"fetch_log_id": latest_log.id},
        )

    return _tushare_readiness_check(
        name="latest_fetch",
        status="fail",
        message="最近抓取失败，不能进入调度准入。",
        metadata={
            "fetch_log_id": latest_log.id,
            "error_message": latest_log.error_message,
        },
    )


def _tushare_quality_readiness(
    latest_quality_check: DataQualityCheck | None,
) -> TushareReadinessCheck:
    if latest_quality_check is None:
        return _tushare_readiness_check(
            name="data_quality",
            status="warning",
            message="暂无数据质量记录，进入调度前需要字段完整性样例。",
        )

    if latest_quality_check.status == DataQualityStatus.OK.value:
        return _tushare_readiness_check(
            name="data_quality",
            status="ok",
            message="最近数据质量为 ok。",
            metadata={"confidence": latest_quality_check.confidence},
        )

    status = "fail" if latest_quality_check.status == DataQualityStatus.FAILED.value else "warning"
    return _tushare_readiness_check(
        name="data_quality",
        status=status,
        message=(
            "最近数据质量失败，不能进入调度准入。"
            if status == "fail"
            else "最近数据质量降级，进入调度前需要处理缺失字段。"
        ),
        metadata={
            "quality_status": latest_quality_check.status,
            "missing_fields": latest_quality_check.missing_fields,
            "confidence": latest_quality_check.confidence,
        },
    )


def _tushare_readiness_check(
    *,
    name: str,
    status: str,
    message: str,
    metadata: dict[str, object] | None = None,
) -> TushareReadinessCheck:
    return TushareReadinessCheck(
        name=name,
        status=status,
        message=message,
        metadata=metadata or {},
    )


def _provider_readiness_status(checks: list[TushareReadinessCheck]) -> str:
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "blocked"
    if "warning" in statuses:
        return "warning"
    return "ready"


def _tushare_overall_readiness_status(
    token_configured: bool,
    endpoints: list[TushareEndpointReadiness],
) -> str:
    if not token_configured or any(item.status == "blocked" for item in endpoints):
        return "blocked"
    if any(item.status == "warning" for item in endpoints):
        return "warning"
    return "ready"


def _tushare_readiness_message(
    token_configured: bool,
    implemented_endpoint_count: int,
    scheduler_ready_count: int,
    scheduler_enabled: bool,
) -> str:
    if not token_configured:
        return "TUSHARE_TOKEN 未配置；Tushare 只能展示端点规划，不能进入抓取或调度准入。"

    if scheduler_enabled:
        return "Tushare anns_d Celery Beat 调度已显式启用；请持续关注接口权限、积分消耗和数据质量。"

    if scheduler_ready_count >= implemented_endpoint_count:
        return (
            "Tushare 端点已有成功抓取和 ok 质量记录；"
            "仍保持手动模式，调度需要单独评审后显式启用。"
        )

    return "Tushare 已可手动验证；进入调度前还需要补齐每个端点的成功抓取、字段完整性和误报样例。"


def _tushare_scheduler_policy(settings: Settings) -> str:
    if settings.tushare_anns_d_beat_enabled:
        return (
            "anns_d_celery_beat_enabled_explicitly;"
            f"interval_seconds={settings.tushare_anns_d_beat_interval_seconds}"
        )

    return "anns_d_celery_beat_disabled_by_default_enable_with_tushare_anns_d_beat_enabled"


def _tushare_daily_query_params(
    *,
    trade_date: str | None,
    ts_code: str | None,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, object] | None:
    query_params: dict[str, object] = {}
    for key, value in {
        "trade_date": trade_date,
        "ts_code": ts_code,
        "start_date": start_date,
        "end_date": end_date,
    }.items():
        if value is not None:
            query_params[key] = value

    return query_params or None


async def _record_failure(
    session: AsyncSession,
    provider_name: str,
    endpoint: str,
    started_at: datetime,
    exc: Exception,
    normalization_version: str,
) -> ProviderEndpointResult:
    await session.rollback()
    error_message = f"{exc.__class__.__name__}: {str(exc)[:800]}"

    fetch_log = ProviderFetchLog(
        provider_name=provider_name,
        endpoint=endpoint,
        status=ProviderStatus.FAILURE.value,
        fetch_started_at=started_at,
        fetch_finished_at=datetime.now(UTC),
        row_count=0,
        error_message=error_message,
        freshness="unavailable",
        confidence=0.0,
        missing_fields=[],
        normalization_version=normalization_version,
    )
    session.add(fetch_log)
    await session.flush()

    quality_check = DataQualityCheck(
        provider_name=provider_name,
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
    provider_name: str = "akshare",
    status: str | None = None,
) -> ProviderFetchLog | None:
    statement = select(ProviderFetchLog).where(
        ProviderFetchLog.provider_name == provider_name,
        ProviderFetchLog.endpoint == endpoint,
    )

    if status is not None:
        statement = statement.where(ProviderFetchLog.status == status)

    statement = statement.order_by(
        desc(ProviderFetchLog.fetch_finished_at),
        desc(ProviderFetchLog.id),
    ).limit(1)
    return await session.scalar(statement)


def _known_provider_endpoints(provider_name: str) -> dict[str, object]:
    if provider_name == "akshare":
        return AKSHARE_ENDPOINTS

    if provider_name == "tushare":
        return TUSHARE_ENDPOINTS

    return {}


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
