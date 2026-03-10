# Coding Guidelines

## General

- Keep the backend simple and explicit; prefer direct Python logic over premature abstraction.
- Preserve ASCII-only source unless a file already requires Unicode.
- Add comments sparingly and only where the behavior is not obvious from the code.
- Prefer stable, deterministic behavior in the MVP over realism that is hard to test.

## Backend Conventions

- Keep FastAPI endpoint functions thin; business logic belongs in the interview engine or persistence layer.
- Keep SQLite access centralized in [`app/database.py`](/home/deming/work/interview-agent/app/database.py).
- Maintain strict request validation in Pydantic schemas before values reach the engine.
- Reject unsupported combinations explicitly; do not silently downgrade user intent.
- Treat per-question evaluation as cumulative across follow-up turns.
- Preserve the workflow seam in [`app/workflow.py`](/home/deming/work/interview-agent/app/workflow.py) even while the project uses the local fallback router.

## Frontend Conventions

- Keep the MVP frontend dependency-light.
- Prefer local state and clear view transitions over adding routing or state libraries too early.
- Frontend controls should only expose combinations the backend can currently satisfy.
- Surface backend failures as readable UI errors rather than swallowing them.

## Data and Persistence

- Seeded question content lives in code for now and should stay synchronized with what the UI exposes.
- Schema or seed changes that affect user-visible capability should be reflected in `docs/`.
- Avoid storing ephemeral build or cache artifacts in git.

## Documentation

- Update `docs/overview.md`, `docs/architecture.md`, `docs/api.md`, and `docs/testing.md` when behavior changes.
- Record documentation and architecture-affecting changes in `docs/CHANGELOG.md`.
