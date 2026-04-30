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


def test_limit_up_pool_normalization() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "序号": 1,
                "代码": "600519",
                "名称": "贵州茅台",
                "涨跌幅": 10.0,
                "最新价": 1688.0,
                "成交额": 123456789.0,
                "流通市值": 1_000_000_000.0,
                "总市值": 1_100_000_000.0,
                "换手率": 2.1,
                "封板资金": 88000000.0,
                "首次封板时间": "093001",
                "最后封板时间": "145501",
                "炸板次数": 0,
                "涨停统计": "1/1",
                "连板数": 1,
                "所属行业": "白酒",
            }
        ]
    )

    dataset = normalize_dataframe(dataframe, AKSHARE_ENDPOINTS["stock_zt_pool_em"])

    assert dataset.snapshot_type == "limit_up_pool"
    assert dataset.quality.status == DataQualityStatus.OK
    assert dataset.normalized_rows[0]["symbol"] == "600519"
    assert dataset.normalized_rows[0]["seal_amount"] == 88000000.0
    assert dataset.normalized_rows[0]["consecutive_limit_count"] == 1


def test_limit_down_pool_normalization() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "序号": 1,
                "代码": "000001",
                "名称": "平安银行",
                "涨跌幅": -10.0,
                "最新价": 9.9,
                "成交额": 50000000.0,
                "流通市值": 900000000.0,
                "总市值": 950000000.0,
                "动态市盈率": 5.2,
                "换手率": 3.3,
                "封单资金": 32000000.0,
                "最后封板时间": "145900",
                "板上成交额": 1000000.0,
                "连续跌停": 1,
                "开板次数": 2,
                "所属行业": "银行",
            }
        ]
    )

    dataset = normalize_dataframe(dataframe, AKSHARE_ENDPOINTS["stock_zt_pool_dtgc_em"])

    assert dataset.snapshot_type == "limit_down_pool"
    assert dataset.quality.status == DataQualityStatus.OK
    assert dataset.normalized_rows[0]["symbol"] == "000001"
    assert dataset.normalized_rows[0]["consecutive_limit_down_count"] == 1
    assert dataset.normalized_rows[0]["open_limit_count"] == 2


def test_broken_limit_up_pool_normalization() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "序号": 1,
                "代码": "300750",
                "名称": "宁德时代",
                "涨跌幅": 8.5,
                "最新价": 200.0,
                "涨停价": 205.0,
                "成交额": 250000000.0,
                "流通市值": 3_000_000_000.0,
                "总市值": 3_100_000_000.0,
                "换手率": 4.1,
                "涨速": -0.5,
                "首次封板时间": "101500",
                "炸板次数": 3,
                "涨停统计": "1/1",
                "振幅": 12.3,
                "所属行业": "电池",
            }
        ]
    )

    dataset = normalize_dataframe(dataframe, AKSHARE_ENDPOINTS["stock_zt_pool_zbgc_em"])

    assert dataset.snapshot_type == "broken_limit_up_pool"
    assert dataset.quality.status == DataQualityStatus.OK
    assert dataset.normalized_rows[0]["symbol"] == "300750"
    assert dataset.normalized_rows[0]["limit_up_price"] == 205.0
    assert dataset.normalized_rows[0]["break_limit_count"] == 3

