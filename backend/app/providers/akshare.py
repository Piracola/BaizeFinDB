import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.providers.schemas import (
    DataQuality,
    DataQualityStatus,
    ProviderDataset,
    ProviderEndpointInfo,
)

if TYPE_CHECKING:
    import pandas as pd


NORMALIZATION_VERSION = "akshare_em_v1"


@dataclass(frozen=True)
class AkshareEndpointSpec:
    endpoint: str
    title: str
    market: str
    snapshot_type: str
    fetcher_name: str
    required_fields: tuple[str, ...]
    column_map: dict[str, str]
    use_current_date: bool = False


STOCK_COLUMN_MAP = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "latest_price",
    "涨跌幅": "pct_change",
    "涨跌额": "change_amount",
    "成交量": "volume",
    "成交额": "turnover",
    "换手率": "turnover_rate",
    "最高": "high",
    "最低": "low",
    "今开": "open",
    "昨收": "previous_close",
    "总市值": "total_market_value",
    "流通市值": "free_float_market_value",
    "涨速": "speed",
    "5分钟涨跌": "five_minute_pct_change",
}

SECTOR_COLUMN_MAP = {
    "板块代码": "sector_code",
    "板块名称": "sector_name",
    "最新价": "latest_price",
    "涨跌幅": "pct_change",
    "涨跌额": "change_amount",
    "总市值": "total_market_value",
    "换手率": "turnover_rate",
    "上涨家数": "rising_count",
    "下跌家数": "falling_count",
    "领涨股票": "leading_stock",
    "领涨股票-涨跌幅": "leading_stock_pct_change",
}

LIMIT_UP_COLUMN_MAP = {
    "序号": "rank",
    "代码": "symbol",
    "名称": "name",
    "涨跌幅": "pct_change",
    "最新价": "latest_price",
    "成交额": "turnover",
    "流通市值": "free_float_market_value",
    "总市值": "total_market_value",
    "换手率": "turnover_rate",
    "封板资金": "seal_amount",
    "首次封板时间": "first_limit_time",
    "最后封板时间": "last_limit_time",
    "炸板次数": "break_limit_count",
    "涨停统计": "limit_up_statistics",
    "连板数": "consecutive_limit_count",
    "所属行业": "industry",
}

LIMIT_DOWN_COLUMN_MAP = {
    "序号": "rank",
    "代码": "symbol",
    "名称": "name",
    "涨跌幅": "pct_change",
    "最新价": "latest_price",
    "成交额": "turnover",
    "流通市值": "free_float_market_value",
    "总市值": "total_market_value",
    "动态市盈率": "dynamic_pe",
    "换手率": "turnover_rate",
    "封单资金": "seal_amount",
    "最后封板时间": "last_limit_time",
    "板上成交额": "limit_board_turnover",
    "连续跌停": "consecutive_limit_down_count",
    "开板次数": "open_limit_count",
    "所属行业": "industry",
}

BROKEN_LIMIT_UP_COLUMN_MAP = {
    "序号": "rank",
    "代码": "symbol",
    "名称": "name",
    "涨跌幅": "pct_change",
    "最新价": "latest_price",
    "涨停价": "limit_up_price",
    "成交额": "turnover",
    "流通市值": "free_float_market_value",
    "总市值": "total_market_value",
    "换手率": "turnover_rate",
    "涨速": "speed",
    "首次封板时间": "first_limit_time",
    "炸板次数": "break_limit_count",
    "涨停统计": "limit_up_statistics",
    "振幅": "amplitude",
    "所属行业": "industry",
}

