"""Annotation helpers: ASR draft, diarization, emotion, prosody, pronunciation."""
from claynext.voice_training.annotation.emotion_annotator import apply_annotation, normalize_emotion
from claynext.voice_training.annotation.khmer_transcriber import draft_transcript

__all__ = ["apply_annotation", "normalize_emotion", "draft_transcript"]
