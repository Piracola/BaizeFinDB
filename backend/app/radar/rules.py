from dataclasses import dataclass

from app.radar.schemas import RadarLifecycleStage, RadarPriority


@dataclass(frozen=True)
class RadarRuleResult:
    priority: RadarPriority
    lifecycle_stage: RadarLifecycleStage
    confidence: float
    reasons: list[str]


def classify_sector_movement(metrics: dict[str, object]) -> RadarRuleResult | None:
    pct_change = _float(metrics.get("pct_change"))
    leading_stock_pct_change = _float(metrics.get("leading_stock_pct_change"))
    rising_count = _int(metrics.get("rising_count"))
    falling_count = _int(metrics.get("falling_count"))
    breadth = _breadth(rising_count, falling_count)

    if pct_change >= 5 and rising_count >= 10 and breadth >= 0.65:
        return RadarRuleResult(
            priority=RadarPriority.P0,
            lifecycle_stage=_lifecycle_for(pct_change, breadth),
            confidence=0.82,
            reasons=[
                "sector_pct_change_ge_5",
                "rising_count_ge_10",
                "breadth_ge_65pct",
            ],
        )

    if pct_change >= 3 and breadth >= 0.55:
        return RadarRuleResult(
            priority=RadarPriority.P1,
            lifecycle_stage=_lifecycle_for(pct_change, breadth),
            confidence=0.68,
            reasons=["sector_pct_change_ge_3", "breadth_ge_55pct"],
        )

    if pct_change >= 1.5 and breadth >= 0.5:
        return RadarRuleResult(
            priority=RadarPriority.P2,
            lifecycle_stage=RadarLifecycleStage.IGNITION,
            confidence=0.52,
            reasons=["weak_positive_sector_move", "breadth_ge_50pct"],
        )

    if leading_stock_pct_change >= 5:
        return RadarRuleResult(
            priority=RadarPriority.P2,
            lifecycle_stage=RadarLifecycleStage.IGNITION,
            confidence=0.52,
            reasons=["leader_pct_change_ge_5"],
        )

    return None


def _lifecycle_for(pct_change: float, breadth: float) -> RadarLifecycleStage:
    if pct_change >= 6.5 and breadth >= 0.75:
        return RadarLifecycleStage.CLIMAX

    if pct_change >= 3.5 and breadth >= 0.6:
        return RadarLifecycleStage.DEVELOPING

    return RadarLifecycleStage.IGNITION


def _breadth(rising_count: int, falling_count: int) -> float:
    total = rising_count + falling_count
    if total <= 0:
        return 0.0

    return round(rising_count / total, 4)


def _float(value: object) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    if value is None:
        return 0

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
