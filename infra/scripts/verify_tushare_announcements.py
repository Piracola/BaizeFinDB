import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.providers.schemas import ProviderDataset
from app.providers.tushare import TushareProvider
from app.providers.tushare_verify_evidence import (
    DEFAULT_MAX_SAMPLE_ROWS,
    sanitize_error,
    sanitize_normalized_row,
    write_json_report,
)
from app.providers.tushare_verify_evidence import (
    build_failure_report as build_evidence_failure_report,
)
from app.providers.tushare_verify_evidence import (
    build_legacy_failure_result as build_evidence_legacy_failure_result,
)
from app.providers.tushare_verify_evidence import (
    build_legacy_success_result as build_evidence_legacy_success_result,
)
from app.providers.tushare_verify_evidence import (
    build_success_report as build_evidence_success_report,
)

ENDPOINT = "anns_d"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Tushare announcements without DB writes."
    )
    parser.add_argument(
        "--ann-date",
        help="Announcement date in YYYYMMDD format. Defaults to today.",
    )
    parser.add_argument(
        "--json-output",
        help="Optional path for a sanitized JSON evidence report.",
    )
    parser.add_argument(
        "--max-sample-rows",
        type=int,
        default=DEFAULT_MAX_SAMPLE_ROWS,
        help="Maximum sanitized normalized rows to include in the report.",
    )
    args = parser.parse_args()

    provider = TushareProvider()
    query_params = {"ann_date": args.ann_date} if args.ann_date else None

    try:
        dataset = await provider.fetch(ENDPOINT, query_params=query_params)
        report = build_success_report(
            dataset=dataset,
            ann_date=args.ann_date,
            max_sample_rows=args.max_sample_rows,
        )
        result = (
            report
            if args.json_output
            else build_legacy_success_result(dataset=dataset)
        )
    except Exception as exc:
        report = build_failure_report(exc=exc, ann_date=args.ann_date)
        result = report if args.json_output else build_legacy_failure_result(exc=exc)

    if args.json_output:
        write_json_report(Path(args.json_output), report)

    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_success_report(
    dataset: ProviderDataset,
    ann_date: str | None,
    max_sample_rows: int = DEFAULT_MAX_SAMPLE_ROWS,
) -> dict[str, Any]:
    return build_evidence_success_report(
        endpoint=ENDPOINT,
        dataset=dataset,
        query_params={"ann_date": ann_date} if ann_date else {},
        max_sample_rows=max_sample_rows,
        extra_fields={
            "ann_date": ann_date or _infer_ann_date(dataset.normalized_rows),
        },
    )


def build_failure_report(exc: Exception, ann_date: str | None) -> dict[str, Any]:
    return build_evidence_failure_report(
        endpoint=ENDPOINT,
        exc=exc,
        query_params={"ann_date": ann_date} if ann_date else {},
        extra_fields={
            "ann_date": ann_date,
        },
    )


def build_legacy_success_result(dataset: ProviderDataset) -> dict[str, Any]:
    return build_evidence_legacy_success_result(endpoint=ENDPOINT, dataset=dataset)


def build_legacy_failure_result(exc: Exception) -> dict[str, Any]:
    return build_evidence_legacy_failure_result(endpoint=ENDPOINT, exc=exc)


def _infer_ann_date(rows: list[dict[str, object]]) -> str | None:
    for row in rows:
        value = row.get("ann_date")
        if isinstance(value, str) and value:
            return value
    return None


_sanitize_normalized_row = sanitize_normalized_row
_sanitize_error = sanitize_error


if __name__ == "__main__":
    asyncio.run(main())
