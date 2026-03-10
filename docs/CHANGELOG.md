# Documentation Changelog

## 2026-03-10

- Added first-pass project documentation for overview, architecture, API, coding guidelines, testing, and references.
- Documented the current Web MVP implementation rather than the earlier desktop-oriented concept.
- Recorded current behavioral constraints, including local-only runtime, deterministic evaluation, supported role and level combinations, and the frontend restriction to `10` minute sessions.
- Updated the docs to describe the real OpenAI-compatible provider flow, persisted LLM settings, and the settings-first startup experience.
- Added a follow-up TODO for replacing plaintext API key storage with system credential stores.
- Updated backend runtime and testing documentation to use `uv sync` and `uv run ...`, and checked in `uv.lock` for Python dependency locking.
