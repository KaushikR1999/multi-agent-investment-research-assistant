from langgraph.graph import END, StateGraph

from backend.app.graph.nodes import ResearchWorkflowNodes, WorkflowDependencies
from backend.app.models.graph_state import ResearchGraphState
from backend.app.models.requests import ResearchRequest


class ResearchWorkflow:
    def __init__(self, dependencies: WorkflowDependencies | None = None) -> None:
        self.nodes = ResearchWorkflowNodes(dependencies=dependencies)
        self.graph = self._build_graph()

    def run(self, request: ResearchRequest, request_id: str) -> ResearchGraphState:
        initial_state = ResearchGraphState(request_id=request_id, request=request)
        result = self.graph.invoke(initial_state)
        return ResearchGraphState.model_validate(result)

    def _build_graph(self):
        graph = StateGraph(ResearchGraphState)
        graph.add_node("parse_query", self.nodes.parse_query)
        graph.add_node("resolve_ticker", self.nodes.resolve_ticker)
        graph.add_node("parallel_workers", self.nodes.run_parallel_workers)
        graph.add_node("risk", self.nodes.run_risk)
        graph.add_node("research_synthesizer", self.nodes.synthesize_draft)
        graph.add_node("verifier", self.nodes.verify_report)
        graph.add_node("final_response", self.nodes.final_response)

        graph.set_entry_point("parse_query")
        graph.add_edge("parse_query", "resolve_ticker")
        graph.add_conditional_edges(
            "resolve_ticker",
            self.nodes.should_continue_after_resolution,
            {
                "parallel_workers": "parallel_workers",
                "final_response": "final_response",
            },
        )
        graph.add_edge("parallel_workers", "risk")
        graph.add_edge("risk", "research_synthesizer")
        graph.add_edge("research_synthesizer", "verifier")
        graph.add_edge("verifier", "final_response")
        graph.add_edge("final_response", END)
        return graph.compile()


def build_research_workflow(dependencies: WorkflowDependencies | None = None) -> ResearchWorkflow:
    return ResearchWorkflow(dependencies=dependencies)
