"""TTS training entrypoints (dry-run capable)."""
from claynext.voice_training.training.tts_trainer import run_finetune, trainer_capability

__all__ = ["run_finetune", "trainer_capability"]
