# References

## Internal References

- Backend entrypoint: [`app/main.py`](/home/deming/work/interview-agent/app/main.py)
- Interview engine: [`app/interview_engine.py`](/home/deming/work/interview-agent/app/interview_engine.py)
- Database layer: [`app/database.py`](/home/deming/work/interview-agent/app/database.py)
- LLM provider client: [`app/llm.py`](/home/deming/work/interview-agent/app/llm.py)
- Question seed data: [`app/data.py`](/home/deming/work/interview-agent/app/data.py)
- Workflow seam: [`app/workflow.py`](/home/deming/work/interview-agent/app/workflow.py)
- Frontend application: [`src/App.tsx`](/home/deming/work/interview-agent/src/App.tsx)
- Backend tests: [`tests/test_sessions_api.py`](/home/deming/work/interview-agent/tests/test_sessions_api.py)
- History test: [`tests/test_history_api.py`](/home/deming/work/interview-agent/tests/test_history_api.py)

## Design Notes

- The current workflow keeps a LangGraph-compatible seam without requiring `langgraph` at runtime.
- The current provider contract targets OpenAI-compatible `chat/completions` APIs.
- The frontend intentionally stays as a single-page state machine until the UI surface becomes large enough to justify routing.
- API keys are intentionally hidden from `GET /settings/llm`, even though the current backend persistence is plaintext.
