"""
Claynext Studio package.

Architecture:
- controllers: UI workflow and window controllers
- adapters: Infrastructure and native Rust core backends
- services: Domain business logic services
- models: Strongly-typed data models
- constants: Theme, layout, and configuration tokens
- utils: Paths, logging, configuration helpers
- gui: PySide6 views, components, and cyber-dark styling
"""
from __future__ import annotations

from claynext.utils.config import APP_NAME, APP_VERSION

__all__ = ["APP_NAME", "APP_VERSION"]
