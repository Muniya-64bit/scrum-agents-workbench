import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("WORKBENCH_MODEL", "claude-sonnet-5-5")
MOCK_LLM = os.getenv("MOCK_LLM", "1") == "1"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./workbench.db")
WORKSPACES_DIR = os.getenv("WORKSPACES_DIR", "./workspaces")