AKSHARE_ENDPOINTS: dict[str, AkshareEndpointSpec] = {
    "stock_zh_a_spot_em": AkshareEndpointSpec(
        endpoint="stock_zh_a_spot_em",
        title="A股实时行情",
        market="A_SHARE",
        snapshot_type="stock_spot",
        fetcher_name="stock_zh_a_spot_em",
        required_fields=("代码", "名称", "最新价", "涨跌幅", "成交额", "换手率"),
        column_map=STOCK_COLUMN_MAP,
    ),
    "stock_board_industry_name_em": AkshareEndpointSpec(
        endpoint="stock_board_industry_name_em",
        title="行业板块行情",
        market="A_SHARE",
        snapshot_type="sector_industry",
        fetcher_name="stock_board_industry_name_em",
        required_fields=("板块代码", "板块名称", "涨跌幅", "上涨家数", "下跌家数"),
        column_map=SECTOR_COLUMN_MAP,
    ),
    "stock_board_concept_name_em": AkshareEndpointSpec(
        endpoint="stock_board_concept_name_em",
        title="概念板块行情",
        market="A_SHARE",
        snapshot_type="sector_concept",
        fetcher_name="stock_board_concept_name_em",
        required_fields=("板块代码", "板块名称", "涨跌幅", "上涨家数", "下跌家数"),
        column_map=SECTOR_COLUMN_MAP,
    ),
    "stock_zt_pool_em": AkshareEndpointSpec(
        endpoint="stock_zt_pool_em",
        title="涨停股池",
        market="A_SHARE",
        snapshot_type="limit_up_pool",
        fetcher_name="stock_zt_pool_em",
        required_fields=(
            "代码",
            "名称",
            "涨跌幅",
            "最新价",
            "成交额",
            "封板资金",
            "首次封板时间",
            "最后封板时间",
            "炸板次数",
            "连板数",
            "所属行业",
        ),
        column_map=LIMIT_UP_COLUMN_MAP,
        use_current_date=True,
    ),
    "stock_zt_pool_dtgc_em": AkshareEndpointSpec(
        endpoint="stock_zt_pool_dtgc_em",
        title="跌停股池",
        market="A_SHARE",
        snapshot_type="limit_down_pool",
        fetcher_name="stock_zt_pool_dtgc_em",
        required_fields=(
            "代码",
            "名称",
            "涨跌幅",
            "最新价",
            "成交额",
            "封单资金",
            "最后封板时间",
            "连续跌停",
            "开板次数",
            "所属行业",
        ),
        column_map=LIMIT_DOWN_COLUMN_MAP,
        use_current_date=True,
    ),
    "stock_zt_pool_zbgc_em": AkshareEndpointSpec(
        endpoint="stock_zt_pool_zbgc_em",
        title="炸板股池",
        market="A_SHARE",
        snapshot_type="broken_limit_up_pool",
        fetcher_name="stock_zt_pool_zbgc_em",
        required_fields=(
            "代码",
            "名称",
            "涨跌幅",
            "最新价",
            "涨停价",
            "成交额",
            "首次封板时间",
            "炸板次数",
            "所属行业",
        ),
        column_map=BROKEN_LIMIT_UP_COLUMN_MAP,
        use_current_date=True,
    ),
}


class AkshareClient:
    def __init__(self, module_loader: Callable[[], object] | None = None) -> None:
        self._module_loader = module_loader or self._load_akshare

    @staticmethod
    def _load_akshare() -> object:
        import akshare as ak

        return ak

    def fetch_dataframe(self, fetcher_name: str, **kwargs: object) -> "pd.DataFrame":
        akshare_module = self._module_loader()
        fetcher = getattr(akshare_module, fetcher_name)
        return fetcher(**kwargs)


class AkshareProvider:
    provider_name = "akshare"

    def __init__(self, client: AkshareClient | None = None) -> None:
        self.client = client or AkshareClient()

    async def fetch(self, endpoint: str) -> ProviderDataset:
        spec = AKSHARE_ENDPOINTS[endpoint]
        dataframe = await asyncio.to_thread(
            self.client.fetch_dataframe,
            spec.fetcher_name,
            **_fetcher_kwargs(spec),
        )
        return normalize_dataframe(dataframe, spec)


def list_akshare_endpoints() -> list[ProviderEndpointInfo]:
    return [
        ProviderEndpointInfo(
            endpoint=spec.endpoint,
            title=spec.title,
            market=spec.market,
            snapshot_type=spec.snapshot_type,
            required_fields=list(spec.required_fields),
        )
        for spec in AKSHARE_ENDPOINTS.values()
    ]


def normalize_dataframe(dataframe: "pd.DataFrame", spec: AkshareEndpointSpec) -> ProviderDataset:
    missing_fields = [field for field in spec.required_fields if field not in dataframe.columns]
    available_columns = [column for column in spec.column_map if column in dataframe.columns]

    normalized_frame = dataframe[available_columns].rename(columns=spec.column_map).copy()
    normalized_frame["snapshot_type"] = spec.snapshot_type
    normalized_rows = _dataframe_to_records(normalized_frame)

    row_count = len(dataframe)
    quality_status = _quality_status(row_count, missing_fields)
    confidence = _confidence(row_count, len(spec.required_fields), len(missing_fields))

    return ProviderDataset(
        provider_name="akshare",
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
        quality=DataQuality(
            status=quality_status,
            confidence=confidence,
            freshness="unknown_source_time",
            missing_fields=missing_fields,
        ),
    )


def _fetcher_kwargs(spec: AkshareEndpointSpec) -> dict[str, object]:
    if not spec.use_current_date:
        return {}

    return {"date": datetime.now(UTC).strftime("%Y%m%d")}


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

