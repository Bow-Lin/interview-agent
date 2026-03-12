import os
import tempfile
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.database import Database
from app.interview_engine import InterviewEngine
from app.llm import OpenAICompatibleLLMClient
from app.schemas import (
    AnswerRequest,
    AnswerResponse,
    HistoryResponse,
    LLMSettingsRequest,
    LLMSettingsResponse,
    QuestionSetListResponse,
    QuestionSetSummary,
    SpeechSettingsRequest,
    SpeechSettingsResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionStatusResponse,
    TranscriptionResponse,
)
from app.speech import SpeechTranscriptionUnavailable, WhisperSpeechTranscriber


def create_app(testing: bool = False, llm_client=None, speech_transcriber=None) -> FastAPI:
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
    engine = InterviewEngine(database, llm_client=llm_client or OpenAICompatibleLLMClient())
    transcriber = speech_transcriber or WhisperSpeechTranscriber()

    @app.get("/settings/llm", response_model=LLMSettingsResponse)
    async def get_llm_settings():
        settings = database.get_llm_settings()
        if settings is None:
            return {
                "configured": False,
                "provider": None,
                "base_url": None,
                "model": None,
                "api_key_set": False,
            }
        return {
            "configured": True,
            "provider": settings["provider"],
            "base_url": settings["base_url"],
            "model": settings["model"],
            "api_key_set": bool(settings["api_key"]),
        }

    @app.put("/settings/llm", response_model=LLMSettingsResponse)
    async def put_llm_settings(payload: LLMSettingsRequest):
        existing = database.get_llm_settings()
        base_url = payload.base_url.strip()
        model = payload.model.strip()
        if not base_url or not model:
            raise HTTPException(status_code=400, detail="Base URL and model are required")
        api_key = (
            payload.api_key.strip()
            if payload.api_key is not None and payload.api_key.strip()
            else (existing["api_key"] if existing else "")
        )
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")
        database.upsert_llm_settings(
            provider=payload.provider,
            base_url=base_url,
            model=model,
            api_key=api_key,
        )
        return {
            "configured": True,
            "provider": payload.provider,
            "base_url": base_url,
            "model": model,
            "api_key_set": True,
        }

    @app.get("/settings/speech", response_model=SpeechSettingsResponse)
    async def get_speech_settings():
        return database.get_speech_settings()

    @app.put("/settings/speech", response_model=SpeechSettingsResponse)
    async def put_speech_settings(payload: SpeechSettingsRequest):
        whisper_model = payload.whisper_model.strip()
        if not whisper_model:
            raise HTTPException(status_code=400, detail="Whisper model is required")
        database.upsert_speech_settings(
            mode=payload.mode,
            whisper_model=whisper_model,
        )
        return {
            "mode": payload.mode,
            "whisper_model": whisper_model,
        }

    @app.post("/sessions", response_model=SessionCreateResponse, status_code=201)
    async def create_session(payload: SessionCreateRequest):
        try:
            return engine.create_session(
                question_set_id=payload.question_set_id,
                role=payload.role,
                level=payload.level,
                duration_minutes=payload.duration_minutes,
                allow_followup=payload.allow_followup,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/question-sets", response_model=QuestionSetListResponse)
    async def get_question_sets():
        return {"question_sets": engine.list_question_sets()}

    @app.post("/question-sets/import", response_model=QuestionSetSummary, status_code=201)
    async def import_question_set(file: UploadFile = File(...)):
        try:
            payload = json.loads((await file.read()).decode("utf-8"))
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Question bank file must be UTF-8 encoded JSON")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Question bank file must be valid JSON")
        finally:
            await file.close()

        try:
            return engine.import_question_set(payload)
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
            return await engine.answer(session_id, payload.answer)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/sessions/{session_id}/finish")
    async def finish_session(session_id: str):
        try:
            return await engine.finish_session(session_id)
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

    @app.post("/transcriptions", response_model=TranscriptionResponse)
    async def transcribe_audio(
        file: UploadFile = File(...),
        language_hint: Optional[str] = Form(default=None),
    ):
        speech_settings = database.get_speech_settings()
        if speech_settings["mode"] != "whisper":
            raise HTTPException(
                status_code=400,
                detail="Speech mode must be set to whisper before using server transcription.",
            )

        suffix = Path(file.filename or "recording.webm").suffix or ".webm"
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(await file.read())
                temp_path = Path(temp_file.name)
            text = transcriber.transcribe(
                audio_path=temp_path,
                model_name=speech_settings["whisper_model"],
                language_hint=language_hint.strip() if language_hint else None,
            )
        except SpeechTranscriptionUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        finally:
            await file.close()
            if temp_path and temp_path.exists():
                os.unlink(temp_path)

        return {"text": text}

    return app


app = create_app()
