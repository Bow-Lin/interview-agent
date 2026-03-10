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
- persisted OpenAI-compatible LLM settings
- persisted speech input settings
- question-bank-driven interviews
- browser-based voice input for interview answers on supported desktop browsers
- optional server-side Whisper transcription for recorded answers
- real LLM-backed answer evaluation
- real LLM-backed follow-up generation
- final report generation
- local history view

Out of scope in the current implementation:

- authentication or multi-user isolation
- cloud sync
- voice or video interview flows
- resume parsing
- real LangGraph runtime dependency

## User Flow

1. Open the home page and start a mock interview.
2. If no provider is configured yet, open `Settings` and save `base URL`, `model`, and `API key`.
3. Configure role, level, duration, and follow-up behavior.
4. Choose browser speech recognition or server-side Whisper in `Settings`.
5. Answer the active prompt in text or with optional voice input.
6. Receive either a follow-up, the next main question, or the final report.
7. Review the report and revisit completed sessions from history.

Voice input is optional and fills the answer box before submission. Browser mode uses native speech recognition with Chinese or English selection. Whisper mode records audio in the browser and sends it to the backend for server-side transcription.

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

- backend setup: `uv sync`
- optional Whisper speech dependencies: `uv sync --extra speech`
- backend: `uv run uvicorn app.main:app --reload`
- frontend: `npm run dev`

The frontend talks to the backend over local HTTP at `http://127.0.0.1:8000` by default.
Python dependencies are managed with `uv` from [`pyproject.toml`](/home/deming/code/awesome-interview-agent/pyproject.toml) and the checked-in `uv.lock`. Project-level `uv` configuration uses the Tsinghua PyPI mirror by default, while the Whisper extra resolves `torch` from the PyTorch CPU wheel index to avoid large CUDA downloads on machines that only need CPU transcription.
Whisper mode also requires `ffmpeg` to be installed on the machine.

## LLM Configuration

The current MVP expects a real OpenAI-compatible chat-completions endpoint.

Required user-provided settings:

- `provider`: `openai_compatible`
- `base_url`
- `model`
- `api_key`

Settings are stored locally by the backend in plaintext for now.
Replacing this with a system credential store is tracked in [`docs/TODO.md`](/home/deming/work/interview-agent/docs/TODO.md).
