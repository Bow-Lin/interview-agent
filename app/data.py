import json
from typing import Iterable


BUILT_IN_QUESTION_SET_ID = "built_in_default"
BUILT_IN_QUESTION_SET_NAME = "Built-in Question Bank"
VALID_ROLES = {
    "agent_engineer",
    "backend_engineer",
    "frontend_engineer",
    "algorithm_engineer",
}
VALID_LEVELS = {"junior", "mid", "senior"}


QUESTION_BANK = [
    {
        "id": "agent_mid_001",
        "role": "agent_engineer",
        "level": "mid",
        "question_text": "What is the difference between an AI agent and a workflow?",
        "expected_points": [
            "autonomous",
            "dynamic tool use",
            "looped reasoning",
        ],
        "tags": ["agents", "workflow"],
        "reference_answer": "An agent decides what to do next based on state, can choose tools dynamically, and may iterate through reasoning steps.",
    },
    {
        "id": "agent_mid_002",
        "role": "agent_engineer",
        "level": "mid",
        "question_text": "Describe the basic architecture of a retrieval augmented generation system.",
        "expected_points": [
            "retrieval step",
            "knowledge grounding",
            "generation with retrieved context",
        ],
        "tags": ["rag"],
        "reference_answer": "RAG retrieves relevant context first, grounds the prompt with that context, and then generates an answer conditioned on it.",
    },
    {
        "id": "agent_mid_003",
        "role": "agent_engineer",
        "level": "mid",
        "question_text": "How do you keep an agent from taking unbounded actions?",
        "expected_points": [
            "step limits",
            "guardrails",
            "human review or stopping conditions",
        ],
        "tags": ["safety"],
        "reference_answer": "Use hard step limits, guardrails around tools, and clear stop conditions or human review for risky actions.",
    },
    {
        "id": "backend_junior_001",
        "role": "backend_engineer",
        "level": "junior",
        "question_text": "What problem does caching solve in a backend system?",
        "expected_points": [
            "reduced latency",
            "reduced load on downstream services",
            "tradeoff with staleness",
        ],
        "tags": ["caching"],
        "reference_answer": "Caching reduces repeated work, lowers latency, and can reduce database load, but introduces staleness tradeoffs.",
    },
    {
        "id": "backend_junior_002",
        "role": "backend_engineer",
        "level": "junior",
        "question_text": "What is the difference between a process and a thread?",
        "expected_points": [
            "memory isolation",
            "shared memory between threads",
            "scheduling unit",
        ],
        "tags": ["concurrency"],
        "reference_answer": "Processes have isolated memory, threads share memory within a process, and both are scheduled independently by the OS.",
    },
    {
        "id": "backend_junior_003",
        "role": "backend_engineer",
        "level": "junior",
        "question_text": "Why do APIs use status codes?",
        "expected_points": [
            "communicate result",
            "client error handling",
            "server error distinction",
        ],
        "tags": ["http"],
        "reference_answer": "Status codes let clients understand whether a request succeeded and how to handle client or server-side failures.",
    },
    {
        "id": "frontend_mid_001",
        "role": "frontend_engineer",
        "level": "mid",
        "question_text": "Why would you split a frontend into reusable components?",
        "expected_points": [
            "reuse",
            "clear ownership",
            "easier maintenance",
        ],
        "tags": ["components"],
        "reference_answer": "Reusable components improve consistency, clarify ownership boundaries, and reduce maintenance costs.",
    },
    {
        "id": "frontend_mid_002",
        "role": "frontend_engineer",
        "level": "mid",
        "question_text": "What causes a slow first render in a web application?",
        "expected_points": [
            "large bundles",
            "blocking network requests",
            "expensive rendering work",
        ],
        "tags": ["performance"],
        "reference_answer": "Slow first render usually comes from oversized bundles, blocking requests, or too much work during initial rendering.",
    },
    {
        "id": "frontend_mid_003",
        "role": "frontend_engineer",
        "level": "mid",
        "question_text": "How do you decide whether state should live locally or globally?",
        "expected_points": [
            "scope of sharing",
            "update frequency",
            "avoid unnecessary coupling",
        ],
        "tags": ["state-management"],
        "reference_answer": "State should stay local unless multiple areas need it; consider update frequency and avoid unnecessary coupling.",
    },
    {
        "id": "algorithm_mid_001",
        "role": "algorithm_engineer",
        "level": "mid",
        "question_text": "When would you prefer dynamic programming over brute force search?",
        "expected_points": [
            "overlapping subproblems",
            "optimal substructure",
            "repeated computation avoidance",
        ],
        "tags": ["dynamic-programming"],
        "reference_answer": "Dynamic programming works well when subproblems overlap and the problem has optimal substructure, avoiding repeated work.",
    },
    {
        "id": "algorithm_mid_002",
        "role": "algorithm_engineer",
        "level": "mid",
        "question_text": "What tradeoff does a hash table make compared with a balanced tree?",
        "expected_points": [
            "average lookup speed",
            "ordering support",
            "worst case behavior",
        ],
        "tags": ["data-structures"],
        "reference_answer": "Hash tables optimize average lookup speed but lose ordering and may degrade in worst-case collisions compared with balanced trees.",
    },
    {
        "id": "algorithm_mid_003",
        "role": "algorithm_engineer",
        "level": "mid",
        "question_text": "How would you explain time and space complexity to a candidate?",
        "expected_points": [
            "growth with input size",
            "runtime resource cost",
            "memory tradeoffs",
        ],
        "tags": ["complexity"],
        "reference_answer": "Time and space complexity describe how runtime and memory grow with input size and what tradeoffs an algorithm makes.",
    },
]


def dump_json(value: Iterable[str]) -> str:
    return json.dumps(list(value), ensure_ascii=True)
