import argparse
import asyncio
import json

from app.providers.tushare import TushareProvider


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
    args = parser.parse_args()

    provider = TushareProvider()

    try:
        dataset = await provider.fetch(
            "stock_company",
            query_params={"exchange": args.exchange},
        )
        result = {
            "endpoint": "stock_company",
            "status": "success",
            "exchange": args.exchange,
            "row_count": dataset.row_count,
            "quality": dataset.quality.model_dump(mode="json"),
            "sample": dataset.normalized_rows[:2],
        }
    except Exception as exc:
        result = {
            "endpoint": "stock_company",
            "status": "failure",
            "exchange": args.exchange,
            "error": f"{exc.__class__.__name__}: {str(exc)[:800]}",
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
