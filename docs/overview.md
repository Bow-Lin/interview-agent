# Interview Agent Overview

## Goal

Interview Agent is a local single-user Web application for mock interview practice.
The current MVP focuses on a complete text-based loop:

- create a session
- ask a question from a local question bank
- evaluate the answer
- optionally ask a follow-up
- finish with a structured report
- store the session in local history

## Current Product Scope

Implemented in the current repository:

- React single-page frontend
- FastAPI backend
- local SQLite persistence
- question-bank-driven interviews
- follow-up generation with a deterministic mock evaluator
- final report generation
- local history view

Out of scope in the current implementation:

- authentication or multi-user isolation
- cloud sync
- voice or video interview flows
- resume parsing
- external LLM integration
- real LangGraph runtime dependency

## User Flow

1. Open the home page and start a mock interview.
2. Configure role, level, duration, and follow-up behavior.
3. Answer the active prompt in text.
4. Receive either a follow-up, the next main question, or the final report.
5. Review the report and revisit completed sessions from history.

## Supported Roles and Limits

Current seeded content supports:

- `agent_engineer` at `mid`
- `backend_engineer` at `junior`
- `frontend_engineer` at `mid`
- `algorithm_engineer` at `mid`

Current UI exposure is intentionally constrained to the working path:

- only `10` minute interviews are selectable in the frontend
- `10` minute interviews map to `3` main questions
- each question can trigger at most `2` follow-ups

## Runtime Model

This project is intended to run locally:

- backend: `uvicorn app.main:app --reload`
- frontend: `npm run dev`

The frontend talks to the backend over local HTTP at `http://127.0.0.1:8000` by default.
