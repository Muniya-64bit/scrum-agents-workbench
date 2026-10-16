"""Single place to plug real agents into the orchestrator.

Replace a StubAgent by adding the real agent here, e.g.
    from workbench.agents.product_owner import ProductOwnerAgent
    AGENTS["product_owner"] = ProductOwnerAgent()
Roles not listed fall back to StubAgent."""

from workbench.agents.base import BaseAgent
from workbench.agents.developer import DeveloperAgent
from workbench.agents.qa import QAAgent

_developer = DeveloperAgent()

AGENTS: dict[str, BaseAgent] = {
    "developer": _developer,
    "qa": QAAgent(developer=_developer),  # QA asks the Developer to fix the bugs it files
}
