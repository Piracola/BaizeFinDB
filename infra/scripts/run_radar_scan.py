import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.radar.service import run_radar_scan


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await run_radar_scan(session)

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
