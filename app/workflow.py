from typing import Any, Dict


class InterviewWorkflow:
    """Graph-style decision router for interview turns.

    The workflow keeps the public node boundaries explicit even when LangGraph is
    not available in the local Python runtime. If LangGraph is installed later,
    this class is the seam where the same nodes can be wired into a real graph.
    """

    def __init__(self) -> None:
        try:
            from langgraph.graph import StateGraph  # type: ignore
        except ImportError:
            self.backend = "local"
        else:
            self.backend = "langgraph"
            self._state_graph_cls = StateGraph

    def route_after_evaluation(self, state: Dict[str, Any]) -> str:
        if state["should_followup"] and state["remaining_seconds"] > 0:
            return "generate_followup"
        if state["remaining_seconds"] <= 0 or state["next_index"] >= state["question_limit"]:
            return "finalize_report"
        return "advance_question"

