"""Validate skill inputs and model outputs against their contracts.

Every check runs the JSON Schema subset validator (type, required,
properties, additionalProperties, items, min/maxItems, min/maxLength,
pattern, minimum/maximum, enum). When Pydantic is installed the typed
contract from ``contracts.py`` also runs and supplies the normalized data.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from claynext.prompts.contracts import CONTRACTS

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: Any = None
    engine: str = "jsonschema"

    def summary(self, limit: int = 5) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "engine": self.engine,
            "errors": self.errors[:limit],
            "warnings": self.warnings[:limit],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


def schema_errors(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    want = schema.get("type")
    if want:
        kinds = want if isinstance(want, list) else [want]
        if not any(_TYPES[k](value) for k in kinds):
            return [f"{path}: expected {'|'.join(kinds)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: does not match {schema['pattern']}")
    if _TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} item(s)")
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                errors.extend(schema_errors(schema["items"], item, f"{path}[{i}]"))
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if key not in value:
                errors.append(f"{path}: missing {key!r}")
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                errors.extend(schema_errors(props[key], item, f"{path}.{key}"))
            elif extra is False:
                errors.append(f"{path}: unexpected {key!r}")
            elif isinstance(extra, dict):
                errors.extend(schema_errors(extra, item, f"{path}.{key}"))
    return errors


def validate(
    schema: dict[str, Any],
    value: Any,
    *,
    contract: str = "",
    use_pydantic: bool = True,
) -> ValidationResult:
    errors = schema_errors(schema, value)
    model = CONTRACTS.get(contract) if use_pydantic and contract else None
    if errors or model is None:
        return ValidationResult(ok=not errors, errors=errors, data=value)
    try:
        parsed = model.model_validate(value)
    except Exception as exc:
        details = getattr(exc, "errors", None)
        msgs = (
            [f"$.{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg')}" for e in details()]
            if callable(details)
            else [str(exc)]
        )
        return ValidationResult(ok=False, errors=msgs, data=value, engine="pydantic+jsonschema")
    return ValidationResult(ok=True, data=parsed.model_dump(), engine="pydantic+jsonschema")


def coerce_json(raw: Any) -> Any:
    """Model reply → JSON value. Accepts parsed data, a JSON string, or a fenced block."""
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return json.loads(text.strip())
