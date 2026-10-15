"""
Events Adapter: Typed engine events emitted from native Rust core to PySide6 Qt GUI.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("claynext.adapters.events")


class EngineEventAdapter:
    """Dispatches asynchronous engine events to registered UI listeners."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

    def subscribe(self, event_name: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if event_name in self._listeners and callback in self._listeners[event_name]:
            self._listeners[event_name].remove(callback)

    def dispatch(self, event_name: str, payload: dict[str, Any]) -> None:
        listeners = self._listeners.get(event_name, [])
        for cb in listeners:
            try:
                cb(payload)
            except Exception as e:
                logger.exception("Error in engine event callback for %s: %s", event_name, e)


_event_adapter: EngineEventAdapter | None = None


def get_event_adapter() -> EngineEventAdapter:
    global _event_adapter
    if _event_adapter is None:
        _event_adapter = EngineEventAdapter()
    return _event_adapter
