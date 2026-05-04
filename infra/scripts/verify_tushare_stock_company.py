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

ENDPOINT = "stock_company"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Tushare stock_company without DB writes."
    )
    parser.add_argument(
        "--exchange",
        choices=("SSE", "SZSE", "BSE"),
        default="SZSE",
        help="Exchange code. Defaults to SZSE.",
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
    query_params = {"exchange": args.exchange}
    report = None

    try:
        dataset = await provider.fetch(
            ENDPOINT,
            query_params=query_params,
        )
        report = build_success_report(
            endpoint=ENDPOINT,
            dataset=dataset,
            query_params=query_params,
            max_sample_rows=args.max_sample_rows,
            extra_fields={"exchange": args.exchange},
        )
        result = (
            report
            if args.json_output
            else build_legacy_success_result(
                endpoint=ENDPOINT,
                dataset=dataset,
                extra_fields={"exchange": args.exchange},
            )
        )
    except Exception as exc:
        report = build_failure_report(
            endpoint=ENDPOINT,
            exc=exc,
            query_params=query_params,
            extra_fields={"exchange": args.exchange},
        )
        result = (
            report
            if args.json_output
            else build_legacy_failure_result(
                endpoint=ENDPOINT,
                exc=exc,
                extra_fields={"exchange": args.exchange},
            )
        )

    if args.json_output:
        write_json_report(Path(args.json_output), report)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
