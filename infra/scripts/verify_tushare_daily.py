import argparse
import asyncio
import json
from pathlib import Path

from app.providers.tushare import TushareProvider
from app.providers.tushare_verify_evidence import (
    DEFAULT_MAX_SAMPLE_ROWS,
    build_failure_report,
    build_legacy_failure_result,
    build_legacy_success_result,
    build_success_report,
    write_json_report,
)

ENDPOINT = "daily"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Tushare daily without DB writes."
    )
    parser.add_argument(
        "--trade-date",
        help="Trade date in YYYYMMDD format. Defaults to today when no query is passed.",
    )
    parser.add_argument(
        "--ts-code",
        help="Tushare stock code, e.g. 000001.SZ. Comma-separated values are supported.",
    )
    parser.add_argument(
        "--start-date",
        help="Start date in YYYYMMDD format. Requires --end-date and --ts-code.",
    )
    parser.add_argument(
        "--end-date",
        help="End date in YYYYMMDD format. Requires --start-date and --ts-code.",
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
    query_params = _daily_query_params(
        trade_date=args.trade_date,
        ts_code=args.ts_code,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    _validate_daily_query(parser, query_params)

    provider = TushareProvider()
    report = None

    try:
        dataset = await provider.fetch(ENDPOINT, query_params=query_params)
        report = build_success_report(
            endpoint=ENDPOINT,
            dataset=dataset,
            query_params=query_params,
            max_sample_rows=args.max_sample_rows,
        )
        result = (
            report
            if args.json_output
            else build_legacy_success_result(endpoint=ENDPOINT, dataset=dataset)
        )
    except Exception as exc:
        report = build_failure_report(endpoint=ENDPOINT, exc=exc, query_params=query_params)
        result = (
            report
            if args.json_output
            else build_legacy_failure_result(endpoint=ENDPOINT, exc=exc)
        )

    if args.json_output:
        write_json_report(Path(args.json_output), report)

    print(json.dumps(result, ensure_ascii=False, indent=2))


def _daily_query_params(
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
        if value:
            query_params[key] = value

    return query_params or None


def _validate_daily_query(
    parser: argparse.ArgumentParser,
    query_params: dict[str, object] | None,
) -> None:
    values = query_params or {}
    if "trade_date" in values and ("start_date" in values or "end_date" in values):
        parser.error("--trade-date cannot be combined with --start-date/--end-date")
    if ("start_date" in values) != ("end_date" in values):
        parser.error("--start-date and --end-date must be provided together")
    if "ts_code" not in values and ("start_date" in values or "end_date" in values):
        parser.error("--ts-code is required when using --start-date/--end-date")


if __name__ == "__main__":
    asyncio.run(main())
