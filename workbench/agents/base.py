import time
from abc import ABC, abstractmethod

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import config
from workbench.agents.tools import Tools
from workbench.llm.client import LLMClient
from workbench.schemas import AgentOutput


class BaseAgent(ABC):
    role: str = "base"
    system_prompt: str = "You are a helpful agent."
    output_schema: type[BaseModel] = AgentOutput

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    @abstractmethod
    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        """Turn current project state + task into the user prompt."""

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        """Canned output used when MOCK_LLM=1. Override to give realistic dev/test data."""
        return {"summary": f"[mock] {self.role} ran"}

    @abstractmethod
    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        """Persist the validated output through the tool API."""

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        task = task or {}
        tools = Tools(db, project_id, self.role)
        tools.log("agent_started", task.get("name", ""))
        usage: dict = {}
        started = time.perf_counter()
        out = self.llm.complete_json(
            self.system_prompt,
            self.build_prompt(db, project_id, task),
            self.output_schema,
            mock=lambda: self.mock_output(db, project_id, task),
            usage=usage,
        )
        self.apply(tools, out, task)
        tools.log("agent_finished", getattr(out, "summary", ""),
                  **_usage_payload(self, usage, started, task))
        return out


def _usage_payload(agent: BaseAgent, usage: dict, started: float, task: dict) -> dict:
    """Payload of `agent_finished`: LLM usage of this run, duration, model and mode."""
    keys = ("calls", "input_tokens", "output_tokens", "cache_hits", "invalid_outputs")
    payload = {k: int(usage.get(k, 0)) for k in keys}
    payload.update(duration_ms=int((time.perf_counter() - started) * 1000), model=config.MODEL,
                   llm_mode="mock" if agent.llm.mock else "live", story_id=task.get("story_id"))
    return payload


class StubAgent(BaseAgent):
    """Placeholder so the orchestrator can run end to end before real agents exist."""

    def __init__(self, role: str, llm: LLMClient | None = None):
        super().__init__(llm or LLMClient(mock=True))
        self.role = role

    def build_prompt(self, db, project_id, task):
        return ""

    def apply(self, tools, out, task):
        pass
