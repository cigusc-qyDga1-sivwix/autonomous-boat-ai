"""Atomic numeric research reports, isolated from BOAT LAB storage."""
import json
from pathlib import Path
import tempfile


def write_report(value, output, *, inputs=()):
    destination = Path(output).resolve()
    forbidden = {"app", "live", "official-pay", "formal", "forecasts", "results"}
    if forbidden.intersection(destination.parts):
        raise ValueError("production_output_path_forbidden")
    if destination in {Path(p).resolve() for p in inputs}:
        raise ValueError("input_evidence_overwrite_forbidden")
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".vision-report-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
