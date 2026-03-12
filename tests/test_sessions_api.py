import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx

from app.main import create_app
from app.llm import EvaluationResult


class StubLLMClient:
    @staticmethod
    def _matches(answer: str, point: str) -> bool:
        answer_tokens = set(answer.lower().replace(".", " ").split())
        point_tokens = [token for token in point.lower().split() if token]
        hit_count = sum(1 for token in point_tokens if token in answer_tokens)
        return hit_count >= max(1, len(point_tokens) // 2)

    async def evaluate_answer(
        self,
        *,
        settings,
        question_text: str,
        answer: str,
        expected_points,
        followup_count: int,
        allow_followup: bool,
    ) -> EvaluationResult:
        strengths = [point for point in expected_points if self._matches(answer, point)]
        missing_points = [point for point in expected_points if not self._matches(answer, point)]
        should_followup = allow_followup and bool(missing_points) and followup_count < 2
        return EvaluationResult(
            quality="good" if not missing_points else "partial",
            score=100 if not missing_points else 70,
            missing_points=missing_points,
            strengths=strengths,
            should_followup=should_followup,
            followup_focus=missing_points[0] if missing_points else "",
        )

    async def generate_followup(self, *, settings, question_text: str, missing_points):
        return f"Follow up on {missing_points[0]}"

    async def generate_report(self, *, settings, role: str, question_summaries):
        return {
            "total_score": 80,
            "knowledge_score": 82,
            "communication_score": 78,
            "system_design_score": 80,
            "strengths": ["clear structure"],
            "weaknesses": ["needs more examples"],
            "suggestions": ["review production incidents"],
            "summary": f"{role} report",
        }


class StubSpeechTranscriber:
    def __init__(self) -> None:
        self.calls = []

    def transcribe(self, *, audio_path, model_name: str, language_hint=None) -> str:
        self.calls.append(
            {
                "audio_path": str(audio_path),
                "model_name": model_name,
                "language_hint": language_hint,
            }
        )
        return "transcribed answer"


class SessionApiTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.speech_transcriber = StubSpeechTranscriber()
        transport = httpx.ASGITransport(
            app=create_app(
                testing=True,
                llm_client=StubLLMClient(),
                speech_transcriber=self.speech_transcriber,
            )
        )
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def configure_llm(self) -> None:
        response = await self.client.put(
            "/settings/llm",
            json={
                "provider": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "model": "test-model",
                "api_key": "test-key",
            },
        )
        self.assertEqual(response.status_code, 200)

    async def test_settings_return_unconfigured_state_by_default(self) -> None:
        response = await self.client.get("/settings/llm")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "configured": False,
                "provider": None,
                "base_url": None,
                "model": None,
                "api_key_set": False,
            },
        )

    async def test_speech_settings_default_to_browser(self) -> None:
        response = await self.client.get("/settings/speech")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "mode": "browser",
                "whisper_model": "small",
            },
        )

    async def test_put_speech_settings_persists_selection(self) -> None:
        response = await self.client.put(
            "/settings/speech",
            json={
                "mode": "whisper",
                "whisper_model": "small",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "mode": "whisper",
                "whisper_model": "small",
            },
        )
        loaded = await self.client.get("/settings/speech")
        self.assertEqual(loaded.json()["mode"], "whisper")
        self.assertEqual(loaded.json()["whisper_model"], "small")

    async def test_put_speech_settings_rejects_blank_whisper_model(self) -> None:
        response = await self.client.put(
            "/settings/speech",
            json={
                "mode": "whisper",
                "whisper_model": "   ",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Whisper model is required")

    async def test_transcription_requires_whisper_mode(self) -> None:
        response = await self.client.post(
            "/transcriptions",
            files={"file": ("answer.webm", b"audio-bytes", "audio/webm")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Speech mode", response.json()["detail"])

    async def test_transcription_uses_configured_whisper_model(self) -> None:
        await self.client.put(
            "/settings/speech",
            json={
                "mode": "whisper",
                "whisper_model": "small",
            },
        )

        response = await self.client.post(
            "/transcriptions",
            data={"language_hint": "en"},
            files={"file": ("answer.webm", b"audio-bytes", "audio/webm")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "transcribed answer"})
        self.assertEqual(self.speech_transcriber.calls[0]["model_name"], "small")
        self.assertEqual(self.speech_transcriber.calls[0]["language_hint"], "en")

    async def test_create_session_requires_llm_settings(self) -> None:
        response = await self.client.post(
            "/sessions",
            json={
                "question_set_id": "built_in_default",
                "role": "agent_engineer",
                "level": "mid",
                "duration_minutes": 10,
                "allow_followup": True,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("LLM settings", response.json()["detail"])

    async def test_create_session_returns_first_question(self) -> None:
        await self.configure_llm()
        response = await self.client.post(
            "/sessions",
            json={
                "question_set_id": "built_in_default",
                "role": "agent_engineer",
                "level": "mid",
                "duration_minutes": 10,
                "allow_followup": True,
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "in_progress")
        self.assertEqual(body["question_index"], 0)
        self.assertEqual(body["question_limit"], 3)
        self.assertIn("question_text", body["current_prompt"])

    async def test_session_status_reports_elapsed_remaining_seconds(self) -> None:
        await self.configure_llm()
        with patch(
            "app.interview_engine.utc_now",
            side_effect=[
                "2026-03-10T00:00:00+00:00",
                "2026-03-10T00:00:45+00:00",
            ],
        ):
            created = await self.client.post(
                "/sessions",
                json={
                    "question_set_id": "built_in_default",
                    "role": "agent_engineer",
                    "level": "mid",
                    "duration_minutes": 10,
                    "allow_followup": True,
                },
            )
            session_id = created.json()["session_id"]
            status = await self.client.get(f"/sessions/{session_id}")

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["remaining_seconds"], 555)

    async def test_answer_with_missing_points_generates_followup_until_limit(self) -> None:
        await self.configure_llm()
        with patch(
            "app.interview_engine.utc_now",
            side_effect=[
                "2026-03-10T00:00:00+00:00",
                "2026-03-10T00:00:30+00:00",
                "2026-03-10T00:00:30+00:00",
                "2026-03-10T00:01:00+00:00",
                "2026-03-10T00:01:00+00:00",
                "2026-03-10T00:01:30+00:00",
                "2026-03-10T00:01:30+00:00",
            ],
        ):
            created = await self.client.post(
                "/sessions",
                json={
                    "question_set_id": "built_in_default",
                    "role": "agent_engineer",
                    "level": "mid",
                    "duration_minutes": 10,
                    "allow_followup": True,
                },
            )
            session_id = created.json()["session_id"]

            first = await self.client.post(
                f"/sessions/{session_id}/answer",
                json={"answer": "Agent can use tools."},
            )
            second = await self.client.post(
                f"/sessions/{session_id}/answer",
                json={"answer": "It also reasons about what to do next."},
            )

            third = await self.client.post(
                f"/sessions/{session_id}/answer",
                json={"answer": "That is all I know."},
            )
        self.assertEqual(first.status_code, 200)
        first_body = first.json()
        self.assertEqual(first_body["event"], "followup")
        self.assertEqual(first_body["followup_count"], 1)
        self.assertEqual(first_body["remaining_seconds"], 570)
        self.assertIn("autonomous", first_body["evaluation"]["missing_points"])

        self.assertEqual(second.status_code, 200)
        second_body = second.json()
        self.assertEqual(second_body["event"], "followup")
        self.assertEqual(second_body["followup_count"], 2)

        self.assertEqual(third.status_code, 200)
        third_body = third.json()
        self.assertEqual(third_body["event"], "next_question")
        self.assertEqual(third_body["question_index"], 1)

    async def test_answer_after_time_limit_finishes_session(self) -> None:
        await self.configure_llm()
        with patch(
            "app.interview_engine.utc_now",
            side_effect=[
                "2026-03-10T00:00:00+00:00",
                "2026-03-10T00:10:05+00:00",
                "2026-03-10T00:10:05+00:00",
                "2026-03-10T00:10:05+00:00",
                "2026-03-10T00:10:05+00:00",
            ],
        ):
            created = await self.client.post(
                "/sessions",
                json={
                    "question_set_id": "built_in_default",
                    "role": "agent_engineer",
                    "level": "mid",
                    "duration_minutes": 10,
                    "allow_followup": True,
                },
            )
            session_id = created.json()["session_id"]

            answered = await self.client.post(
                f"/sessions/{session_id}/answer",
                json={"answer": "An agent is autonomous and can use tools dynamically."},
            )

        self.assertEqual(answered.status_code, 200)
        self.assertEqual(answered.json()["event"], "finished")
        self.assertEqual(answered.json()["remaining_seconds"], 0)

    async def test_finishing_session_returns_structured_report(self) -> None:
        await self.configure_llm()
        created = await self.client.post(
            "/sessions",
            json={
                "question_set_id": "built_in_default",
                "role": "agent_engineer",
                "level": "mid",
                "duration_minutes": 10,
                "allow_followup": True,
            },
        )
        session_id = created.json()["session_id"]

        await self.client.post(
            f"/sessions/{session_id}/answer",
            json={
                "answer": "An agent makes autonomous decisions, chooses tools dynamically, and loops through reasoning."
            },
        )

        finished = await self.client.post(f"/sessions/{session_id}/finish")

        self.assertEqual(finished.status_code, 200)
        report = finished.json()
        self.assertEqual(report["session_id"], session_id)
        self.assertIn("total_score", report)
        self.assertTrue(report["question_summaries"])
        self.assertIn("strengths", report)

    async def test_followup_evaluation_is_cumulative_across_answers(self) -> None:
        await self.configure_llm()
        created = await self.client.post(
            "/sessions",
            json={
                "question_set_id": "built_in_default",
                "role": "agent_engineer",
                "level": "mid",
                "duration_minutes": 10,
                "allow_followup": True,
            },
        )
        session_id = created.json()["session_id"]

        first = await self.client.post(
            f"/sessions/{session_id}/answer",
            json={"answer": "An agent is autonomous."},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["event"], "followup")

        second = await self.client.post(
            f"/sessions/{session_id}/answer",
            json={"answer": "It can use tools dynamically."},
        )
        self.assertEqual(second.status_code, 200)
        evaluation = second.json()["evaluation"]
        self.assertIn("autonomous", evaluation["strengths"])
        self.assertIn("dynamic tool use", evaluation["strengths"])
        self.assertEqual(evaluation["missing_points"], ["looped reasoning"])

    async def test_unsupported_level_is_rejected(self) -> None:
        await self.configure_llm()
        response = await self.client.post(
            "/sessions",
            json={
                "question_set_id": "built_in_default",
                "role": "backend_engineer",
                "level": "senior",
                "duration_minutes": 10,
                "allow_followup": True,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Not enough questions", response.json()["detail"])

    async def test_invalid_duration_is_rejected_by_validation(self) -> None:
        await self.configure_llm()
        response = await self.client.post(
            "/sessions",
            json={
                "question_set_id": "built_in_default",
                "role": "agent_engineer",
                "level": "mid",
                "duration_minutes": 15,
                "allow_followup": True,
            },
        )

        self.assertEqual(response.status_code, 422)

    async def test_put_settings_persists_provider_without_returning_api_key(self) -> None:
        await self.configure_llm()

        response = await self.client.get("/settings/llm")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["configured"], True)
        self.assertEqual(response.json()["provider"], "openai_compatible")
        self.assertEqual(response.json()["base_url"], "https://api.openai.com/v1")
        self.assertEqual(response.json()["model"], "test-model")
        self.assertEqual(response.json()["api_key_set"], True)

    async def test_question_sets_list_built_in_bank(self) -> None:
        response = await self.client.get("/question-sets")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["question_sets"],
            [
                {
                    "id": "built_in_default",
                    "name": "Built-in Question Bank",
                    "source_type": "system",
                    "status": "ready",
                    "question_count": 12,
                }
            ],
        )

    async def test_import_question_set_creates_new_bank(self) -> None:
        payload = {
            "name": "Custom Agent Pack",
            "questions": [
                {
                    "id": "custom_agent_mid_001",
                    "role": "agent_engineer",
                    "level": "mid",
                    "question_text": "How do agents recover from tool failures?",
                    "expected_points": ["retry strategy", "fallback handling", "observability"],
                    "tags": ["agents", "reliability"],
                    "reference_answer": "Agents need retries, fallback behavior, and strong logging.",
                },
                {
                    "id": "custom_agent_mid_002",
                    "role": "agent_engineer",
                    "level": "mid",
                    "question_text": "What makes tool schemas important?",
                    "expected_points": ["validation", "clear contracts", "error prevention"],
                    "tags": ["tools"],
                    "reference_answer": "Schemas validate tool inputs and clarify contracts.",
                },
                {
                    "id": "custom_agent_mid_003",
                    "role": "agent_engineer",
                    "level": "mid",
                    "question_text": "When should an agent ask for human approval?",
                    "expected_points": ["high risk action", "uncertainty", "policy boundaries"],
                    "tags": ["safety"],
                    "reference_answer": "Agents should pause for risky or uncertain actions.",
                },
            ],
        }

        response = await self.client.post(
            "/question-sets/import",
            files={"file": ("custom-agent-pack.json", json.dumps(payload).encode("utf-8"), "application/json")},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["name"], "Custom Agent Pack")
        self.assertEqual(body["question_count"], 3)
        self.assertNotEqual(body["id"], "built_in_default")

        listed = await self.client.get("/question-sets")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["question_sets"]), 2)
        self.assertEqual(listed.json()["question_sets"][1]["name"], "Custom Agent Pack")

    async def test_import_question_set_rejects_invalid_role(self) -> None:
        payload = {
            "name": "Broken Pack",
            "questions": [
                {
                    "id": "broken_001",
                    "role": "ml_engineer",
                    "level": "mid",
                    "question_text": "What is model drift?",
                    "expected_points": ["distribution shift"],
                    "tags": ["ml"],
                    "reference_answer": "Drift is a change in production data.",
                }
            ],
        }

        response = await self.client.post(
            "/question-sets/import",
            files={"file": ("broken-pack.json", json.dumps(payload).encode("utf-8"), "application/json")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid role", response.json()["detail"])

    async def test_create_session_uses_selected_question_set(self) -> None:
        await self.configure_llm()
        import_payload = {
            "name": "Focused Backend Pack",
            "questions": [
                {
                    "id": "custom_backend_junior_001",
                    "role": "backend_engineer",
                    "level": "junior",
                    "question_text": "How do you roll out schema changes safely?",
                    "expected_points": ["backward compatibility", "migration steps", "monitoring"],
                    "tags": ["database"],
                    "reference_answer": "Roll out additive changes first and monitor each step.",
                },
                {
                    "id": "custom_backend_junior_002",
                    "role": "backend_engineer",
                    "level": "junior",
                    "question_text": "What should an API timeout protect against?",
                    "expected_points": ["hung dependencies", "resource exhaustion", "user latency"],
                    "tags": ["http"],
                    "reference_answer": "Timeouts bound latency and resource usage.",
                },
                {
                    "id": "custom_backend_junior_003",
                    "role": "backend_engineer",
                    "level": "junior",
                    "question_text": "Why log request identifiers?",
                    "expected_points": ["traceability", "debugging", "correlation"],
                    "tags": ["observability"],
                    "reference_answer": "Request ids correlate logs across services.",
                },
            ],
        }
        imported = await self.client.post(
            "/question-sets/import",
            files={
                "file": (
                    "focused-backend-pack.json",
                    json.dumps(import_payload).encode("utf-8"),
                    "application/json",
                )
            },
        )
        question_set_id = imported.json()["id"]

        response = await self.client.post(
            "/sessions",
            json={
                "question_set_id": question_set_id,
                "role": "backend_engineer",
                "level": "junior",
                "duration_minutes": 10,
                "allow_followup": True,
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["current_prompt"]["question_text"],
            "How do you roll out schema changes safely?",
        )
