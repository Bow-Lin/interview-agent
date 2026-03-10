import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


class SpeechTranscriber(Protocol):
    def transcribe(
        self, *, audio_path: Path, model_name: str, language_hint: Optional[str] = None
    ) -> str:
        ...


@dataclass
class SpeechSettings:
    mode: str
    whisper_model: str


class SpeechTranscriptionUnavailable(RuntimeError):
    pass


class WhisperSpeechTranscriber:
    def __init__(self) -> None:
        self._loaded_model = None
        self._loaded_model_name: Optional[str] = None

    def transcribe(
        self, *, audio_path: Path, model_name: str, language_hint: Optional[str] = None
    ) -> str:
        model = self._load_model(model_name)
        options = {
            "fp16": False,
            "verbose": False,
        }
        if language_hint:
            options["language"] = language_hint
        try:
            result = model.transcribe(str(audio_path), **options)
        except FileNotFoundError as exc:
            raise SpeechTranscriptionUnavailable(
                "Whisper transcription requires ffmpeg to be installed on this machine."
            ) from exc
        except Exception as exc:
            raise SpeechTranscriptionUnavailable(str(exc)) from exc

        text = str(result.get("text", "")).strip()
        if not text:
            raise SpeechTranscriptionUnavailable("Whisper did not return any transcription text.")
        return text

    def _load_model(self, model_name: str):
        if self._loaded_model is not None and self._loaded_model_name == model_name:
            return self._loaded_model

        try:
            import whisper
        except ImportError as exc:
            raise SpeechTranscriptionUnavailable(
                "Whisper mode is unavailable. Install the optional speech dependencies first."
            ) from exc

        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        self._loaded_model = whisper.load_model(model_name)
        self._loaded_model_name = model_name
        return self._loaded_model
