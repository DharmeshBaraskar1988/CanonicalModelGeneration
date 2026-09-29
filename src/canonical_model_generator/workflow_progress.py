"""Deterministic progress accounting for the regional application workflow."""


def reached_stage_count(states: list[str]) -> int:
    """Count stages reached, including partial/current work without calling it complete."""
    return sum(state in {"Complete", "Partial", "Current"} for state in states)
