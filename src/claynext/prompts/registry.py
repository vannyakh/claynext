"""Skill registry: discover versioned skills, resolve dependencies, render, validate.

A skill guides a model with instructions and a contract. It never opens
media files, calls a backend, or touches widgets; callers pass data in and
send the rendered prompt through their own provider path.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from claynext.prompts import loader, renderer, validator, versioning
from claynext.prompts.loader import ManifestError, SkillManifest


class SkillNotFound(KeyError):
    pass


class SkillResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    skill_id: str
    version: str
    fingerprint: str
    settings: dict[str, Any]
    target_language: str = ""

    def record(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "settings": dict(self.settings),
            "prompt_chars": len(self.text),
        }


@dataclass
class Skill:
    manifest: SkillManifest
    force_fallback: bool = False
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def settings(self) -> dict[str, Any]:
        return dict(self.manifest.settings)

    @property
    def fingerprint(self) -> str:
        if "fingerprint" not in self._cache:
            self._cache["fingerprint"] = versioning.fingerprint(self.manifest.source_files())
        return self._cache["fingerprint"]

    def lock_status(self) -> str:
        return versioning.lock_status(self.id, self.version, self.fingerprint)

    def supports_backend(self, backend: str) -> bool:
        allowed = self.manifest.backends
        if not allowed:
            return True
        if backend in allowed:
            return True
        if "chat" in allowed:
            from claynext.models.llm_providers import CHAT_PROVIDERS

            return backend in CHAT_PROVIDERS
        return False

    def _schema(self, name: str) -> dict[str, Any]:
        key = f"schema:{name}"
        if key not in self._cache:
            self._cache[key] = loader.load_schema(name)
        return self._cache[key]

    def _template(self) -> str:
        if "template" not in self._cache:
            self._cache["template"] = self.manifest.template_path.read_text(encoding="utf-8")
        return self._cache["template"]

    def validate_input(self, inputs: dict[str, Any]) -> validator.ValidationResult:
        unknown = sorted(set(inputs) - set(self.manifest.inputs))
        name = self.manifest.input_schema
        if name:
            res = validator.validate(
                self._schema(name), inputs, contract=name, use_pydantic=not self.force_fallback
            )
        else:
            missing = [k for k, spec in self.manifest.inputs.items() if spec.get("required") and k not in inputs]
            res = validator.ValidationResult(ok=not missing, errors=[f"$: missing {k!r}" for k in missing], data=inputs)
        if unknown:
            res.ok = False
            res.errors.extend(f"$: unknown input {k!r}" for k in unknown)
        return res

    def context(self, inputs: dict[str, Any]) -> dict[str, Any]:
        ctx: dict[str, Any] = {k: spec.get("default") for k, spec in self.manifest.inputs.items()}
        ctx.update(inputs)
        for key, spec in self.manifest.inputs.items():
            if ctx.get(key) is None and "default" not in spec:
                ctx[key] = ""
        target = str(ctx.get("target_language") or "")
        source = str(ctx.get("source_language") or "")
        ctx["target"] = (
            loader.load_language(target, force_fallback=self.force_fallback) or loader.generic_language(target)
        )
        ctx["source_label"] = "" if source.lower() in ("", "auto", "auto detect") else source
        ctx["system_instructions"] = loader.load_system_text(self.manifest.system)
        schema = self._schema(self.manifest.output_schema)
        ctx["output_schema"] = {k: v for k, v in schema.items() if not k.startswith("$")}
        ctx["skill"] = {"id": self.id, "version": self.version, "name": self.manifest.name}
        return ctx

    def render(self, inputs: dict[str, Any], *, validate_inputs: bool = True) -> RenderedPrompt:
        if validate_inputs:
            res = self.validate_input(inputs)
            if not res.ok:
                raise renderer.RenderError("invalid inputs: " + "; ".join(res.errors[:5]))
        text = renderer.render_template(
            self._template(), self.context(inputs), force_fallback=self.force_fallback
        )
        return RenderedPrompt(
            text=text,
            skill_id=self.id,
            version=self.version,
            fingerprint=self.fingerprint,
            settings=self.settings,
            target_language=str(inputs.get("target_language") or ""),
        )

    def validate_output(self, raw: Any, inputs: dict[str, Any] | None = None) -> validator.ValidationResult:
        """Contract check plus coverage (one output per input id, no extras)."""
        try:
            value = validator.coerce_json(raw)
        except ValueError as exc:
            return validator.ValidationResult(ok=False, errors=[f"$: not JSON ({exc})"], data=raw)
        out_spec = self.manifest.raw.get("output") or {}
        list_key = str(out_spec.get("list_key") or "")
        if list_key and isinstance(value, list):
            value = {list_key: value}
        res = validator.validate(
            self._schema(self.manifest.output_schema),
            value,
            contract=self.manifest.output_contract,
            use_pydantic=not self.force_fallback,
        )
        cover = out_spec.get("coverage") or {}
        if res.ok and inputs is not None and cover and list_key:
            want = [str(row.get(cover.get("key", "id"))) for row in inputs.get(cover.get("input", ""), []) or []]
            got = [str(row.get(cover.get("key", "id"))) for row in res.data.get(list_key, [])]
            missing = [k for k in want if k not in got]
            extra = [k for k in got if k not in want]
            dupes = sorted({k for k in got if got.count(k) > 1})
            if missing:
                res.errors.append(f"omitted id(s): {', '.join(missing[:10])}")
            if extra:
                res.errors.append(f"added id(s): {', '.join(extra[:10])}")
            if dupes:
                res.errors.append(f"duplicate id(s): {', '.join(dupes[:10])}")
            res.ok = not res.errors
        return res

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "name": self.manifest.name,
            "model_capability": self.manifest.model_capability,
            "requires": [dict(d) for d in self.manifest.requires],
            "backends": list(self.manifest.backends),
            "languages": list(self.manifest.languages),
            "settings": self.settings,
            "fingerprint": self.fingerprint,
            "lock": self.lock_status(),
        }


class SkillRegistry:
    def __init__(self, root: Path = loader.SKILLS_DIR, *, force_fallback: bool = False):
        self.root = root
        self.force_fallback = force_fallback
        self._skills: dict[str, dict[str, Skill]] = {}
        self._loaded = False

    def load(self) -> "SkillRegistry":
        if not self._loaded:
            for manifest in loader.discover_manifests(self.root, force_fallback=self.force_fallback):
                self.register(manifest)
            self._loaded = True
        return self

    def register(self, manifest: SkillManifest) -> Skill:
        versions = self._skills.setdefault(manifest.id, {})
        if manifest.version in versions:
            raise ManifestError(f"duplicate skill {manifest.key}")
        skill = Skill(manifest, force_fallback=self.force_fallback)
        versions[manifest.version] = skill
        return skill

    def ids(self) -> list[str]:
        self.load()
        return sorted(self._skills)

    def versions(self, skill_id: str) -> list[str]:
        self.load()
        found = self._skills.get(skill_id, {})
        return sorted(found, key=lambda v: versioning.SemVer.parse(v).sort_key())

    def get(self, skill_id: str, spec: str = "") -> Skill:
        self.load()
        found = self._skills.get(skill_id)
        if not found:
            raise SkillNotFound(skill_id)
        version = versioning.best_match(found, spec)
        if version is None:
            raise SkillNotFound(f"{skill_id} {spec}")
        return found[version]

    def resolve(
        self,
        skill_id: str,
        spec: str = "",
        *,
        capabilities: Iterable[str] | None = None,
    ) -> list[Skill]:
        """The skill and its dependencies, dependencies first."""
        have = set(capabilities) if capabilities is not None else None
        order: list[Skill] = []
        visiting: set[str] = set()

        def _walk(sid: str, sp: str) -> None:
            try:
                skill = self.get(sid, sp)
            except SkillNotFound as exc:
                raise SkillResolutionError(f"missing dependency {sid} {sp}".strip()) from exc
            if skill.manifest.key in visiting:
                raise SkillResolutionError(f"dependency cycle at {skill.manifest.key}")
            if any(s.manifest.key == skill.manifest.key for s in order):
                return
            if have is not None and skill.manifest.model_capability not in have:
                raise SkillResolutionError(
                    f"{skill.manifest.key} needs {skill.manifest.model_capability}"
                )
            visiting.add(skill.manifest.key)
            for dep in skill.manifest.requires:
                _walk(dep["id"], dep.get("version", ""))
            visiting.discard(skill.manifest.key)
            order.append(skill)

        _walk(skill_id, spec)
        return order

    def catalog(self) -> list[dict[str, Any]]:
        return [self._skills[sid][v].summary() for sid in self.ids() for v in self.versions(sid)]


_registry: SkillRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> SkillRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = SkillRegistry().load()
        return _registry
