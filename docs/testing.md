# Testing

## Current Test Stack

Backend:

- Python `unittest`
- `httpx.ASGITransport` for API-level tests against the FastAPI app

Frontend:

- `vitest`
- `@testing-library/react`
- `jsdom`

## Commands

Backend full suite:

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
```

Backend dependency sync:

```bash
uv sync
```

Backend dependency sync with Whisper support:

```bash
uv sync --extra speech
```

The Whisper extra resolves `torch` from the PyTorch CPU wheel index by default, so local installs do not pull CUDA wheels unless you explicitly change the source configuration.
Other Python packages resolve through the Tsinghua PyPI mirror configured in the project `pyproject.toml`.

Frontend tests:

```bash
npm test
```

Frontend production build:

```bash
npm run build
```

## Covered Behavior

Current backend coverage includes:

- settings read and write behavior
- rejection of session creation without configured LLM settings
- session creation
- follow-up generation
- follow-up cap behavior
- wall-clock remaining time behavior
- structured report generation
- cumulative scoring across follow-up turns
- rejection of unsupported levels
- validation failure for unsupported durations
- history listing for completed sessions
- speech settings persistence
- transcription endpoint behavior in browser and whisper modes

Current frontend coverage includes:

- home page render
- history fetch on startup
- config flow defaulting to the supported `10` minute duration
- hiding unsupported duration options from the user
- opening the settings panel when no provider is configured
- live countdown updates during the interview
- voice input fallback on unsupported browsers
- voice transcript merge behavior on supported browsers
- voice language switching between Chinese and English
- Whisper-mode recording and transcript insertion

## Testing Strategy

- Prefer API-level tests for backend behavior rather than testing internal helpers only.
- Add regression tests first for user-visible bugs before modifying implementation.
- Keep frontend tests focused on rendered behavior and user-facing affordances.
- Run both backend and frontend checks before claiming completion.

## Known Gaps

- No browser end-to-end test suite yet
- No live integration test against a real OpenAI-compatible endpoint
- No persistence migration tests
- No visual regression tests
