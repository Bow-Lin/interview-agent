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


class SessionApiTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        transport = httpx.ASGITransport(app=create_app(testing=True, llm_client=StubLLMClient()))
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

    async def test_create_session_requires_llm_settings(self) -> None:
        response = await self.client.post(
            "/sessions",
            json={
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
