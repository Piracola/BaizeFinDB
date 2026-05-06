import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.config import Settings, get_settings
from app.providers.schemas import (
    DataQuality,
    DataQualityStatus,
    ProviderDataset,
    TushareEndpointInfo,
    TushareProviderStatusResponse,
)

if TYPE_CHECKING:
    import pandas as pd


NORMALIZATION_VERSION = "tushare_pro_v1"


@dataclass(frozen=True)
class TushareEndpointSpec:
    endpoint: str
    title: str
    market: str
    snapshot_type: str
    required_fields: tuple[str, ...]
    purpose: str
    permission_note: str
    implemented: bool = False
    fields: tuple[str, ...] = ()
    query_params: dict[str, object] | None = None
    freshness: str = "reference_data"


TUSHARE_ENDPOINTS: dict[str, TushareEndpointSpec] = {
    "daily": TushareEndpointSpec(
        endpoint="daily",
        title="A股日线行情",
        market="A_SHARE",
        snapshot_type="daily_bar",
        required_fields=(
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "vol",
            "amount",
        ),
        purpose="提供 A 股未复权日线 OHLCV 行情，作为后续雷达、复盘和报告的基础行情源。",
        permission_note=(
            "Tushare Pro daily 接口；可按单个交易日抓全市场，或按股票代码抓区间。"
        ),
        implemented=True,
        fields=(
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
        ),
        freshness="daily_market_data",
    ),
    "anns_d": TushareEndpointSpec(
        endpoint="anns_d",
        title="公告快讯",
        market="A_SHARE",
        snapshot_type="announcements",
        required_fields=("ann_date", "ts_code", "title"),
        purpose="补充重大公告、风险事件和持仓/自选相关催化。",
        permission_note="Tushare Pro 接口，真实抓取前需要 token 和对应权限。",
        implemented=True,
        fields=("ann_date", "ts_code", "name", "title", "url", "rec_time"),
        freshness="dated_event_data",
    ),
    "stock_company": TushareEndpointSpec(
        endpoint="stock_company",
        title="上市公司基本信息",
        market="A_SHARE",
        snapshot_type="stock_company",
        required_fields=("ts_code", "chairman", "manager", "main_business"),
        purpose="补充主体画像、主营业务和后续报告上下文。",
        permission_note="Tushare Pro 接口，真实抓取前需要 token 和对应权限。",
        implemented=True,
        fields=(
            "ts_code",
            "exchange",
            "chairman",
            "manager",
            "secretary",
            "reg_capital",
            "setup_date",
            "province",
            "city",
            "website",
            "email",
            "office",
            "employees",
            "main_business",
            "business_scope",
        ),
        query_params={"exchange": "SZSE"},
    ),
    "stock_basic": TushareEndpointSpec(
        endpoint="stock_basic",
        title="股票基础信息",
        market="A_SHARE",
        snapshot_type="stock_basic",
        required_fields=("ts_code", "symbol", "name", "market", "list_date"),
        purpose="补充证券主数据，后续用于代码映射和跨源标准化。",
        permission_note="Tushare Pro 接口，真实抓取前需要 token 和对应权限。",
        implemented=True,
        fields=(
            "ts_code",
            "symbol",
            "name",
            "area",
            "industry",
            "market",
            "exchange",
            "list_status",
            "list_date",
            "is_hs",
        ),
        query_params={"exchange": "", "list_status": "L"},
    ),
}


class TushareClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def fetch_dataframe(self, endpoint: str, **kwargs: object) -> "pd.DataFrame":
        import tushare as ts

        pro_client = ts.pro_api(self.token)
        fetcher = getattr(pro_client, endpoint)
        return fetcher(**kwargs)


