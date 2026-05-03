import argparse
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.providers.service import collect_tushare_announcements


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect Tushare announcements into provider snapshots."
    )
    parser.add_argument(
        "--ann-date",
        help="Announcement date in YYYYMMDD format. Defaults to today.",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        result = await collect_tushare_announcements(session, ann_date=args.ann_date)

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
