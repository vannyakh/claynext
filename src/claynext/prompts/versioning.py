"""Semantic versions, version specs, and prompt fingerprints for skills.

A skill version names a behavior. The fingerprint is a hash of every file
that shapes the prompt (manifest, template, system text, schemas, language
files). ``versions.lock.json`` pins the fingerprint per ``id@version`` so a
template edit without a version bump shows up as drift in tests.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_SEMVER = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?\s*$")
_CLAUSE = re.compile(r"^(\^|~|>=|<=|>|<|==|=)?\s*(.+)$")

LOCK_FILE = Path(__file__).resolve().parent / "versions.lock.json"


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int
    pre: str = ""

    @classmethod
    def parse(cls, text: str) -> "SemVer":
        m = _SEMVER.match(str(text or ""))
        if not m:
            raise ValueError(f"Not a semantic version: {text!r}")
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "")

    def sort_key(self) -> tuple:
        # A pre-release sorts before its release (1.0.0-rc1 < 1.0.0).
        return (self.major, self.minor, self.patch, 0 if self.pre else 1, self.pre)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.pre}" if self.pre else base


def _partial(text: str) -> tuple[int, ...]:
    parts = [p for p in str(text).strip().lstrip("v").split(".") if p not in ("", "x", "*")]
    return tuple(int(p) for p in parts)


def _clause_ok(version: SemVer, op: str, target: str) -> bool:
    key = version.sort_key()
    nums = _partial(target)
    if op in ("^", "~"):
        lo = SemVer(*(list(nums) + [0, 0, 0])[:3]).sort_key()
        if key < lo:
            return False
        if op == "^":
            if nums and nums[0] > 0:
                return version.major == nums[0]
            if len(nums) > 1:
                return version.major == 0 and version.minor == nums[1]
            return version.major == 0
        # ~1.2 → >=1.2.0 <1.3.0 ; ~1 → >=1.0.0 <2.0.0
        if len(nums) >= 2:
            return version.major == nums[0] and version.minor == nums[1]
        return version.major == nums[0]
    if op in ("", "=", "=="):
        if len(nums) == 3:
            return key == SemVer.parse(target).sort_key()
        return (version.major, version.minor, version.patch)[: len(nums)] == nums
    other = (
        SemVer.parse(target) if _SEMVER.match(target) else SemVer(*(list(nums) + [0, 0, 0])[:3])
    ).sort_key()
    return {
        ">=": key >= other,
        "<=": key <= other,
        ">": key > other,
        "<": key < other,
    }[op]


def matches(version: str | SemVer, spec: str = "") -> bool:
    """True when ``version`` satisfies ``spec`` ("", "*", "1.0.0", "^1.0", ">=1.0.0,<2")."""
    ver = version if isinstance(version, SemVer) else SemVer.parse(version)
    spec = (spec or "").strip()
    if spec in ("", "*", "latest"):
        return not ver.pre
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        m = _CLAUSE.match(raw)
        if not m or not _clause_ok(ver, m.group(1) or "", m.group(2)):
            return False
    return True


def best_match(versions: Iterable[str], spec: str = "") -> str | None:
    """Highest version in ``versions`` that satisfies ``spec``."""
    ok = [SemVer.parse(v) for v in versions if matches(v, spec)]
    if not ok:
        return None
    return str(max(ok, key=SemVer.sort_key))


def fingerprint(paths: Iterable[Path]) -> str:
    """sha256 over file names + contents (line endings normalized)."""
    digest = hashlib.sha256()
    for path in sorted({Path(p) for p in paths}, key=lambda p: p.name + str(p)):
        data = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(path.name.encode("utf-8") + b"\0" + data + b"\0")
    return "sha256:" + digest.hexdigest()


def read_lock(path: Path = LOCK_FILE) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in (data.get("skills") or {}).items()}


def lock_status(skill_id: str, version: str, current: str, path: Path = LOCK_FILE) -> str:
    """``locked`` when the pin matches, ``drift`` when files changed, ``unlocked`` when unpinned."""
    pinned = read_lock(path).get(f"{skill_id}@{version}")
    if not pinned:
        return "unlocked"
    return "locked" if pinned == current else "drift"


def write_lock(entries: dict[str, str], path: Path = LOCK_FILE) -> None:
    """Pin ``{"id@version": fingerprint}``. Run only when a version is deliberately released."""
    merged = read_lock(path)
    merged.update(entries)
    payload = {
        "comment": "Bump the skill version in skill.yaml before re-pinning a changed prompt.",
        "skills": dict(sorted(merged.items())),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
