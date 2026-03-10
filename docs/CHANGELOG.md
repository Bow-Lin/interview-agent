# Documentation Changelog

## 2026-03-10

- Added first-pass project documentation for overview, architecture, API, coding guidelines, testing, and references.
- Documented the current Web MVP implementation rather than the earlier desktop-oriented concept.
- Recorded current behavioral constraints, including local-only runtime, deterministic evaluation, supported role and level combinations, and the frontend restriction to `10` minute sessions.
- Updated the docs to describe the real OpenAI-compatible provider flow, persisted LLM settings, and the settings-first startup experience.
- Added a follow-up TODO for replacing plaintext API key storage with system credential stores.
- Updated backend runtime and testing documentation to use `uv sync` and `uv run ...`, and checked in `uv.lock` for Python dependency locking.
- Updated the timer documentation to reflect real wall-clock `remaining_seconds` tracking instead of the earlier fixed per-answer decrement.
- Added optional browser-native voice input for interview answers with text-input fallback on unsupported browsers.
- Added a voice-language toggle so supported browsers can switch speech recognition between Chinese and English.
- Added persisted speech settings and an optional Whisper transcription path that records in the browser and transcribes on the backend.
- Configured the Whisper extra to resolve `torch` from the PyTorch CPU wheel index by default, avoiding oversized CUDA downloads during `uv sync --extra speech`.
- Configured project-level `uv` package resolution to use the Tsinghua PyPI mirror by default for faster dependency downloads in domestic environments.
