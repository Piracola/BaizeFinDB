import asyncio
import json

from app.providers.tushare import TushareProvider


async def main() -> None:
    provider = TushareProvider()

    try:
        dataset = await provider.fetch("stock_basic")
        result = {
            "endpoint": "stock_basic",
            "status": "success",
            "row_count": dataset.row_count,
            "quality": dataset.quality.model_dump(mode="json"),
            "sample": dataset.normalized_rows[:2],
        }
    except Exception as exc:
        result = {
            "endpoint": "stock_basic",
            "status": "failure",
            "error": f"{exc.__class__.__name__}: {str(exc)[:800]}",
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
