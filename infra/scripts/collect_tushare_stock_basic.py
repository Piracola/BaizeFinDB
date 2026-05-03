import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.providers.service import collect_tushare_stock_basic


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await collect_tushare_stock_basic(session)

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
