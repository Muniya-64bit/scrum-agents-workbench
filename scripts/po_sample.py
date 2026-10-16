"""Run the Product Owner agent once and print the resulting backlog as Markdown.

    python scripts/po_sample.py "A simple to-do app" > docs/samples/product_owner.md

Uses the mode set in .env (MOCK_LLM=1 canned output, MOCK_LLM=0 real Claude call).
Uses an in-memory database, so nothing is written to workbench.db."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from workbench import config  # noqa: E402
from workbench.agents.product_owner import ProductOwnerAgent  # noqa: E402
from workbench.db import models as m  # noqa: E402
from workbench.db import repo  # noqa: E402
from workbench.db.session import init_db, make_engine  # noqa: E402


def main(idea: str) -> None:
    engine = make_engine("sqlite://")
    init_db(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        p = repo.create_project(db, "Sample", idea)
        ProductOwnerAgent().run(db, p.id)
        db.refresh(p)
        mode = "mock (canned output)" if config.MOCK_LLM else f"real run, model {config.MODEL}"
        print(f"# Product Owner sample\n\n- Idea: {idea}\n- Mode: {mode}\n")
        print(f"## Vision\n{p.vision}\n")
        for epic in repo.list_for_project(db, p.id, m.Epic):
            print(f"## Epic: {epic.title}\n{epic.description}\n")
            for s in epic.stories:
                print(f"### {s.title} (priority {s.priority}, {s.points} points)")
                print(f"As a {s.as_a}, I want {s.i_want}, so that {s.so_that}.\n")
                for c in s.acceptance_criteria:
                    print(f"- {c}")
                print()


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "A simple to-do app")
