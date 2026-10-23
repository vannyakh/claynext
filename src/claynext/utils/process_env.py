"""Environment handed to processes this app starts."""
from __future__ import annotations

import os

# macOS libmalloc prints
# "can't turn off malloc stack logging because it was not enabled"
# in every child when a parent (often an IDE) exported these and the
# child does not actually have stack logging turned on.
_MALLOC_STACK_KEYS = ("MallocStackLogging", "MallocStackLoggingNoCompact")


def scrub_malloc_stack_logging(env: dict[str, str] | None = None) -> dict[str, str]:
    """Drop malloc stack-logging variables. Defaults to this process."""
    target = os.environ if env is None else env
    for key in _MALLOC_STACK_KEYS:
        target.pop(key, None)
    return target


def child_environ(base: dict[str, str] | None = None) -> dict[str, str]:
    """Copy of the environment safe to pass to a subprocess."""
    env = dict(os.environ if base is None else base)
    return scrub_malloc_stack_logging(env)
