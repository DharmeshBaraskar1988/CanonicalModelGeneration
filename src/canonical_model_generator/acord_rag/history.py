"""Local persistence for independently ingested ACORD reference records."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from canonical_model_generator.acord_rag.pipeline import ACORD_ARTIFACTS

RUN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def save_acord_record(
    root: Path,
    run_id: str,
    *,
    model: dict[str, Any],
    artifacts: dict[str, bytes],
    source_content: bytes,
) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("ACORD run ID must be a UUID hex value")
    run_path = root.resolve() / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    source_name = Path(model["source"]["filename"]).name
    (run_path / source_name).write_bytes(source_content)
    (run_path / "acord-model.json").write_text(
        json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact_path = run_path / "artifacts"
    artifact_path.mkdir(exist_ok=True)
    for label, filename in ACORD_ARTIFACTS.items():
        (artifact_path / filename).write_bytes(artifacts[label])
    record = {
        "runId": run_id,
        "sourceFile": source_name,
        "referenceLabel": model["source"]["referenceLabel"],
        "referenceVersion": model["source"]["referenceVersion"],
        "sha256": model["source"]["sha256"],
    }
    (run_path / "record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return run_path


def load_acord_records(root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return records
    for run_path in sorted(root.iterdir()):
        if not run_path.is_dir() or not RUN_ID_PATTERN.fullmatch(run_path.name):
            continue
        try:
            record = json.loads((run_path / "record.json").read_text(encoding="utf-8"))
            model = json.loads((run_path / "acord-model.json").read_text(encoding="utf-8"))
            manifest = json.loads(
                (run_path / "index" / "acord-rag-manifest.json").read_text(encoding="utf-8")
            )
            artifacts = {
                label: (run_path / "artifacts" / filename).read_bytes()
                for label, filename in ACORD_ARTIFACTS.items()
            }
            records[run_path.name] = {
                "profile": record,
                "model": model,
                "artifacts": artifacts,
                "manifest": manifest,
                "storagePath": str(run_path / "index"),
            }
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return records


def delete_acord_record(root: Path, run_id: str) -> bool:
    """Delete one ACORD ingestion run directory and its index from disk."""
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("ACORD run ID must be a UUID hex value")
    resolved_root = root.resolve()
    run_path = (resolved_root / run_id).resolve()
    try:
        run_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("ACORD run path is outside the configured history root") from exc
    if not run_path.exists():
        return False
    import shutil

    shutil.rmtree(run_path)
    return True
