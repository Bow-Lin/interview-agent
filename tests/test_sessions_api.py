from unittest import IsolatedAsyncioTestCase

import httpx

from app.main import create_app


class SessionApiTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        transport = httpx.ASGITransport(app=create_app(testing=True))
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_create_session_returns_first_question(self) -> None:
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

    async def test_answer_with_missing_points_generates_followup_until_limit(self) -> None:
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
        self.assertEqual(first.status_code, 200)
        first_body = first.json()
        self.assertEqual(first_body["event"], "followup")
        self.assertEqual(first_body["followup_count"], 1)
        self.assertIn("autonomous", first_body["evaluation"]["missing_points"])

        second = await self.client.post(
            f"/sessions/{session_id}/answer",
            json={"answer": "It also reasons about what to do next."},
        )
        self.assertEqual(second.status_code, 200)
        second_body = second.json()
        self.assertEqual(second_body["event"], "followup")
        self.assertEqual(second_body["followup_count"], 2)

        third = await self.client.post(
            f"/sessions/{session_id}/answer",
            json={"answer": "That is all I know."},
        )
        self.assertEqual(third.status_code, 200)
        third_body = third.json()
        self.assertEqual(third_body["event"], "next_question")
        self.assertEqual(third_body["question_index"], 1)

    async def test_finishing_session_returns_structured_report(self) -> None:
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
