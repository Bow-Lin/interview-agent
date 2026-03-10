from unittest import IsolatedAsyncioTestCase

import httpx

from app.main import create_app


class HistoryApiTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        transport = httpx.ASGITransport(app=create_app(testing=True))
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_history_lists_completed_sessions(self) -> None:
        created = await self.client.post(
            "/sessions",
            json={
                "role": "backend_engineer",
                "level": "junior",
                "duration_minutes": 10,
                "allow_followup": False,
            },
        )
        session_id = created.json()["session_id"]

        await self.client.post(
            f"/sessions/{session_id}/answer",
            json={"answer": "RAG combines retrieval with generation."},
        )
        await self.client.post(f"/sessions/{session_id}/finish")

        history = await self.client.get("/history")

        self.assertEqual(history.status_code, 200)
        sessions = history.json()["sessions"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], session_id)
        self.assertEqual(sessions[0]["status"], "completed")
