from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "runs" / "competitor-trials"
WEIGHTS = {
    "capture_completeness": 20,
    "structure_type_fidelity": 15,
    "lifecycle_correctness": 20,
    "provenance_traceability": 15,
    "fresh_session_retrieval": 15,
    "behavior_correctness": 10,
    "controllability": 5,
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temporary, path)


def score(run_dir: Path) -> dict[str, Any]:
    manifest = load(run_dir / "manifest.json")
    samples: dict[str, list[float]] = {key: [] for key in WEIGHTS}
    for observation in sorted(run_dir.glob("phases/*/observation.json")):
        checks = load(observation).get("checks", {})
        for key in WEIGHTS:
            value = checks.get(key)
            if value is not None:
                if not isinstance(value, int | float) or not 0 <= value <= 1:
                    raise ValueError(f"{observation}: {key} must be between 0 and 1")
                samples[key].append(float(value))
    values: dict[str, float | None] = {
        key: (sum(items) / len(items) if items else None)
        for key, items in samples.items()
    }
    dimensions = {
        key: round((values[key] or 0.0) * weight, 2) for key, weight in WEIGHTS.items()
    }
    unknown = [key for key, value in values.items() if value is None]
    payload = {
        "system": manifest["system"],
        "run_id": manifest["run_id"],
        "total": round(sum(dimensions.values()), 2),
        "dimensions": dimensions,
        "raw_values": values,
        "sample_counts": {key: len(items) for key, items in samples.items()},
        "unknown": unknown,
        "interpretation": (
            "Exploratory score; UNKNOWN dimensions receive zero and remain explicit."
        ),
    }
    write(run_dir / "final" / "score.json", payload)
    write(
        run_dir / "final" / "comparison-row.json",
        {
            "system": payload["system"],
            "run_id": payload["run_id"],
            "total": payload["total"],
            "unknown_count": len(unknown),
        },
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", default="round-01")
    parser.add_argument("--system", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    run_dir = RESULTS / args.round / args.system / args.run_id
    try:
        result = score(run_dir)
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
