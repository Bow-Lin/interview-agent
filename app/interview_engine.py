import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.database import Database
from app.workflow import InterviewWorkflow


QUESTION_LIMITS = {
    10: 3,
    20: 5,
    30: 7,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class MockLLMClient:
    def evaluate_answer(
        self, answer: str, expected_points: List[str], followup_count: int, allow_followup: bool
    ) -> EvaluationResult:
        hits = keyword_hits(answer, expected_points)
        strengths = [point for point, present in hits.items() if present]
        missing_points = [point for point, present in hits.items() if not present]
        ratio = len(strengths) / max(1, len(expected_points))
        if ratio >= 1:
            quality = "good"
        elif ratio >= 0.5:
            quality = "partial"
        elif ratio > 0:
            quality = "weak"
        else:
            quality = "off_topic"
        score = int(50 + ratio * 50)
        should_followup = allow_followup and bool(missing_points) and followup_count < 2
        focus = missing_points[0] if missing_points else ""
        return EvaluationResult(
            quality=quality,
            score=score,
            missing_points=missing_points,
            strengths=strengths,
            should_followup=should_followup,
            followup_focus=focus,
        )

    def generate_followup(self, question_text: str, missing_points: List[str]) -> str:
        focus = missing_points[0] if missing_points else "the missing detail"
        return (
            f"You touched on the topic, but please go deeper on {focus}. "
            f"How does that relate back to: {question_text}"
        )

    def generate_report(self, role: str, question_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        if question_summaries:
            avg_score = sum(item["score"] for item in question_summaries) // len(question_summaries)
        else:
            avg_score = 0
        strengths: List[str] = []
        weaknesses: List[str] = []
        for item in question_summaries:
            strengths.extend(item["strengths"][:1])
            weaknesses.extend(item["missing_points"][:1])
        strengths = strengths[:3] or ["Kept the interview moving with direct answers."]
        weaknesses = weaknesses[:3] or ["Needs more depth on edge cases."]
        suggestions = [
            f"Review {topic}" for topic in weaknesses[:2]
        ] or ["Practice structured answer framing."]
        return {
            "total_score": avg_score,
            "knowledge_score": min(100, avg_score + 4),
            "communication_score": max(55, avg_score - 4),
            "system_design_score": avg_score,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "suggestions": suggestions,
            "summary": f"This {role} interview showed the strongest coverage on {strengths[0].lower()}."
        }


class InterviewEngine:
    def __init__(self, database: Database, llm_client: Optional[MockLLMClient] = None) -> None:
        self.database = database
        self.llm_client = llm_client or MockLLMClient()
        self.workflow = InterviewWorkflow()

    def create_session(
        self, role: str, level: str, duration_minutes: int, allow_followup: bool
    ) -> Dict[str, Any]:
        question_limit = QUESTION_LIMITS[duration_minutes]
        questions = self.database.get_questions(role, level, question_limit)
        if len(questions) < question_limit:
            raise ValueError(f"Not enough questions for role={role} level={level}")
        session_id = str(uuid.uuid4())
        started_at = utc_now()
        selected_question_ids = [question["id"] for question in questions]
        self.database.create_session(
            session_id=session_id,
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
        current_prompt = None
        if session["status"] == "in_progress":
            current_prompt = self._build_current_prompt(session)
        return {
            "session_id": session_id,
            "status": session["status"],
            "role": session["role"],
            "level": session["level"],
            "duration_minutes": session["duration_minutes"],
            "allow_followup": bool(session["allow_followup"]),
            "question_index": session["current_question_index"],
            "question_limit": session["question_limit"],
            "remaining_seconds": session["remaining_seconds"],
            "current_prompt": current_prompt,
        }

    def answer(self, session_id: str, answer: str) -> Dict[str, Any]:
        session = self.database.get_session(session_id)
        if session["status"] != "in_progress":
            raise ValueError("Session is not active")
        selected_question_ids = json.loads(session["selected_question_ids"])
        question_id = selected_question_ids[session["current_question_index"]]
        question = self.database.get_question(question_id)
        question_record = self.database.get_question_record(session_id, question_id)
        followup_count = self.database.count_followups(question_record["id"])
        prior_answers = [
            turn["content"]
            for turn in self.database.list_turns(question_record["id"])
            if turn["turn_type"] == "user_answer"
        ]
        cumulative_answer = " ".join(prior_answers + [answer])

        evaluation = self.llm_client.evaluate_answer(
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

        remaining_seconds = max(0, session["remaining_seconds"] - 90)
        self.database.update_session(session_id, remaining_seconds=remaining_seconds)

        route = self.workflow.route_after_evaluation(
            {
                "should_followup": evaluation.should_followup,
                "remaining_seconds": remaining_seconds,
                "next_index": session["current_question_index"] + 1,
                "question_limit": session["question_limit"],
            }
        )

        if route == "generate_followup":
            followup_text = self.llm_client.generate_followup(
                question["question_text"], evaluation.missing_points
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
            report = self.finish_session(session_id)
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

    def finish_session(self, session_id: str) -> Dict[str, Any]:
        session = self.database.get_session(session_id)
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
        report = self.llm_client.generate_report(session["role"], question_summaries)
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
        self.database.update_session(session_id, status="completed", ended_at=utc_now())
        return {
            "session_id": session_id,
            **report,
            "question_summaries": question_summaries,
        }

    def get_report(self, session_id: str) -> Dict[str, Any]:
        return self.database.get_report(session_id)

    def list_history(self) -> List[Dict[str, Any]]:
        return self.database.list_history()

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
