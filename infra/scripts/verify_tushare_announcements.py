import argparse
import asyncio
import json

from app.providers.tushare import TushareProvider


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Tushare announcements without DB writes."
    )
    parser.add_argument(
        "--ann-date",
        help="Announcement date in YYYYMMDD format. Defaults to today.",
    )
    args = parser.parse_args()

    provider = TushareProvider()
    query_params = {"ann_date": args.ann_date} if args.ann_date else None

    try:
        dataset = await provider.fetch("anns_d", query_params=query_params)
        result = {
            "endpoint": "anns_d",
            "status": "success",
            "row_count": dataset.row_count,
            "quality": dataset.quality.model_dump(mode="json"),
            "sample": dataset.normalized_rows[:2],
        }
    except Exception as exc:
        result = {
            "endpoint": "anns_d",
            "status": "failure",
            "error": f"{exc.__class__.__name__}: {str(exc)[:800]}",
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
