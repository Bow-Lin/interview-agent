# API

## Base Assumptions

- transport: local HTTP
- content type: `application/json`
- backend default URL: `http://127.0.0.1:8000`

## Endpoints

### `GET /settings/llm`

Return the currently stored LLM configuration without exposing the plaintext key.

Success response:

```json
{
  "configured": true,
  "provider": "openai_compatible",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key_set": true
}
```

If no settings are stored:

```json
{
  "configured": false,
  "provider": null,
  "base_url": null,
  "model": null,
  "api_key_set": false
}
```

### `PUT /settings/llm`

Create or update the local provider configuration.

Request body:

```json
{
  "provider": "openai_compatible",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key": "sk-..."
}
```

Behavior:

- `provider` is currently fixed to `openai_compatible`
- `base_url` and `model` must be non-empty after trimming
- on first save, `api_key` is required
- on later saves, an empty `api_key` keeps the previously stored key

### `POST /sessions`

Create a new interview session.

Request body:

```json
{
  "role": "agent_engineer",
  "level": "mid",
  "duration_minutes": 10,
  "allow_followup": true
}
```

Rules:

- `duration_minutes` must be one of `10`, `20`, `30`
- the requested `role + level` must have enough seeded questions
- LLM settings must already be configured
- unsupported combinations return `400`

Success response: `201`

```json
{
  "session_id": "uuid",
  "status": "in_progress",
  "question_index": 0,
  "question_limit": 3,
  "remaining_seconds": 600,
  "current_prompt": {
    "question_id": "agent_mid_001",
    "question_text": "What is the difference between an AI agent and a workflow?",
    "prompt_type": "main_question"
  }
}
```

### `GET /sessions/{session_id}`

Return current session status and active prompt.

Success response: `200`

```json
{
  "session_id": "uuid",
  "status": "in_progress",
  "role": "agent_engineer",
  "level": "mid",
  "duration_minutes": 10,
  "allow_followup": true,
  "question_index": 0,
  "question_limit": 3,
  "remaining_seconds": 510,
  "current_prompt": {
    "question_id": "agent_mid_001",
    "question_text": "You touched on the topic, but please go deeper on autonomous.",
    "prompt_type": "followup"
  }
}
```

### `POST /sessions/{session_id}/answer`

Submit one answer for the active prompt.

Request body:

```json
{
  "answer": "An agent is autonomous and can use tools dynamically."
}
```

Possible events:

- `followup`
- `next_question`
- `finished`

Example `followup` response:

```json
{
  "event": "followup",
  "session_id": "uuid",
  "status": "in_progress",
  "question_index": 0,
  "followup_count": 1,
  "remaining_seconds": 510,
  "evaluation": {
    "quality": "partial",
    "score": 83,
    "missing_points": ["looped reasoning"],
    "strengths": ["autonomous", "dynamic tool use"],
    "should_followup": true,
    "followup_focus": "looped reasoning"
  },
  "current_prompt": {
    "question_id": "agent_mid_001",
    "question_text": "You touched on the topic, but please go deeper on looped reasoning.",
    "prompt_type": "followup"
  }
}
```

Behavioral notes:

- evaluation is cumulative across all answers for the current question
- follow-up count is capped at `2`
- each submitted answer currently reduces `remaining_seconds` by `90`

### `POST /sessions/{session_id}/finish`

Force-complete the current session and generate a report immediately.

Success response: `200`

```json
{
  "session_id": "uuid",
  "total_score": 74,
  "knowledge_score": 78,
  "communication_score": 70,
  "system_design_score": 74,
  "strengths": ["autonomous", "dynamic tool use"],
  "weaknesses": ["looped reasoning"],
  "suggestions": ["Review looped reasoning"],
  "summary": "This agent_engineer interview showed the strongest coverage on autonomous.",
  "question_summaries": []
}
```

### `GET /reports/{session_id}`

Return a previously stored report for a completed session.

### `GET /history`

Return completed sessions for the home page.

Success response:

```json
{
  "sessions": [
    {
      "session_id": "uuid",
      "role": "agent_engineer",
      "level": "mid",
      "status": "completed",
      "duration_minutes": 10,
      "total_score": 74,
      "started_at": "2026-03-10T00:00:00+00:00",
      "ended_at": "2026-03-10T00:10:00+00:00"
    }
  ]
}
```

## Error Semantics

- `400` for missing LLM settings, unavailable `role + level`, or invalid LLM configuration payload after trimming
- `400` for unsupported but syntactically valid requests such as unavailable `role + level`
- `404` for unknown sessions or reports
- `422` for schema validation failures such as unsupported duration values
