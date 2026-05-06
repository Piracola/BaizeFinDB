import argparse
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.providers.service import collect_tushare_daily


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect Tushare daily into provider snapshots."
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
    args = parser.parse_args()
    _validate_daily_args(parser, args)

    async with AsyncSessionLocal() as session:
        result = await collect_tushare_daily(
            session,
            trade_date=args.trade_date,
            ts_code=args.ts_code,
            start_date=args.start_date,
            end_date=args.end_date,
        )

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


def _validate_daily_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.trade_date and (args.start_date or args.end_date):
        parser.error("--trade-date cannot be combined with --start-date/--end-date")
    if bool(args.start_date) != bool(args.end_date):
        parser.error("--start-date and --end-date must be provided together")
    if not args.ts_code and (args.start_date or args.end_date):
        parser.error("--ts-code is required when using --start-date/--end-date")


if __name__ == "__main__":
    asyncio.run(main())
