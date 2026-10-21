"""AI provider seam for movie transcription, translation, and voices.

Studio talks to this interface. A concrete server (SGLang-Omni, and later
others) reports which of those jobs it can do. The UI and the dub pipeline
do not import a model's HTTP client.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """One error shape for every AI server failure."""

    def __init__(self, message: str, *, code: str, provider: str):
        super().__init__(message)
        self.code = code
        self.provider = provider


@dataclass(frozen=True)
class ProviderCapabilities:
    """Model ids the server listed, and the id chosen for each job."""

    models: tuple[str, ...] = ()
    transcribe: str | None = None
    translate: str | None = None
    speak: str | None = None

    def supports(self, kind: str) -> bool:
        return bool(getattr(self, kind, None))


class AiProvider(Protocol):
    """Transcription, dialogue rewrite, and speech. Each method may be unsupported."""

    provider_id: str

    def available(self) -> bool:
        """True when the endpoint answered recently."""

    def capabilities(self) -> ProviderCapabilities:
        """What the current model list can transcribe, translate, and speak."""

    def transcribe(
        self,
        media_path: str,
        language: str = "Auto Detect",
        *,
        control: Any = None,
    ) -> list[dict[str, Any]]:
        """Timed dialogue lines."""

    def complete(self, prompt: str, *, control: Any = None) -> str:
        """Raw model text for a subtitle prompt."""

    def speak(
        self,
        text: str,
        output_path: str,
        *,
        voice: str = "",
        control: Any = None,
    ) -> str:
        """Write dubbed audio and return its path."""
