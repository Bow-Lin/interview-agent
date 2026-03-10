import json
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

import httpx


@dataclass
class LLMSettings:
    provider: str
    base_url: str
    model: str
    api_key: str


@dataclass
class EvaluationResult:
    quality: str
    score: int
    missing_points: List[str]
    strengths: List[str]
    should_followup: bool
    followup_focus: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "quality": self.quality,
            "score": self.score,
            "missing_points": self.missing_points,
            "strengths": self.strengths,
            "should_followup": self.should_followup,
            "followup_focus": self.followup_focus,
        }


class LLMClient(Protocol):
    async def evaluate_answer(
        self,
        *,
        settings: LLMSettings,
        question_text: str,
        answer: str,
        expected_points: List[str],
        followup_count: int,
        allow_followup: bool,
    ) -> EvaluationResult:
        ...

    async def generate_followup(
        self,
        *,
        settings: LLMSettings,
        question_text: str,
        missing_points: List[str],
    ) -> str:
        ...

    async def generate_report(
        self,
        *,
        settings: LLMSettings,
        role: str,
        question_summaries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        ...


class OpenAICompatibleLLMClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def evaluate_answer(
        self,
        *,
        settings: LLMSettings,
        question_text: str,
        answer: str,
        expected_points: List[str],
        followup_count: int,
        allow_followup: bool,
    ) -> EvaluationResult:
        payload = await self._chat_json(
            settings=settings,
            system_prompt=(
                "You are an interview evaluator. Return only valid JSON. "
                "Required keys: quality, score, missing_points, strengths, should_followup, followup_focus. "
                "quality must be one of good, partial, weak, off_topic. "
                "score must be an integer from 0 to 100."
            ),
            user_prompt=(
                f"Question: {question_text}\n"
                f"Expected points: {json.dumps(expected_points)}\n"
                f"Candidate answer: {answer}\n"
                f"Current follow-up count: {followup_count}\n"
                f"Follow-ups allowed: {allow_followup}\n"
                "Respond with JSON only."
            ),
        )
        missing_points = self._ensure_list(payload.get("missing_points"))
        strengths = self._ensure_list(payload.get("strengths"))
        should_followup = allow_followup and bool(missing_points) and followup_count < 2
        followup_focus = str(payload.get("followup_focus") or (missing_points[0] if missing_points else ""))
        return EvaluationResult(
            quality=str(payload.get("quality", "partial")),
            score=int(payload.get("score", 60)),
            missing_points=missing_points,
            strengths=strengths,
            should_followup=should_followup,
            followup_focus=followup_focus,
        )

    async def generate_followup(
        self,
        *,
        settings: LLMSettings,
        question_text: str,
        missing_points: List[str],
    ) -> str:
        payload = await self._chat_json(
            settings=settings,
            system_prompt=(
                "You are an interviewer writing a single concise follow-up question. "
                "Return only valid JSON with one key: followup_question."
            ),
            user_prompt=(
                f"Original question: {question_text}\n"
                f"Missing points: {json.dumps(missing_points)}\n"
                "Generate one focused follow-up question."
            ),
        )
        followup = str(payload.get("followup_question", "")).strip()
        if not followup:
            raise ValueError("LLM follow-up response was empty")
        return followup

    async def generate_report(
        self,
        *,
        settings: LLMSettings,
        role: str,
        question_summaries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = await self._chat_json(
            settings=settings,
            system_prompt=(
                "You are generating a mock interview report. Return only valid JSON. "
                "Required keys: total_score, knowledge_score, communication_score, system_design_score, "
                "strengths, weaknesses, suggestions, summary."
            ),
            user_prompt=(
                f"Role: {role}\n"
                f"Question summaries: {json.dumps(question_summaries, ensure_ascii=True)}\n"
                "Produce a structured interview report."
            ),
        )
        return {
            "total_score": int(payload.get("total_score", 0)),
            "knowledge_score": int(payload.get("knowledge_score", 0)),
            "communication_score": int(payload.get("communication_score", 0)),
            "system_design_score": int(payload.get("system_design_score", 0)),
            "strengths": self._ensure_list(payload.get("strengths")),
            "weaknesses": self._ensure_list(payload.get("weaknesses")),
            "suggestions": self._ensure_list(payload.get("suggestions")),
            "summary": str(payload.get("summary", "")).strip(),
        }

    async def _chat_json(
        self, *, settings: LLMSettings, system_prompt: str, user_prompt: str
    ) -> Dict[str, Any]:
        url = settings.base_url.rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            body = response.json()
        content = body["choices"][0]["message"]["content"]
        return self._parse_json_content(content)

    @staticmethod
    def _parse_json_content(content: Any) -> Dict[str, Any]:
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str):
            raise ValueError("LLM response content was not text")
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("LLM response did not contain JSON")
        return json.loads(content[start : end + 1])

    @staticmethod
    def _ensure_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]
