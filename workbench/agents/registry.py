"""Single place to plug real agents into the orchestrator.

Replace a StubAgent by adding the real agent here, e.g.
    from workbench.agents.product_owner import ProductOwnerAgent
    AGENTS["product_owner"] = ProductOwnerAgent()
Roles not listed fall back to StubAgent."""

from workbench.agents.architect import ArchitectAgent
from workbench.agents.base import BaseAgent

AGENTS: dict[str, BaseAgent] = {
    "architect": ArchitectAgent(),
}
