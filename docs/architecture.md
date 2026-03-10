# Architecture

## System Shape

The application is split into a small local frontend and backend:

- React frontend in [`src/`](/home/deming/work/interview-agent/src)
- FastAPI backend in [`app/`](/home/deming/work/interview-agent/app)
- SQLite database file `interview_agent.db` for local persistence
- Python dependency and environment management through `uv` using [`pyproject.toml`](/home/deming/code/awesome-interview-agent/pyproject.toml) and `uv.lock`

The system runs as a local Web app rather than a desktop bundle.

## Backend Components

### API Layer

[`app/main.py`](/home/deming/work/interview-agent/app/main.py) creates the FastAPI application and exposes the session, answer, report, and history endpoints.
It also exposes persisted LLM settings endpoints.
It also enables local development CORS for Vite on `127.0.0.1:5173` and `localhost:5173`.

### Interview Engine

[`app/interview_engine.py`](/home/deming/work/interview-agent/app/interview_engine.py) owns interview progression:

- maps duration to question count
- creates sessions
- evaluates answers
- tracks remaining interview time from the session start timestamp
- tracks cumulative scoring per question across follow-ups
- decides whether to follow up, advance, or finish
- produces the final report

Current answer evaluation, follow-up generation, and report generation use a real OpenAI-compatible provider client from [`app/llm.py`](/home/deming/work/interview-agent/app/llm.py).
The engine refuses to start sessions unless LLM settings are configured.

### Workflow Seam

[`app/workflow.py`](/home/deming/work/interview-agent/app/workflow.py) provides a graph-style routing seam.
If `langgraph` is installed later, this file is the intended integration point.
Today it falls back to a local router with these states:

- `generate_followup`
- `advance_question`
- `finalize_report`

### Persistence Layer

[`app/database.py`](/home/deming/work/interview-agent/app/database.py) manages SQLite schema creation and all reads/writes.

Persisted tables:

- `question_bank`
- `interview_sessions`
- `question_records`
- `turn_records`
- `interview_reports`
- `llm_settings`

`llm_settings` currently stores `provider`, `base_url`, `model`, and `api_key` in plaintext.

## Frontend Components

[`src/App.tsx`](/home/deming/work/interview-agent/src/App.tsx) is a single-page React application with four view states:

- `home`
- `config`
- `interview`
- `report`

The frontend currently avoids a router dependency and switches views via local React state.
LLM configuration is handled through a modal-style settings panel rather than a login flow.

[`src/styles.css`](/home/deming/work/interview-agent/src/styles.css) contains the visual system and layout styling.

## Data Flow

1. The frontend loads `/settings/llm` and `/history` on startup.
2. If needed, the user saves provider configuration through `PUT /settings/llm`.
3. The frontend posts interview configuration to `POST /sessions`.
4. The backend selects seeded questions for the requested role/level.
5. Each answer is stored in `turn_records`.
6. The engine evaluates the cumulative answer for the current question through the OpenAI-compatible endpoint.
7. The workflow decides whether to ask a follow-up, move to the next question, or finish.
8. The final report is generated through the same provider, persisted, and returned to the frontend.
9. History reads from completed sessions and stored reports.

## Important Current Constraints

- The question bank is seeded in code from [`app/data.py`](/home/deming/work/interview-agent/app/data.py).
- Role/level combinations without enough questions are rejected instead of silently downgraded.
- The frontend only exposes durations the current seed data can satisfy.
- The backend already validates durations at the schema level to prevent unsupported values such as `15`.
- The provider integration currently targets `POST /chat/completions` on an OpenAI-compatible base URL.
