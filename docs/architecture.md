# Architecture

## System Shape

The application is split into a small local frontend and backend:

- React frontend in [`src/`](/home/deming/work/awesome-interview-agent/src)
- FastAPI backend in [`app/`](/home/deming/work/awesome-interview-agent/app)
- SQLite database file `interview_agent.db` for local persistence

The system runs as a local Web app rather than a desktop bundle.

## Backend Components

### API Layer

[`app/main.py`](/home/deming/work/awesome-interview-agent/app/main.py) creates the FastAPI application and exposes the session, answer, report, and history endpoints.
It also enables local development CORS for Vite on `127.0.0.1:5173` and `localhost:5173`.

### Interview Engine

[`app/interview_engine.py`](/home/deming/work/awesome-interview-agent/app/interview_engine.py) owns interview progression:

- maps duration to question count
- creates sessions
- evaluates answers
- tracks cumulative scoring per question across follow-ups
- decides whether to follow up, advance, or finish
- produces the final report

Current answer evaluation and report generation use `MockLLMClient`.
This is deterministic logic based on keyword overlap, not a real model provider.

### Workflow Seam

[`app/workflow.py`](/home/deming/work/awesome-interview-agent/app/workflow.py) provides a graph-style routing seam.
If `langgraph` is installed later, this file is the intended integration point.
Today it falls back to a local router with these states:

- `generate_followup`
- `advance_question`
- `finalize_report`

### Persistence Layer

[`app/database.py`](/home/deming/work/awesome-interview-agent/app/database.py) manages SQLite schema creation and all reads/writes.

Persisted tables:

- `question_bank`
- `interview_sessions`
- `question_records`
- `turn_records`
- `interview_reports`

## Frontend Components

[`src/App.tsx`](/home/deming/work/awesome-interview-agent/src/App.tsx) is a single-page React application with four view states:

- `home`
- `config`
- `interview`
- `report`

The frontend currently avoids a router dependency and switches views via local React state.

[`src/styles.css`](/home/deming/work/awesome-interview-agent/src/styles.css) contains the visual system and layout styling.

## Data Flow

1. The frontend posts configuration to `POST /sessions`.
2. The backend selects seeded questions for the requested role/level.
3. Each answer is stored in `turn_records`.
4. The engine evaluates the cumulative answer for the current question.
5. The workflow decides whether to ask a follow-up, move to the next question, or finish.
6. The final report is persisted and then returned to the frontend.
7. History reads from completed sessions and stored reports.

## Important Current Constraints

- The question bank is seeded in code from [`app/data.py`](/home/deming/work/awesome-interview-agent/app/data.py).
- Role/level combinations without enough questions are rejected instead of silently downgraded.
- The frontend only exposes durations the current seed data can satisfy.
- The backend already validates durations at the schema level to prevent unsupported values such as `15`.
