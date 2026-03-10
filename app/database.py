import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from app.data import QUESTION_BANK, dump_json


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.initialize()

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def initialize(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS question_bank (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    level TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    expected_points TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    reference_answer TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS interview_sessions (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    level TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    allow_followup INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    question_limit INTEGER NOT NULL,
                    current_question_index INTEGER NOT NULL,
                    remaining_seconds INTEGER NOT NULL,
                    selected_question_ids TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS question_records (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    asked_order INTEGER NOT NULL,
                    final_score INTEGER DEFAULT 0,
                    answer_quality TEXT DEFAULT 'unanswered',
                    strengths TEXT DEFAULT '[]',
                    missing_points TEXT DEFAULT '[]',
                    summary TEXT DEFAULT '',
                    UNIQUE(session_id, question_id)
                );
                CREATE TABLE IF NOT EXISTS turn_records (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    question_record_id TEXT NOT NULL,
                    turn_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    evaluation_snapshot TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS interview_reports (
                    session_id TEXT PRIMARY KEY,
                    total_score INTEGER NOT NULL,
                    knowledge_score INTEGER NOT NULL,
                    communication_score INTEGER NOT NULL,
                    system_design_score INTEGER NOT NULL,
                    strengths TEXT NOT NULL,
                    weaknesses TEXT NOT NULL,
                    suggestions TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    question_summaries TEXT NOT NULL
                );
                """
            )
            conn.executemany(
                """
                INSERT OR IGNORE INTO question_bank (
                    id, role, level, question_text, expected_points, tags, reference_answer
                ) VALUES (:id, :role, :level, :question_text, :expected_points, :tags, :reference_answer)
                """,
                [
                    {
                        **row,
                        "expected_points": dump_json(row["expected_points"]),
                        "tags": dump_json(row["tags"]),
                    }
                    for row in QUESTION_BANK
                ],
            )

    def create_session(
        self,
        session_id: str,
        role: str,
        level: str,
        duration_minutes: int,
        allow_followup: bool,
        started_at: str,
        question_limit: int,
        selected_question_ids: List[str],
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO interview_sessions (
                    id, role, level, duration_minutes, allow_followup, status, started_at,
                    question_limit, current_question_index, remaining_seconds, selected_question_ids
                ) VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?, 0, ?, ?)
                """,
                (
                    session_id,
                    role,
                    level,
                    duration_minutes,
                    1 if allow_followup else 0,
                    started_at,
                    question_limit,
                    duration_minutes * 60,
                    json.dumps(selected_question_ids),
                ),
            )

    def get_questions(self, role: str, level: str, limit: int) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM question_bank
            WHERE role = ? AND level = ?
            ORDER BY id
            LIMIT ?
            """,
            (role, level, limit),
        ).fetchall()
        return [self._question_row_to_dict(row) for row in rows]

    def get_question(self, question_id: str) -> Dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM question_bank WHERE id = ?",
            (question_id,),
        ).fetchone()
        if row is None:
            raise KeyError(question_id)
        return self._question_row_to_dict(row)

    def get_session(self, session_id: str) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM interview_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return row

    def update_session(
        self,
        session_id: str,
        *,
        status: Optional[str] = None,
        ended_at: Optional[str] = None,
        current_question_index: Optional[int] = None,
        remaining_seconds: Optional[int] = None,
    ) -> None:
        fields: List[str] = []
        params: List[Any] = []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if ended_at is not None:
            fields.append("ended_at = ?")
            params.append(ended_at)
        if current_question_index is not None:
            fields.append("current_question_index = ?")
            params.append(current_question_index)
        if remaining_seconds is not None:
            fields.append("remaining_seconds = ?")
            params.append(remaining_seconds)
        if not fields:
            return
        params.append(session_id)
        with self.transaction() as conn:
            conn.execute(
                "UPDATE interview_sessions SET " + ", ".join(fields) + " WHERE id = ?",
                params,
            )

    def ensure_question_record(
        self, session_id: str, question_id: str, question_text: str, asked_order: int
    ) -> str:
        row = self._conn.execute(
            """
            SELECT id FROM question_records
            WHERE session_id = ? AND question_id = ?
            """,
            (session_id, question_id),
        ).fetchone()
        if row is not None:
            return row["id"]
        record_id = str(uuid.uuid4())
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO question_records (
                    id, session_id, question_id, question_text, asked_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (record_id, session_id, question_id, question_text, asked_order),
            )
        return record_id

    def get_question_record(self, session_id: str, question_id: str) -> sqlite3.Row:
        row = self._conn.execute(
            """
            SELECT * FROM question_records
            WHERE session_id = ? AND question_id = ?
            """,
            (session_id, question_id),
        ).fetchone()
        if row is None:
            raise KeyError((session_id, question_id))
        return row

    def update_question_record(
        self,
        record_id: str,
        *,
        final_score: int,
        answer_quality: str,
        strengths: Iterable[str],
        missing_points: Iterable[str],
        summary: str,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE question_records
                SET final_score = ?, answer_quality = ?, strengths = ?, missing_points = ?, summary = ?
                WHERE id = ?
                """,
                (
                    final_score,
                    answer_quality,
                    json.dumps(list(strengths)),
                    json.dumps(list(missing_points)),
                    summary,
                    record_id,
                ),
            )

    def add_turn(
        self,
        session_id: str,
        question_record_id: str,
        turn_type: str,
        content: str,
        evaluation_snapshot: Optional[Dict[str, Any]] = None,
    ) -> int:
        next_sequence = (
            self._conn.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) + 1
                FROM turn_records
                WHERE question_record_id = ?
                """,
                (question_record_id,),
            ).fetchone()[0]
        )
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO turn_records (
                    id, session_id, question_record_id, turn_type, content, sequence, evaluation_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    session_id,
                    question_record_id,
                    turn_type,
                    content,
                    next_sequence,
                    json.dumps(evaluation_snapshot or {}),
                ),
            )
        return next_sequence

    def count_followups(self, question_record_id: str) -> int:
        return self._conn.execute(
            """
            SELECT COUNT(*) FROM turn_records
            WHERE question_record_id = ? AND turn_type = 'followup'
            """,
            (question_record_id,),
        ).fetchone()[0]

    def list_turns(self, question_record_id: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM turn_records
            WHERE question_record_id = ?
            ORDER BY sequence
            """,
            (question_record_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_question_records(self, session_id: str) -> List[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT * FROM question_records
            WHERE session_id = ?
            ORDER BY asked_order
            """,
            (session_id,),
        ).fetchall()

    def save_report(
        self,
        session_id: str,
        total_score: int,
        knowledge_score: int,
        communication_score: int,
        system_design_score: int,
        strengths: Iterable[str],
        weaknesses: Iterable[str],
        suggestions: Iterable[str],
        summary: str,
        question_summaries: Iterable[Dict[str, Any]],
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO interview_reports (
                    session_id, total_score, knowledge_score, communication_score,
                    system_design_score, strengths, weaknesses, suggestions, summary, question_summaries
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    total_score,
                    knowledge_score,
                    communication_score,
                    system_design_score,
                    json.dumps(list(strengths)),
                    json.dumps(list(weaknesses)),
                    json.dumps(list(suggestions)),
                    summary,
                    json.dumps(list(question_summaries)),
                ),
            )

    def get_report(self, session_id: str) -> Dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM interview_reports WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return {
            "session_id": row["session_id"],
            "total_score": row["total_score"],
            "knowledge_score": row["knowledge_score"],
            "communication_score": row["communication_score"],
            "system_design_score": row["system_design_score"],
            "strengths": json.loads(row["strengths"]),
            "weaknesses": json.loads(row["weaknesses"]),
            "suggestions": json.loads(row["suggestions"]),
            "summary": row["summary"],
            "question_summaries": json.loads(row["question_summaries"]),
        }

    def list_history(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT s.id, s.role, s.level, s.status, s.duration_minutes, r.total_score, s.started_at, s.ended_at
            FROM interview_sessions s
            LEFT JOIN interview_reports r ON r.session_id = s.id
            WHERE s.status = 'completed'
            ORDER BY s.started_at DESC
            """
        ).fetchall()
        return [
            {
                "session_id": row["id"],
                "role": row["role"],
                "level": row["level"],
                "status": row["status"],
                "duration_minutes": row["duration_minutes"],
                "total_score": row["total_score"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _question_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "role": row["role"],
            "level": row["level"],
            "question_text": row["question_text"],
            "expected_points": json.loads(row["expected_points"]),
            "tags": json.loads(row["tags"]),
            "reference_answer": row["reference_answer"],
        }
