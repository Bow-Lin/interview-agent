from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LLMSettingsRequest(BaseModel):
    provider: Literal["openai_compatible"]
    base_url: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    api_key: Optional[str] = None


class LLMSettingsResponse(BaseModel):
    configured: bool
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key_set: bool = False


class SpeechSettingsRequest(BaseModel):
    mode: Literal["browser", "whisper"]
    whisper_model: str = Field(..., min_length=1)


class SpeechSettingsResponse(BaseModel):
    mode: Literal["browser", "whisper"]
    whisper_model: str


class TranscriptionResponse(BaseModel):
    text: str


class QuestionSetSummary(BaseModel):
    id: str
    name: str
    source_type: Literal["system", "upload"]
    status: str
    question_count: int


class QuestionSetListResponse(BaseModel):
    question_sets: List[QuestionSetSummary]


class QuestionSetParseRequest(BaseModel):
    name: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    source_text: str = Field(..., min_length=1)


class QuestionDraft(BaseModel):
    draft_id: str
    question_text: str
    level: str
    expected_points: List[str]
    tags: List[str]
    reference_answer: str
    source_question: str
    source_answer: str
    warnings: List[str]


class QuestionSetDraft(BaseModel):
    name: str
    role: str
    questions: List[QuestionDraft]


class SessionCreateRequest(BaseModel):
    question_set_id: str = Field(..., min_length=1)
    role: str
    level: str
    duration_minutes: Literal[10, 20, 30]
    allow_followup: bool = True


class PromptPayload(BaseModel):
    question_id: str
    question_text: str
    prompt_type: Literal["main_question", "followup"]


class SessionCreateResponse(BaseModel):
    session_id: str
    question_set_id: str
    status: str
    question_index: int
    question_limit: int
    current_prompt: PromptPayload
    remaining_seconds: int


class AnswerRequest(BaseModel):
    answer: str = Field(..., min_length=1)


class AnswerResponse(BaseModel):
    event: Literal["followup", "next_question", "finished"]
    session_id: str
    status: str
    question_index: int
    followup_count: int
    remaining_seconds: int
    evaluation: Dict[str, Any]
    current_prompt: Optional[PromptPayload] = None
    report: Optional[Dict[str, Any]] = None


class SessionStatusResponse(BaseModel):
    session_id: str
    question_set_id: str
    status: str
    role: str
    level: str
    duration_minutes: int
    allow_followup: bool
    question_index: int
    question_limit: int
    remaining_seconds: int
    current_prompt: Optional[PromptPayload]


class HistoryResponse(BaseModel):
    sessions: List[Dict[str, Any]]
