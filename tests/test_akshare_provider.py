import pandas as pd

from app.providers.akshare import AKSHARE_ENDPOINTS, normalize_dataframe
from app.providers.schemas import DataQualityStatus


def test_stock_spot_normalization() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "代码": "600000",
                "名称": "浦发银行",
                "最新价": 8.12,
                "涨跌幅": 1.25,
                "成交额": 12345678.0,
                "换手率": 0.8,
            }
        ]
    )

    dataset = normalize_dataframe(dataframe, AKSHARE_ENDPOINTS["stock_zh_a_spot_em"])

    assert dataset.row_count == 1
    assert dataset.quality.status == DataQualityStatus.OK
    assert dataset.normalized_rows[0]["symbol"] == "600000"
    assert dataset.normalized_rows[0]["name"] == "浦发银行"


def test_missing_required_fields_marks_dataset_degraded() -> None:
    dataframe = pd.DataFrame([{"代码": "600000", "名称": "浦发银行"}])

    dataset = normalize_dataframe(dataframe, AKSHARE_ENDPOINTS["stock_zh_a_spot_em"])

    assert dataset.quality.status == DataQualityStatus.DEGRADED
    assert "成交额" in dataset.quality.missing_fields
    assert dataset.quality.confidence < 0.95

