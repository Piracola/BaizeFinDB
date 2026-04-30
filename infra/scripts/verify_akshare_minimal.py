import argparse
import asyncio
import json

from app.providers.akshare import AKSHARE_ENDPOINTS, AkshareProvider


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify minimal AKShare endpoints without DB writes."
    )
    parser.add_argument(
        "--endpoint",
        choices=AKSHARE_ENDPOINTS.keys(),
        action="append",
        help="Endpoint to verify. Defaults to all minimal endpoints.",
    )
    args = parser.parse_args()

    provider = AkshareProvider()
    endpoints = args.endpoint or list(AKSHARE_ENDPOINTS)
    results = []

    for endpoint in endpoints:
        try:
            dataset = await provider.fetch(endpoint)
            results.append(
                {
                    "endpoint": endpoint,
                    "status": "success",
                    "row_count": dataset.row_count,
                    "quality": dataset.quality.model_dump(mode="json"),
                    "sample": dataset.normalized_rows[:2],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "endpoint": endpoint,
                    "status": "failure",
                    "error": f"{exc.__class__.__name__}: {str(exc)[:800]}",
                }
            )

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
