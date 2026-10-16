"""Single place to plug real agents into the orchestrator.

Replace a StubAgent by adding the real agent here, e.g.
    from workbench.agents.product_owner import ProductOwnerAgent
    AGENTS["product_owner"] = ProductOwnerAgent()
Roles not listed fall back to StubAgent."""

from workbench.agents.architect import ArchitectAgent
from workbench.agents.base import BaseAgent
from workbench.agents.developer import DeveloperAgent
from workbench.agents.devops import DevOpsAgent
from workbench.agents.product_owner import ProductOwnerAgent
from workbench.agents.qa import QAAgent
from workbench.agents.scrum_master import ScrumMasterAgent

_developer = DeveloperAgent()

AGENTS: dict[str, BaseAgent] = {
    "product_owner": ProductOwnerAgent(),
    "scrum_master": ScrumMasterAgent(),
    "architect": ArchitectAgent(),
    "developer": _developer,
    "qa": QAAgent(developer=_developer),  # QA asks the Developer to fix the bugs it files
    "devops": DevOpsAgent(),
}
