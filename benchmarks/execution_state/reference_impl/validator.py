from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    feedback: str


def validate_boundary(content: str, specification: dict) -> ValidationResult:
    """Deterministic pipeline validator; it never reads benchmark gold."""

    normalized = content.casefold()
    required = [
        str(item).casefold() for item in specification.get("required_terms", [])
    ]
    terms_present = all(item in normalized for item in required)
    passed = bool(specification.get("test_passed")) and terms_present
    feedback = (
        ""
        if passed
        else str(specification.get("feedback") or "Boundary validation failed.")
    )
    return ValidationResult(passed, feedback)
