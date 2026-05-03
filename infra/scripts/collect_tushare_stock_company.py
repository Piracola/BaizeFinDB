import argparse
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.providers.service import collect_tushare_stock_company


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect Tushare stock_company into provider snapshots."
    )
    parser.add_argument(
        "--exchange",
        choices=("SSE", "SZSE", "BSE"),
        default="SZSE",
        help="Exchange code. Defaults to SZSE.",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        result = await collect_tushare_stock_company(session, exchange=args.exchange)

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
