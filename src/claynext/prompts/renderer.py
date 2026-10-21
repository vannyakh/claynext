"""Render skill templates.

Jinja2's sandboxed environment is used when installed (StrictUndefined,
no autoescape, trim/lstrip blocks). Without Jinja2 a small renderer covers
the portable subset that shipped templates are limited to:

- ``{{ path }}`` and ``{{ path | tojson }}`` (``path`` is ``name`` or ``name.key``)
- ``{% if [not] path %}`` … ``{% else %}`` … ``{% endif %}``
- ``{% for item in path %}`` … ``{% endfor %}``
- ``{# comments #}``

A test renders every shipped template with both engines and compares them.
"""
from __future__ import annotations

import json
import re
from typing import Any

try:
    from jinja2 import StrictUndefined
    from jinja2.sandbox import SandboxedEnvironment
except ImportError:  # pragma: no cover - exercised by forcing the fallback in tests
    SandboxedEnvironment = None


class RenderError(ValueError):
    """Template uses a missing variable or syntax outside the portable subset."""


def tojson(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


_env = None


def _jinja_env():
    global _env
    if _env is None:
        _env = SandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )
        _env.filters["tojson"] = tojson
    return _env


def render_template(source: str, context: dict[str, Any], *, force_fallback: bool = False) -> str:
    if SandboxedEnvironment is not None and not force_fallback:
        try:
            return _jinja_env().from_string(source).render(**context)
        except Exception as exc:
            raise RenderError(str(exc)) from exc
    return _MiniTemplate(source).render(context)


# ── Fallback renderer ──────────────────────────────────────────────────

_TOKEN = re.compile(r"({{.*?}}|{%.*?%}|{#.*?#})", re.S)
_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_MISSING = object()


def _tokens(source: str) -> list[tuple[str, str]]:
    if source.endswith("\n"):
        source = source[:-1]
    parts = _TOKEN.split(source)
    out: list[tuple[str, str]] = []
    trim_next = False
    for idx, part in enumerate(parts):
        if idx % 2 == 0:
            text = part
            nxt = parts[idx + 1] if idx + 1 < len(parts) else ""
            if nxt.startswith(("{%", "{#")):
                # lstrip_blocks: drop spaces/tabs between line start and the block tag.
                head, nl, tail = text.rpartition("\n")
                if tail.strip(" \t") == "" and (nl or idx == 0):
                    text = head + nl
            if trim_next and text.startswith("\n"):
                text = text[1:]
            trim_next = False
            out.append(("text", text))
        elif part.startswith("{{"):
            out.append(("var", part[2:-2].strip()))
        elif part.startswith("{%"):
            out.append(("block", part[2:-2].strip()))
            trim_next = True
        else:
            trim_next = True
    return out


def _lookup(context: dict[str, Any], path: str) -> Any:
    if not _PATH.match(path):
        raise RenderError(f"unsupported expression {path!r}")
    head, *rest = path.split(".")
    if head not in context:
        raise RenderError(f"{head!r} is undefined")
    value = context[head]
    for key in rest:
        if isinstance(value, dict):
            value = value.get(key, _MISSING)
        else:
            value = getattr(value, key, _MISSING)
        if value is _MISSING:
            raise RenderError(f"{path!r} is undefined")
    return value


def _expr(context: dict[str, Any], expr: str) -> Any:
    name, _, filt = (p.strip() for p in expr.partition("|"))
    value = _lookup(context, name)
    if not filt:
        return value
    if filt == "tojson":
        return tojson(value)
    raise RenderError(f"unsupported filter {filt!r}")


class _MiniTemplate:
    def __init__(self, source: str):
        self.nodes, rest = self._parse(_tokens(source), 0, ())
        if rest is not None:
            raise RenderError(f"unexpected {{% {rest} %}}")

    def _parse(self, toks: list[tuple[str, str]], i: int, stop: tuple[str, ...]):
        nodes: list[Any] = []
        while i < len(toks):
            kind, val = toks[i]
            if kind != "block":
                nodes.append((kind, val))
                i += 1
                continue
            word = val.split()[0] if val.split() else ""
            if word in stop:
                self._end = i
                return nodes, val
            if word == "if":
                cond = val[2:].strip()
                body, end_tag = self._parse(toks, i + 1, ("else", "endif"))
                i = self._end + 1
                other: list[Any] = []
                if end_tag == "else":
                    other, end_tag = self._parse(toks, i, ("endif",))
                    i = self._end + 1
                if end_tag != "endif":
                    raise RenderError("missing {% endif %}")
                nodes.append(("if", cond, body, other))
                continue
            if word == "for":
                m = re.match(r"^for\s+([A-Za-z_]\w*)\s+in\s+(\S+)$", val)
                if not m:
                    raise RenderError(f"unsupported loop {val!r}")
                body, end_tag = self._parse(toks, i + 1, ("endfor",))
                if end_tag != "endfor":
                    raise RenderError("missing {% endfor %}")
                i = self._end + 1
                nodes.append(("for", m.group(1), m.group(2), body))
                continue
            raise RenderError(f"unsupported tag {val!r}")
        if stop:
            raise RenderError(f"missing {{% {stop[-1]} %}}")
        return nodes, None

    def render(self, context: dict[str, Any]) -> str:
        out: list[str] = []
        self._emit(self.nodes, dict(context), out)
        return "".join(out)

    def _emit(self, nodes: list[Any], ctx: dict[str, Any], out: list[str]) -> None:
        for node in nodes:
            kind = node[0]
            if kind == "text":
                out.append(node[1])
            elif kind == "var":
                value = _expr(ctx, node[1])
                out.append(value if isinstance(value, str) else str(value))
            elif kind == "if":
                cond = node[1]
                negate = cond.startswith("not ")
                value = bool(_lookup(ctx, cond[4:].strip() if negate else cond))
                self._emit(node[2] if value != negate else node[3], ctx, out)
            elif kind == "for":
                for item in _lookup(ctx, node[2]) or []:
                    inner = dict(ctx)
                    inner[node[1]] = item
                    self._emit(node[3], inner, out)
