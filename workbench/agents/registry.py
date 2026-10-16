"""Single place to plug real agents into the orchestrator.

Replace a StubAgent by adding the real agent here, e.g.
    from workbench.agents.product_owner import ProductOwnerAgent
    AGENTS["product_owner"] = ProductOwnerAgent()
Roles not listed fall back to StubAgent."""

from workbench.agents.architect import ArchitectAgent
from workbench.agents.base import BaseAgent
from workbench.agents.product_owner import ProductOwnerAgent
from workbench.agents.scrum_master import ScrumMasterAgent

AGENTS: dict[str, BaseAgent] = {
    "architect": ArchitectAgent(),
    "product_owner": ProductOwnerAgent(),
    "scrum_master": ScrumMasterAgent(),
}
