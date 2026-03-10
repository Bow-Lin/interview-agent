from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.database import Database
from app.interview_engine import InterviewEngine
from app.schemas import (
    AnswerRequest,
    AnswerResponse,
    HistoryResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionStatusResponse,
)


def create_app(testing: bool = False) -> FastAPI:
    app = FastAPI(title="Interview Agent MVP")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    database = Database(":memory:" if testing else "interview_agent.db")
    engine = InterviewEngine(database)

    @app.post("/sessions", response_model=SessionCreateResponse, status_code=201)
    async def create_session(payload: SessionCreateRequest):
        try:
            return engine.create_session(
                role=payload.role,
                level=payload.level,
                duration_minutes=payload.duration_minutes,
                allow_followup=payload.allow_followup,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/sessions/{session_id}", response_model=SessionStatusResponse)
    async def get_session(session_id: str):
        try:
            return engine.get_session_status(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")

    @app.post("/sessions/{session_id}/answer", response_model=AnswerResponse)
    async def answer_session(session_id: str, payload: AnswerRequest):
        try:
            return engine.answer(session_id, payload.answer)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/sessions/{session_id}/finish")
    async def finish_session(session_id: str):
        try:
            return engine.finish_session(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")

    @app.get("/reports/{session_id}")
    async def get_report(session_id: str):
        try:
            return engine.get_report(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Report not found")

    @app.get("/history", response_model=HistoryResponse)
    async def history():
        return {"sessions": engine.list_history()}

    return app


app = create_app()
