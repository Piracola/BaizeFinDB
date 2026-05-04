import argparse
import json
import sys
from pathlib import Path

from app.providers.tushare_anns_preflight import validate_anns_d_preflight_cases

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = ROOT_DIR / "golden_cases" / "tushare_anns_d_preflight.json"


def load_cases(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list):
        raise ValueError("preflight cases file must contain a JSON array")

    cases: list[dict[str, object]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"preflight case #{index} must be a JSON object")
        cases.append(item)
    return cases


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Offline/no-token Tushare anns_d pre-scheduling validator. "
            "Uses local sample rows and never calls live Tushare APIs."
        )
    )
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES_PATH),
        help="Path to local JSON preflight cases.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases_path = Path(args.cases)

    try:
        cases = load_cases(cases_path)
        report = validate_anns_d_preflight_cases(cases)
        output = {
            **report.to_dict(),
            "cases_path": str(cases_path),
            "mode": "offline_no_token",
        }
    except Exception as exc:
        output = {
            "status": "fail",
            "cases_path": str(cases_path),
            "mode": "offline_no_token",
            "error": f"{exc.__class__.__name__}: {str(exc)[:800]}",
        }
        print(json.dumps(output, indent=2))
        return 1

    print(json.dumps(output, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