class TushareProvider:
    provider_name = "tushare"

    def __init__(
        self,
        client: TushareClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.client = client
        self.settings = settings or get_settings()

    async def fetch(
        self,
        endpoint: str,
        query_params: dict[str, object] | None = None,
    ) -> ProviderDataset:
        spec = TUSHARE_ENDPOINTS[endpoint]
        if not spec.implemented:
            raise NotImplementedError(f"tushare endpoint is not implemented: {endpoint}")

        client = self.client or TushareClient(self._require_token())
        dataframe = await asyncio.to_thread(
            client.fetch_dataframe,
            spec.endpoint,
            **_fetcher_kwargs(spec, query_params),
        )
        return normalize_dataframe(dataframe, spec)

    def _require_token(self) -> str:
        token = self.settings.tushare_token
        if token is None or not token.strip():
            raise RuntimeError("TUSHARE_TOKEN is not configured")

        return token.strip()


def list_tushare_endpoints() -> list[TushareEndpointInfo]:
    return [
        TushareEndpointInfo(
            endpoint=spec.endpoint,
            title=spec.title,
            market=spec.market,
            snapshot_type=spec.snapshot_type,
            required_fields=list(spec.required_fields),
            purpose=spec.purpose,
            permission_note=spec.permission_note,
            implemented=spec.implemented,
        )
        for spec in TUSHARE_ENDPOINTS.values()
    ]


def get_tushare_provider_status(
    settings: Settings | None = None,
) -> TushareProviderStatusResponse:
    active_settings = settings or get_settings()
    token_configured = active_settings.tushare_token_configured
    implemented_endpoint_count = sum(1 for spec in TUSHARE_ENDPOINTS.values() if spec.implemented)

    return TushareProviderStatusResponse(
        token_configured=token_configured,
        fetch_enabled=implemented_endpoint_count > 0 and token_configured,
        endpoint_count=len(TUSHARE_ENDPOINTS),
        implemented_endpoint_count=implemented_endpoint_count,
        status="configured" if token_configured else "not_configured",
        message=_status_message(token_configured, implemented_endpoint_count),
    )


def _status_message(token_configured: bool, implemented_endpoint_count: int) -> str:
    if implemented_endpoint_count <= 0:
        return "Tushare provider shell is registered; real fetch is not implemented yet."

    if not token_configured:
        return "TUSHARE_TOKEN is required before enabling Tushare fetch."

    return "Tushare token is configured and implemented endpoints can be enabled."


def normalize_dataframe(dataframe: "pd.DataFrame", spec: TushareEndpointSpec) -> ProviderDataset:
    missing_fields = [field for field in spec.required_fields if field not in dataframe.columns]
    selected_columns = [field for field in spec.fields if field in dataframe.columns]
    normalized_rows = _dataframe_to_records(dataframe[selected_columns].copy())
    row_count = len(dataframe)

    return ProviderDataset(
        provider_name="tushare",
        endpoint=spec.endpoint,
        market=spec.market,
        snapshot_type=spec.snapshot_type,
        collected_at=datetime.now(UTC),
        row_count=row_count,
        raw_summary={
            "columns": list(dataframe.columns),
            "sample": _dataframe_to_records(dataframe.head(5)),
        },
        normalized_rows=normalized_rows,
        normalization_version=NORMALIZATION_VERSION,
        source_time=_source_time(dataframe, spec),
        quality=DataQuality(
            status=_quality_status(row_count, missing_fields),
            confidence=_confidence(row_count, len(spec.required_fields), len(missing_fields)),
            freshness=spec.freshness,
            missing_fields=missing_fields,
        ),
    )


def _fetcher_kwargs(
    spec: TushareEndpointSpec,
    query_params: dict[str, object] | None = None,
) -> dict[str, object]:
    kwargs = dict(spec.query_params or {})
    kwargs.update(query_params or {})

    if spec.endpoint == "anns_d" and "ann_date" not in kwargs:
        kwargs["ann_date"] = datetime.now(UTC).strftime("%Y%m%d")

    if spec.endpoint == "daily" and not _has_daily_query(kwargs):
        kwargs["trade_date"] = datetime.now(UTC).strftime("%Y%m%d")

    if spec.fields:
        kwargs["fields"] = ",".join(spec.fields)

    return kwargs


def _has_daily_query(kwargs: dict[str, object]) -> bool:
    return any(
        str(kwargs.get(name) or "").strip()
        for name in ("trade_date", "ts_code", "start_date", "end_date")
    )


def _source_time(dataframe: "pd.DataFrame", spec: TushareEndpointSpec) -> datetime | None:
    if spec.endpoint != "daily" or dataframe.empty or "trade_date" not in dataframe.columns:
        return None

    trade_dates = [
        str(value)
        for value in dataframe["trade_date"].dropna().tolist()
        if str(value).strip()
    ]
    if not trade_dates:
        return None

    try:
        return datetime.strptime(max(trade_dates), "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _dataframe_to_records(dataframe: "pd.DataFrame") -> list[dict[str, object]]:
    if dataframe.empty:
        return []

    json_text = dataframe.to_json(orient="records", force_ascii=False, date_format="iso")
    return json.loads(json_text)


def _quality_status(row_count: int, missing_fields: list[str]) -> DataQualityStatus:
    if row_count <= 0 or missing_fields:
        return DataQualityStatus.DEGRADED

    return DataQualityStatus.OK


def _confidence(row_count: int, required_count: int, missing_count: int) -> float:
    if row_count <= 0:
        return 0.25

    if missing_count <= 0:
        return 0.95

    present_ratio = max(required_count - missing_count, 0) / max(required_count, 1)
    return round(max(0.45, present_ratio), 2)
