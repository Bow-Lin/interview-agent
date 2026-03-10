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
python3 -m unittest discover -s tests -p 'test_*.py'
```

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

- session creation
- follow-up generation
- follow-up cap behavior
- structured report generation
- cumulative scoring across follow-up turns
- rejection of unsupported levels
- validation failure for unsupported durations
- history listing for completed sessions

Current frontend coverage includes:

- home page render
- history fetch on startup
- config flow defaulting to the supported `10` minute duration
- hiding unsupported duration options from the user

## Testing Strategy

- Prefer API-level tests for backend behavior rather than testing internal helpers only.
- Add regression tests first for user-visible bugs before modifying implementation.
- Keep frontend tests focused on rendered behavior and user-facing affordances.
- Run both backend and frontend checks before claiming completion.

## Known Gaps

- No browser end-to-end test suite yet
- No coverage for real external LLM providers
- No persistence migration tests
- No visual regression tests
