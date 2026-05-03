import pandas as pd

from app.providers.schemas import DataQualityStatus
from app.providers.tushare import TUSHARE_ENDPOINTS, TushareProvider, normalize_dataframe


class FakeTushareClient:
    def __init__(self, dataframe: pd.DataFrame) -> None:
        self.dataframe = dataframe
        self.calls: list[tuple[str, dict[str, object]]] = []

    def fetch_dataframe(self, endpoint: str, **kwargs: object) -> pd.DataFrame:
        self.calls.append((endpoint, kwargs))
        return self.dataframe


def test_stock_basic_normalization() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "ts_code": "600000.SH",
                "symbol": "600000",
                "name": "浦发银行",
                "area": "上海",
                "industry": "银行",
                "market": "主板",
                "exchange": "SSE",
                "list_status": "L",
                "list_date": "19991110",
                "is_hs": "H",
            }
        ]
    )

    dataset = normalize_dataframe(dataframe, TUSHARE_ENDPOINTS["stock_basic"])

    assert dataset.provider_name == "tushare"
    assert dataset.endpoint == "stock_basic"
    assert dataset.snapshot_type == "stock_basic"
    assert dataset.row_count == 1
    assert dataset.quality.status == DataQualityStatus.OK
    assert dataset.quality.freshness == "reference_data"
    assert dataset.normalized_rows[0]["ts_code"] == "600000.SH"
    assert dataset.normalized_rows[0]["symbol"] == "600000"


def test_stock_basic_missing_required_fields_marks_dataset_degraded() -> None:
    dataframe = pd.DataFrame([{"ts_code": "600000.SH", "symbol": "600000"}])

    dataset = normalize_dataframe(dataframe, TUSHARE_ENDPOINTS["stock_basic"])

    assert dataset.quality.status == DataQualityStatus.DEGRADED
    assert "name" in dataset.quality.missing_fields
    assert dataset.quality.confidence < 0.95


def test_announcements_normalization() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "ann_date": "20260503",
                "ts_code": "600000.SH",
                "name": "浦发银行",
                "title": "董事会决议公告",
                "url": "https://example.test/notice.pdf",
                "rec_time": "2026-05-03 20:00:00",
            }
        ]
    )

    dataset = normalize_dataframe(dataframe, TUSHARE_ENDPOINTS["anns_d"])

    assert dataset.endpoint == "anns_d"
    assert dataset.snapshot_type == "announcements"
    assert dataset.quality.status == DataQualityStatus.OK
    assert dataset.quality.freshness == "dated_event_data"
    assert dataset.normalized_rows[0]["ann_date"] == "20260503"
    assert dataset.normalized_rows[0]["title"] == "董事会决议公告"


async def test_tushare_provider_fetches_stock_basic_with_expected_query() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "market": "主板",
                "list_date": "19910403",
            }
        ]
    )
    client = FakeTushareClient(dataframe)
    provider = TushareProvider(client=client)

    dataset = await provider.fetch("stock_basic")

    assert dataset.endpoint == "stock_basic"
    assert client.calls == [
        (
            "stock_basic",
            {
                "exchange": "",
                "list_status": "L",
                "fields": (
                    "ts_code,symbol,name,area,industry,market,exchange,"
                    "list_status,list_date,is_hs"
                ),
            },
        )
    ]


async def test_tushare_provider_fetches_announcements_with_date_query() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "ann_date": "20260503",
                "ts_code": "000001.SZ",
                "title": "年度权益分派实施公告",
            }
        ]
    )
    client = FakeTushareClient(dataframe)
    provider = TushareProvider(client=client)

    dataset = await provider.fetch("anns_d", query_params={"ann_date": "20260503"})

    assert dataset.endpoint == "anns_d"
    assert client.calls == [
        (
            "anns_d",
            {
                "ann_date": "20260503",
                "fields": "ann_date,ts_code,name,title,url,rec_time",
            },
        )
    ]
