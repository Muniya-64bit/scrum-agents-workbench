import re
import time
from abc import ABC, abstractmethod

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import config
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
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

    def _agreements(self, db: Session, project_id: int, task: dict) -> str:
        """The team's working agreements from the last retrospective, for every agent's prompt
        (the Product Owner runs before any retrospective exists)."""
        if self.role == "product_owner":
            return ""
        from workbench.process import effective_process  # lazy: process imports the agents' deps

        guidelines = effective_process(db, project_id, task.get("phase", "")).guidelines
        if not guidelines:
            return ""
        return ("\n\nTeam working agreements (from the last retrospective):\n"
                + "\n".join(f"- {g}" for g in guidelines))

    def llm_key(self, db: Session, project_id: int, task: dict) -> str:
        """Names this LLM call by meaning, not by prompt: role, class, phase, sprint number and
        (when the task has one) the story. Record/replay files are stored under this key, so
        editing a prompt does not invalidate a recording."""
        sprint = repo.current_sprint(db, project_id)
        number = task.get("sprint_number") or (sprint.number if sprint else 0)
        key = f"{self.role}.{type(self).__name__}.{task.get('phase') or 'none'}.s{number}"
        if task.get("story_id"):
            story = repo.get(db, m.UserStory, task["story_id"])
            if story is not None:
                key += f".{_slug(story.title)}"
        return key

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        task = task or {}
        tools = Tools(db, project_id, self.role)
        tools.log("agent_started", task.get("name", ""))
        usage: dict = {}
        started = time.perf_counter()
        prompt = self.build_prompt(db, project_id, task) + self._agreements(db, project_id, task)
        key = self.llm_key(db, project_id, task)
        try:
            out = self.llm.complete_json(
                self.system_prompt,
                prompt,
                self.output_schema,
                mock=lambda: self.mock_output(db, project_id, task),
                usage=usage,
                key=key,
                model=config.model_for(self.role),
            )
        finally:  # replay notes are logged also when the call fails
            if usage.get("replay_drift"):
                tools.log("llm_replay_drift", f"Prompt changed since recording: {key}",
                          key=key, n=usage.get("replay_n", 0))
            if usage.get("replay_fallback"):
                tools.log("llm_replay_fallback", f"No recorded response, used mock: {key}",
                          key=key, n=usage.get("replay_n", 0))
        self.apply(tools, out, task)
        tools.log("agent_finished", getattr(out, "summary", ""),
                  **_usage_payload(self, usage, started, task))
        return out


def _usage_payload(agent: BaseAgent, usage: dict, started: float, task: dict) -> dict:
    """Payload of `agent_finished`: LLM usage of this run, duration, model and mode."""
    keys = ("calls", "input_tokens", "output_tokens", "cache_hits", "invalid_outputs")
    payload = {k: int(usage.get(k, 0)) for k in keys}
    payload.update(duration_ms=int((time.perf_counter() - started) * 1000), model=config.MODEL,
                   llm_mode=agent.llm.mode, story_id=task.get("story_id"))
    return payload


def _slug(text: str) -> str:
    """Lowercase words joined by '-', at most 40 characters."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")


class StubAgent(BaseAgent):
    """Placeholder so the orchestrator can run end to end before real agents exist."""

    def __init__(self, role: str, llm: LLMClient | None = None):
        super().__init__(llm or LLMClient(mock=True))
        self.role = role

    def build_prompt(self, db, project_id, task):
        return ""

    def apply(self, tools, out, task):
        pass
