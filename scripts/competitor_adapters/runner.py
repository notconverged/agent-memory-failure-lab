from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path

from scripts.competitor_adapters.base import AdapterRequest, to_jsonable


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(to_jsonable(value), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = json.loads(args.request.read_text(encoding="utf-8"))
    request = AdapterRequest(
        system=raw["system"],
        run_id=raw["run_id"],
        phase_id=raw["phase_id"],
        workspace=Path(raw["workspace"]),
        data_dir=Path(raw["data_dir"]),
        prompt=raw["prompt"],
    )
    try:
        module = importlib.import_module(
            f"scripts.competitor_adapters.{request.system}"
        )
        result = module.run_phase(request)
    except Exception as error:  # Preserve a structured failure for the trial log.
        result = {
            "status": "adapter_error",
            "system": request.system,
            "run_id": request.run_id,
            "phase_id": request.phase_id,
            "error_type": type(error).__name__,
            "error": str(error),
        }
    write_json(args.output, result)
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
