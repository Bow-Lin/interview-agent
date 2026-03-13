import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.data import VALID_LEVELS, VALID_ROLES
from app.database import Database
from app.llm import EvaluationResult, LLMClient, LLMSettings
from app.workflow import InterviewWorkflow


QUESTION_LIMITS = {
    10: 3,
    20: 5,
    30: 7,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seconds_since(started_at: str, current_time: str) -> int:
    started = datetime.fromisoformat(started_at)
    current = datetime.fromisoformat(current_time)
    return max(0, int((current - started).total_seconds()))


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]+", " ", text.lower())


def keyword_hits(answer: str, expected_points: Iterable[str]) -> Dict[str, bool]:
    normalized = normalize_text(answer)
    answer_tokens = set(normalized.split())
    point_hits: Dict[str, bool] = {}
    for point in expected_points:
        point_tokens = [token for token in normalize_text(point).split() if token]
        hit_count = sum(1 for token in point_tokens if token in answer_tokens)
        point_hits[point] = bool(point_tokens) and hit_count >= max(1, len(point_tokens) // 2)
    return point_hits


class InterviewEngine:
    def __init__(self, database: Database, llm_client: LLMClient) -> None:
        self.database = database
        self.llm_client = llm_client
        self.workflow = InterviewWorkflow()

    def create_session(
        self,
        question_set_id: str,
        role: str,
        level: str,
        duration_minutes: int,
        allow_followup: bool,
    ) -> Dict[str, Any]:
        self._require_llm_settings()
        question_limit = QUESTION_LIMITS[duration_minutes]
        try:
            question_set = self.database.get_question_set(question_set_id)
        except KeyError as exc:
            raise ValueError(f"Question bank '{question_set_id}' was not found") from exc
        if question_set["status"] != "ready":
            raise ValueError(f"Question bank '{question_set_id}' is unavailable")
        questions = self.database.get_questions(question_set_id, role, level, question_limit)
        if len(questions) < question_limit:
            raise ValueError(
                f"Not enough questions for question_set={question_set_id} role={role} level={level}"
            )
        session_id = str(uuid.uuid4())
        started_at = utc_now()
        selected_question_ids = [question["id"] for question in questions]
        self.database.create_session(
            session_id=session_id,
            question_set_id=question_set_id,
            role=role,
            level=level,
            duration_minutes=duration_minutes,
            allow_followup=allow_followup,
            started_at=started_at,
            question_limit=question_limit,
            selected_question_ids=selected_question_ids,
        )
        current_question = questions[0]
        question_record_id = self.database.ensure_question_record(
            session_id, current_question["id"], current_question["question_text"], 0
        )
        self.database.add_turn(
            session_id,
            question_record_id,
            "main_question",
            current_question["question_text"],
        )
        return {
            "session_id": session_id,
            "question_set_id": question_set_id,
            "status": "in_progress",
            "question_index": 0,
            "question_limit": question_limit,
            "remaining_seconds": duration_minutes * 60,
            "current_prompt": {
                "question_id": current_question["id"],
                "question_text": current_question["question_text"],
                "prompt_type": "main_question",
            },
        }

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        session = self.database.get_session(session_id)
        remaining_seconds = self._sync_remaining_seconds(session)
        current_prompt = None
        if session["status"] == "in_progress":
            current_prompt = self._build_current_prompt(session)
        return {
            "session_id": session_id,
            "question_set_id": session["question_set_id"],
            "status": session["status"],
            "role": session["role"],
            "level": session["level"],
            "duration_minutes": session["duration_minutes"],
            "allow_followup": bool(session["allow_followup"]),
            "question_index": session["current_question_index"],
            "question_limit": session["question_limit"],
            "remaining_seconds": remaining_seconds,
            "current_prompt": current_prompt,
        }

    async def answer(self, session_id: str, answer: str) -> Dict[str, Any]:
        session = self.database.get_session(session_id)
        if session["status"] != "in_progress":
            raise ValueError("Session is not active")
        remaining_seconds = self._sync_remaining_seconds(session)
        selected_question_ids = json.loads(session["selected_question_ids"])
        question_id = selected_question_ids[session["current_question_index"]]
        question = self.database.get_question(question_id)
        question_record = self.database.get_question_record(session_id, question_id)
        followup_count = self.database.count_followups(question_record["id"])
        llm_settings = self._require_llm_settings()
        prior_answers = [
            turn["content"]
            for turn in self.database.list_turns(question_record["id"])
            if turn["turn_type"] == "user_answer"
        ]
        cumulative_answer = " ".join(prior_answers + [answer])

        evaluation = await self.llm_client.evaluate_answer(
            settings=llm_settings,
            question_text=question["question_text"],
            answer=cumulative_answer,
            expected_points=question["expected_points"],
            followup_count=followup_count,
            allow_followup=bool(session["allow_followup"]),
        )
        self.database.add_turn(
            session_id,
            question_record["id"],
            "user_answer",
            answer,
            evaluation.as_dict(),
        )
        self.database.update_question_record(
            question_record["id"],
            final_score=evaluation.score,
            answer_quality=evaluation.quality,
            strengths=evaluation.strengths,
            missing_points=evaluation.missing_points,
            summary=self._build_question_summary(question["question_text"], evaluation),
        )
        session = self.database.get_session(session_id)
        remaining_seconds = self._sync_remaining_seconds(session)

        route = self.workflow.route_after_evaluation(
            {
                "should_followup": evaluation.should_followup,
                "remaining_seconds": remaining_seconds,
                "next_index": session["current_question_index"] + 1,
                "question_limit": session["question_limit"],
            }
        )

        if route == "generate_followup":
            followup_text = await self.llm_client.generate_followup(
                settings=llm_settings,
                question_text=question["question_text"],
                missing_points=evaluation.missing_points,
            )
            self.database.add_turn(
                session_id,
                question_record["id"],
                "followup",
                followup_text,
                evaluation.as_dict(),
            )
            return {
                "event": "followup",
                "session_id": session_id,
                "status": "in_progress",
                "question_index": session["current_question_index"],
                "followup_count": followup_count + 1,
                "remaining_seconds": remaining_seconds,
                "evaluation": evaluation.as_dict(),
                "current_prompt": {
                    "question_id": question["id"],
                    "question_text": followup_text,
                    "prompt_type": "followup",
                },
            }

        next_index = session["current_question_index"] + 1
        if route == "finalize_report":
            report = await self.finish_session(session_id)
            return {
                "event": "finished",
                "session_id": session_id,
                "status": "completed",
                "question_index": session["current_question_index"],
                "followup_count": followup_count,
                "remaining_seconds": remaining_seconds,
                "evaluation": evaluation.as_dict(),
                "report": report,
                "current_prompt": None,
            }

        self.database.update_session(session_id, current_question_index=next_index)
        next_question = self.database.get_question(selected_question_ids[next_index])
        next_record_id = self.database.ensure_question_record(
            session_id, next_question["id"], next_question["question_text"], next_index
        )
        self.database.add_turn(
            session_id,
            next_record_id,
            "main_question",
            next_question["question_text"],
        )
        return {
            "event": "next_question",
            "session_id": session_id,
            "status": "in_progress",
            "question_index": next_index,
            "followup_count": 0,
            "remaining_seconds": remaining_seconds,
            "evaluation": evaluation.as_dict(),
            "current_prompt": {
                "question_id": next_question["id"],
                "question_text": next_question["question_text"],
                "prompt_type": "main_question",
            },
        }

    async def finish_session(self, session_id: str) -> Dict[str, Any]:
        session = self.database.get_session(session_id)
        remaining_seconds = self._sync_remaining_seconds(session)
        llm_settings = self._require_llm_settings()
        question_records = self.database.list_question_records(session_id)
        question_summaries = [
            {
                "question_id": record["question_id"],
                "question_text": record["question_text"],
                "score": record["final_score"],
                "answer_quality": record["answer_quality"],
                "strengths": json.loads(record["strengths"]),
                "missing_points": json.loads(record["missing_points"]),
                "summary": record["summary"],
                "turns": self._serialize_turns(record["id"]),
            }
            for record in question_records
        ]
        report = await self.llm_client.generate_report(
            settings=llm_settings,
            role=session["role"],
            question_summaries=question_summaries,
        )
        self.database.save_report(
            session_id=session_id,
            total_score=report["total_score"],
            knowledge_score=report["knowledge_score"],
            communication_score=report["communication_score"],
            system_design_score=report["system_design_score"],
            strengths=report["strengths"],
            weaknesses=report["weaknesses"],
            suggestions=report["suggestions"],
            summary=report["summary"],
            question_summaries=question_summaries,
        )
        self.database.update_session(
            session_id,
            status="completed",
            ended_at=utc_now(),
            remaining_seconds=remaining_seconds,
        )
        return {
            "session_id": session_id,
            **report,
            "question_summaries": question_summaries,
        }

    def get_report(self, session_id: str) -> Dict[str, Any]:
        return self.database.get_report(session_id)

    def list_history(self) -> List[Dict[str, Any]]:
        return self.database.list_history()

    def list_question_sets(self) -> List[Dict[str, Any]]:
        return self.database.list_question_sets()

    def soft_delete_question_set(self, question_set_id: str) -> None:
        self.database.soft_delete_question_set(question_set_id)

    async def parse_question_set_text(
        self, *, name: str, role: str, source_text: str
    ) -> Dict[str, Any]:
        llm_settings = self._require_llm_settings()
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Question bank name is required")
        normalized_role = role.strip()
        if normalized_role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{normalized_role}'")
        qa_pairs = self._extract_qa_pairs(source_text)
        payload = await self.llm_client.parse_question_bank_text(
            settings=llm_settings,
            role=normalized_role,
            qa_pairs=qa_pairs,
        )
        if not isinstance(payload, dict):
            raise ValueError("LLM parse response must be a JSON object")

        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list) or len(raw_questions) != len(qa_pairs):
            raise ValueError("LLM parse response must return one question per QA pair")

        draft_questions: List[Dict[str, Any]] = []
        for index, (pair, raw_question) in enumerate(zip(qa_pairs, raw_questions), start=1):
            if not isinstance(raw_question, dict):
                raise ValueError(f"Draft question #{index} must be an object")

            question_text = str(raw_question.get("question_text", "")).strip() or pair["question"]
            level = str(raw_question.get("level", "")).strip()
            if level not in VALID_LEVELS:
                raise ValueError(f"Draft question #{index} returned invalid level '{level}'")

            expected_points = raw_question.get("expected_points")
            if (
                not isinstance(expected_points, list)
                or not expected_points
                or not all(isinstance(point, str) and point.strip() for point in expected_points)
            ):
                raise ValueError(
                    f"Draft question #{index} must include a non-empty expected_points array"
                )

            tags = raw_question.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise ValueError(f"Draft question #{index} must include a tags string array")

            reference_answer = (
                str(raw_question.get("reference_answer", "")).strip() or pair["answer"]
            )
            if not reference_answer:
                raise ValueError(f"Draft question #{index} is missing reference_answer")

            warnings = raw_question.get("warnings", [])
            if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
                raise ValueError(f"Draft question #{index} must include a warnings string array")

            draft_questions.append(
                {
                    "draft_id": f"draft-{index}",
                    "question_text": question_text,
                    "level": level,
                    "expected_points": [point.strip() for point in expected_points],
                    "tags": [tag.strip() for tag in tags if tag.strip()],
                    "reference_answer": reference_answer,
                    "source_question": pair["question"],
                    "source_answer": pair["answer"],
                    "warnings": [warning.strip() for warning in warnings if warning.strip()],
                }
            )

        return {
            "name": normalized_name,
            "role": normalized_role,
            "questions": draft_questions,
        }

    def import_question_set(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Question bank payload must be a JSON object")
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Question bank name is required")

        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list) or not raw_questions:
            raise ValueError("Question bank must include at least one question")

        normalized_questions: List[Dict[str, Any]] = []
        seen_ids = set()
        for index, raw_question in enumerate(raw_questions, start=1):
            if not isinstance(raw_question, dict):
                raise ValueError(f"Question #{index} must be an object")

            question_id = str(raw_question.get("id", "")).strip()
            if not question_id:
                raise ValueError(f"Question #{index} is missing an id")
            if question_id in seen_ids:
                raise ValueError(f"Duplicate question id '{question_id}' in uploaded question bank")
            seen_ids.add(question_id)

            role = str(raw_question.get("role", "")).strip()
            if role not in VALID_ROLES:
                raise ValueError(f"Invalid role '{role}' for question '{question_id}'")

            level = str(raw_question.get("level", "")).strip()
            if level not in VALID_LEVELS:
                raise ValueError(f"Invalid level '{level}' for question '{question_id}'")

            question_text = str(raw_question.get("question_text", "")).strip()
            if not question_text:
                raise ValueError(f"Question '{question_id}' is missing question_text")

            reference_answer = str(raw_question.get("reference_answer", "")).strip()
            if not reference_answer:
                raise ValueError(f"Question '{question_id}' is missing reference_answer")

            expected_points = raw_question.get("expected_points")
            if (
                not isinstance(expected_points, list)
                or not expected_points
                or not all(isinstance(point, str) and point.strip() for point in expected_points)
            ):
                raise ValueError(
                    f"Question '{question_id}' must include a non-empty expected_points array"
                )

            tags = raw_question.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise ValueError(f"Question '{question_id}' must include a tags string array")

            normalized_questions.append(
                {
                    "id": question_id,
                    "role": role,
                    "level": level,
                    "question_text": question_text,
                    "expected_points": [point.strip() for point in expected_points],
                    "tags": [tag.strip() for tag in tags if tag.strip()],
                    "reference_answer": reference_answer,
                }
            )

        return self.database.create_question_set(name, normalized_questions)

    def import_question_set_draft(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Question bank draft payload must be a JSON object")

        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Question bank name is required")

        role = str(payload.get("role", "")).strip()
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'")

        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list) or not raw_questions:
            raise ValueError("Question bank draft must include at least one question")

        normalized_questions: List[Dict[str, Any]] = []
        for index, raw_question in enumerate(raw_questions, start=1):
            if not isinstance(raw_question, dict):
                raise ValueError(f"Draft question #{index} must be an object")

            question_text = str(raw_question.get("question_text", "")).strip()
            if not question_text:
                raise ValueError(f"Draft question #{index} is missing question_text")

            level = str(raw_question.get("level", "")).strip()
            if level not in VALID_LEVELS:
                raise ValueError(f"Draft question #{index} returned invalid level '{level}'")

            reference_answer = str(raw_question.get("reference_answer", "")).strip()
            if not reference_answer:
                raise ValueError(f"Draft question #{index} is missing reference_answer")

            expected_points = raw_question.get("expected_points")
            if (
                not isinstance(expected_points, list)
                or not expected_points
                or not all(isinstance(point, str) and point.strip() for point in expected_points)
            ):
                raise ValueError(
                    f"Draft question #{index} must include a non-empty expected_points array"
                )

            tags = raw_question.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise ValueError(f"Draft question #{index} must include a tags string array")

            normalized_questions.append(
                {
                    "id": f"generated_{index:03d}",
                    "role": role,
                    "level": level,
                    "question_text": question_text,
                    "expected_points": [point.strip() for point in expected_points],
                    "tags": [tag.strip() for tag in tags if tag.strip()],
                    "reference_answer": reference_answer,
                }
            )

        return self.database.create_question_set(name, normalized_questions)

    def _build_current_prompt(self, session: Any) -> Dict[str, Any]:
        selected_question_ids = json.loads(session["selected_question_ids"])
        question_id = selected_question_ids[session["current_question_index"]]
        question = self.database.get_question(question_id)
        question_record = self.database.get_question_record(session["id"], question_id)
        turns = self.database.list_turns(question_record["id"])
        if turns and turns[-1]["turn_type"] == "followup":
            return {
                "question_id": question_id,
                "question_text": turns[-1]["content"],
                "prompt_type": "followup",
            }
        return {
            "question_id": question_id,
            "question_text": question["question_text"],
            "prompt_type": "main_question",
        }

    def _serialize_turns(self, question_record_id: str) -> List[Dict[str, Any]]:
        turns = self.database.list_turns(question_record_id)
        serialized = []
        for turn in turns:
            serialized.append(
                {
                    "turn_type": turn["turn_type"],
                    "content": turn["content"],
                    "sequence": turn["sequence"],
                    "evaluation_snapshot": json.loads(turn["evaluation_snapshot"]),
                }
            )
        return serialized

    @staticmethod
    def _build_question_summary(question_text: str, evaluation: EvaluationResult) -> str:
        if evaluation.quality == "good":
            return f"The candidate answered '{question_text}' with strong coverage."
        if evaluation.missing_points:
            return (
                f"The answer covered some basics but missed: "
                + ", ".join(evaluation.missing_points[:2])
                + "."
            )
        return f"The answer to '{question_text}' needs more structure."

    def _require_llm_settings(self) -> LLMSettings:
        raw_settings = self.database.get_llm_settings()
        if raw_settings is None:
            raise ValueError("LLM settings are not configured")
        return LLMSettings(**raw_settings)

    @staticmethod
    def _extract_qa_pairs(source_text: str) -> List[Dict[str, str]]:
        question_pattern = re.compile(r"^\s*(?:[-*]\s*)?(?:q|question)\s*[:：\-]\s*(.+)$", re.IGNORECASE)
        answer_pattern = re.compile(r"^\s*(?:[-*]\s*)?(?:a|answer)\s*[:：\-]\s*(.+)$", re.IGNORECASE)

        pairs: List[Dict[str, str]] = []
        current_question = ""
        current_answer_lines: List[str] = []
        mode: Optional[str] = None

        for raw_line in source_text.splitlines():
            line = raw_line.strip()
            if not line:
                if mode == "answer" and current_answer_lines:
                    current_answer_lines.append("")
                continue

            question_match = question_pattern.match(line)
            if question_match:
                if current_question and current_answer_lines:
                    pairs.append(
                        {
                            "question": current_question.strip(),
                            "answer": " ".join(part for part in current_answer_lines if part).strip(),
                        }
                    )
                current_question = question_match.group(1).strip()
                current_answer_lines = []
                mode = "question"
                continue

            answer_match = answer_pattern.match(line)
            if answer_match:
                if not current_question:
                    continue
                current_answer_lines = [answer_match.group(1).strip()]
                mode = "answer"
                continue

            if mode == "question" and current_question:
                current_question = f"{current_question} {line}".strip()
            elif mode == "answer" and current_question:
                current_answer_lines.append(line)

        if current_question and current_answer_lines:
            pairs.append(
                {
                    "question": current_question.strip(),
                    "answer": " ".join(part for part in current_answer_lines if part).strip(),
                }
            )

        if not pairs:
            raise ValueError("Provide QA-style text with clear Q:/A: pairs.")
        return pairs

    def _sync_remaining_seconds(self, session: Any) -> int:
        if session["status"] != "in_progress":
            return session["remaining_seconds"]
        remaining_seconds = max(
            0,
            session["duration_minutes"] * 60 - seconds_since(session["started_at"], utc_now()),
        )
        if remaining_seconds != session["remaining_seconds"]:
            self.database.update_session(session["id"], remaining_seconds=remaining_seconds)
        return remaining_seconds
