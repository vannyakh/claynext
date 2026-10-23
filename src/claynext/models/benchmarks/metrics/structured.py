"""JSON schema validity. Structural only; not the human 99% gate."""
from __future__ import annotations

import json
from typing import Any

from claynext.models.benchmarks.metrics.common import metric, not_scored


def schema_validity_metric(
    outputs: dict[str, str],
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if schema is None:
        return not_scored(
            "structured_output",
            "no output schema configured; structured-output rate is not scored",
        )
    from claynext.prompts.validator import schema_errors

    valid = 0
    problems: list[dict[str, Any]] = []
    for row_id, text in outputs.items():
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            problems.append({"id": row_id, "errors": ["not_json"]})
            continue
        errors = schema_errors(schema, parsed)
        if errors:
            problems.append({"id": row_id, "errors": errors})
        else:
            valid += 1
    return metric(
        "structured_output",
        method="json_schema",
        reason="structural validity only; not a human structured-output gate",
        automatic_check={"valid": valid, "n": len(outputs), "problems": problems},
    )
