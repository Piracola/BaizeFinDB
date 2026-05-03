from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.providers.schemas import TushareEndpointInfo, TushareProviderStatusResponse


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


TUSHARE_ENDPOINTS: dict[str, TushareEndpointSpec] = {
    "anns_d": TushareEndpointSpec(
        endpoint="anns_d",
        title="公告快讯",
        market="A_SHARE",
        snapshot_type="announcements",
        required_fields=("ann_date", "ts_code", "title"),
        purpose="补充重大公告、风险事件和持仓/自选相关催化。",
        permission_note="Tushare Pro 接口，真实抓取前需要 token 和对应权限。",
    ),
    "stock_company": TushareEndpointSpec(
        endpoint="stock_company",
        title="上市公司基本信息",
        market="A_SHARE",
        snapshot_type="stock_company",
        required_fields=("ts_code", "chairman", "manager", "main_business"),
        purpose="补充主体画像、主营业务和后续报告上下文。",
        permission_note="Tushare Pro 接口，真实抓取前需要 token 和对应权限。",
    ),
    "stock_basic": TushareEndpointSpec(
        endpoint="stock_basic",
        title="股票基础信息",
        market="A_SHARE",
        snapshot_type="stock_basic",
        required_fields=("ts_code", "symbol", "name", "market", "list_date"),
        purpose="补充证券主数据，后续用于代码映射和跨源标准化。",
        permission_note="Tushare Pro 接口，真实抓取前需要 token 和对应权限。",
    ),
}


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
