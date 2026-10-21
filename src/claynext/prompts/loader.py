"""Load skill manifests, language profiles, schemas, and system text from package data.

PyYAML is used when installed. Without it, a block-style YAML subset parser
reads the shipped files (mappings, ``- `` lists, quoted / plain scalars,
``|`` / ``>`` block scalars, ``[]`` / ``{}`` / ``[a, b]`` inline values).
Shipped YAML must stay inside that subset; a test compares both parsers.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent
SKILLS_DIR = PROMPTS_DIR / "skills"
LANGUAGES_DIR = PROMPTS_DIR / "languages"
SCHEMAS_DIR = PROMPTS_DIR / "schemas"
SYSTEM_DIR = PROMPTS_DIR / "system"
EVALUATIONS_DIR = PROMPTS_DIR / "evaluations"

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover - exercised by forcing the fallback in tests
    _yaml = None


class ManifestError(ValueError):
    """A skill or language file is missing fields or cannot be parsed."""


# ── YAML ────────────────────────────────────────────────────────────────

def load_yaml_text(text: str, *, force_fallback: bool = False) -> Any:
    if _yaml is not None and not force_fallback:
        return _yaml.safe_load(text)
    return _MiniYaml(text).parse()


def load_yaml(path: Path, *, force_fallback: bool = False) -> Any:
    try:
        return load_yaml_text(path.read_text(encoding="utf-8"), force_fallback=force_fallback)
    except ManifestError:
        raise
    except Exception as exc:
        raise ManifestError(f"{path.name}: {exc}") from exc


_INT = re.compile(r"^[-+]?\d+$")
_FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")


def _strip_comment(text: str) -> str:
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"') and (i == 0 or text[i - 1] in " [,:{"):
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text.rstrip()


def _split_key(content: str) -> tuple[str, str] | None:
    if content[:1] in ("'", '"', "[", "{"):
        return None
    for i, ch in enumerate(content):
        if ch == ":" and (i + 1 == len(content) or content[i + 1] in " \t"):
            return content[:i].strip(), content[i + 1:].strip()
    return None


def _scalar(raw: str) -> Any:
    text = _strip_comment(raw.strip())
    if not text:
        return None
    if text[0] == '"':
        return json.loads(text)
    if text[0] == "'":
        return text[1:-1].replace("''", "'")
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text[0] == "[" and text[-1] == "]":
        return [_scalar(part) for part in _split_flow(text[1:-1])]
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    if _INT.match(text):
        return int(text)
    if _FLOAT.match(text):
        return float(text)
    return text


def _split_flow(body: str) -> list[str]:
    parts, cur, quote = [], [], ""
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
        if ch == ",":
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


class _MiniYaml:
    def __init__(self, text: str):
        if re.search(r"^ *\t", text, re.M):
            raise ManifestError("Tabs are not allowed for YAML indentation")
        self.lines = text.splitlines()
        self.i = 0

    def parse(self) -> Any:
        self._skip()
        if self.i >= len(self.lines):
            return None
        return self._node(_indent(self.lines[self.i]))

    def _skip(self) -> None:
        while self.i < len(self.lines):
            stripped = self.lines[self.i].strip()
            if not stripped or stripped.startswith("#") or stripped in ("---", "..."):
                self.i += 1
                continue
            break

    def _node(self, ind: int) -> Any:
        content = self.lines[self.i].strip()
        if content == "-" or content.startswith("- "):
            return self._seq(ind)
        if _split_key(_strip_comment(content)) is not None:
            return self._map(ind)
        self.i += 1
        return _scalar(content)

    def _map(self, ind: int) -> dict:
        out: dict[str, Any] = {}
        while True:
            self._skip()
            if self.i >= len(self.lines):
                break
            line = self.lines[self.i]
            cur = _indent(line)
            if cur < ind:
                break
            if cur > ind:
                raise ManifestError(f"line {self.i + 1}: unexpected indent")
            content = _strip_comment(line.strip())
            if content.startswith("- ") or content == "-":
                break
            pair = _split_key(content)
            if pair is None:
                raise ManifestError(f"line {self.i + 1}: expected 'key: value'")
            key, rest = pair
            self.i += 1
            out[key] = self._value(rest, ind)
        return out

    def _value(self, rest: str, ind: int) -> Any:
        if rest[:1] in ("|", ">"):
            return self._block(rest, ind)
        if rest:
            return _scalar(rest)
        self._skip()
        if self.i < len(self.lines):
            nxt = self.lines[self.i]
            nind = _indent(nxt)
            is_seq = nxt.strip() == "-" or nxt.strip().startswith("- ")
            if nind > ind or (nind == ind and is_seq):
                return self._node(nind)
        return None

    def _seq(self, ind: int) -> list:
        out: list[Any] = []
        while True:
            self._skip()
            if self.i >= len(self.lines):
                break
            line = self.lines[self.i]
            content = line.strip()
            if _indent(line) != ind or not (content == "-" or content.startswith("- ")):
                break
            item = content[1:].lstrip()
            col = ind + (len(content) - len(item))
            if not item:
                self.i += 1
                self._skip()
                out.append(self._node(_indent(self.lines[self.i])) if self.i < len(self.lines) else None)
            elif _split_key(_strip_comment(item)) is not None:
                self.lines[self.i] = " " * col + item
                out.append(self._map(col))
            else:
                self.i += 1
                out.append(_scalar(item))
        return out

    def _block(self, head: str, ind: int) -> str:
        style, chomp = head[0], head[1:].strip()
        body: list[str] = []
        block_ind = None
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.strip():
                cur = _indent(line)
                if cur <= ind:
                    break
                if block_ind is None:
                    block_ind = cur
                body.append(line[block_ind:])
            else:
                body.append("")
            self.i += 1
        while body and not body[-1]:
            body.pop()
        if style == "|":
            text = "\n".join(body)
        else:
            paras, cur = [], []
            for row in body:
                if row:
                    cur.append(row)
                else:
                    paras.append(" ".join(cur))
                    cur = []
            paras.append(" ".join(cur))
            text = "\n".join(paras)
        return text if chomp == "-" else text + "\n"


# ── Manifests ───────────────────────────────────────────────────────────

_REQUIRED = ("id", "version", "name", "model_capability", "template", "inputs", "output", "settings")


@dataclass(frozen=True)
class SkillManifest:
    id: str
    version: str
    name: str
    description: str
    model_capability: str
    template: str
    inputs: dict[str, dict[str, Any]]
    input_schema: str
    output_schema: str
    output_contract: str
    settings: dict[str, Any]
    system: tuple[str, ...]
    requires: tuple[dict[str, str], ...]
    backends: tuple[str, ...]
    languages: tuple[str, ...]
    limits: dict[str, Any]
    changelog: tuple[dict[str, Any], ...]
    root: Path
    raw: dict[str, Any] = field(repr=False, compare=False, default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def template_path(self) -> Path:
        return self.root / self.template

    @property
    def manifest_path(self) -> Path:
        return self.root / "skill.yaml"

    def system_paths(self) -> list[Path]:
        return [SYSTEM_DIR / f"{name}.md" for name in self.system]

    def schema_paths(self) -> list[Path]:
        return [SCHEMAS_DIR / f"{name}.schema.json" for name in (self.input_schema, self.output_schema) if name]

    def language_paths(self) -> list[Path]:
        return [LANGUAGES_DIR / f"{name}.yaml" for name in self.languages]

    def source_files(self) -> list[Path]:
        return [
            self.manifest_path,
            self.template_path,
            *self.system_paths(),
            *self.schema_paths(),
            *self.language_paths(),
        ]


def _as_tuple(value: Any) -> tuple:
    if value in (None, ""):
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def load_manifest(skill_dir: Path, *, force_fallback: bool = False) -> SkillManifest:
    path = skill_dir / "skill.yaml"
    data = load_yaml(path, force_fallback=force_fallback)
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: manifest must be a mapping")
    missing = [key for key in _REQUIRED if key not in data]
    if missing:
        raise ManifestError(f"{path}: missing {', '.join(missing)}")
    from claynext.prompts.versioning import SemVer

    SemVer.parse(str(data["version"]))
    output = data.get("output") or {}
    if not isinstance(output, dict) or not output.get("schema"):
        raise ManifestError(f"{path}: output.schema is required")
    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise ManifestError(f"{path}: inputs must be a mapping of name → spec")
    requires = []
    for dep in _as_tuple(data.get("requires")):
        if isinstance(dep, str):
            dep = {"id": dep, "version": ""}
        requires.append({"id": str(dep.get("id") or ""), "version": str(dep.get("version") or "")})
    manifest = SkillManifest(
        id=str(data["id"]),
        version=str(data["version"]),
        name=str(data["name"]),
        description=str(data.get("description") or "").strip(),
        model_capability=str(data["model_capability"]),
        template=str(data["template"]),
        inputs={str(k): dict(v or {}) for k, v in inputs.items()},
        input_schema=str(data.get("input_schema") or ""),
        output_schema=str(output.get("schema")),
        output_contract=str(output.get("contract") or output.get("schema")),
        settings=dict(data.get("settings") or {}),
        system=tuple(str(s) for s in _as_tuple(data.get("system"))),
        requires=tuple(requires),
        backends=tuple(str(b) for b in _as_tuple(data.get("backends"))),
        languages=tuple(str(lang) for lang in _as_tuple(data.get("languages"))),
        limits=dict(data.get("limits") or {}),
        changelog=tuple(_as_tuple(data.get("changelog"))),
        root=skill_dir,
        raw=data,
    )
    for p in manifest.source_files():
        if not p.is_file():
            raise ManifestError(f"{manifest.key}: missing file {p.name}")
    return manifest


def discover_manifests(root: Path = SKILLS_DIR, *, force_fallback: bool = False) -> list[SkillManifest]:
    found = []
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if (skill_dir / "skill.yaml").is_file():
            found.append(load_manifest(skill_dir, force_fallback=force_fallback))
    return found


# ── Languages, schemas, system text ─────────────────────────────────────

def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMAS_DIR / f"{name}.schema.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"schema {name}: {exc}") from exc


def load_system_text(names: tuple[str, ...] | list[str]) -> str:
    return "\n\n".join(
        (SYSTEM_DIR / f"{name}.md").read_text(encoding="utf-8").strip() for name in names
    )


def _normalize_glossary(rows: Any) -> list[dict[str, str]]:
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        src = str(row.get("source") or "").strip()
        tgt = str(row.get("target") or "").strip()
        if src and tgt:
            out.append({"source": src, "target": tgt, "note": str(row.get("note") or "").strip()})
    return out


def _normalize_examples(rows: Any) -> list[dict[str, str]]:
    out = []
    for row in rows or []:
        if isinstance(row, dict) and row.get("source") and row.get("say"):
            out.append({
                "source": str(row["source"]).strip(),
                "say": str(row["say"]).strip(),
                "avoid": str(row.get("avoid") or "").strip(),
                "note": str(row.get("note") or "").strip(),
            })
    return out


def load_language(name: str, *, force_fallback: bool = False) -> dict[str, Any] | None:
    """Language profile by file id, display name, or code. ``None`` when not shipped."""
    want = (name or "").strip().lower()
    if not want:
        return None
    for path in sorted(LANGUAGES_DIR.glob("*.yaml")):
        data = load_yaml(path, force_fallback=force_fallback) or {}
        names = {path.stem.lower(), str(data.get("name") or "").lower(), str(data.get("native_name") or "").lower()}
        names.update(str(code).lower() for code in data.get("codes") or [])
        if want in names or any(n and n in want for n in names if len(n) > 3):
            return {
                "id": path.stem,
                "name": str(data.get("name") or path.stem.title()),
                "native_name": str(data.get("native_name") or ""),
                "display_name": str(data.get("display_name") or data.get("name") or path.stem),
                "spoken_unit": str(data.get("spoken_unit") or "spoken beat"),
                "instructions": [str(x).strip() for x in data.get("instructions") or [] if str(x).strip()],
                "examples": _normalize_examples(data.get("examples")),
                "glossary": _normalize_glossary(data.get("glossary")),
            }
    return None


def generic_language(name: str) -> dict[str, Any]:
    return {
        "id": "",
        "name": name,
        "native_name": "",
        "display_name": f"natural spoken {name}",
        "spoken_unit": "spoken beat",
        "instructions": [],
        "examples": [],
        "glossary": [],
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise ManifestError(f"{path.name}:{n}: {exc}") from exc
    return rows
