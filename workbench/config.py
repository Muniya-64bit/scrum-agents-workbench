import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("WORKBENCH_MODEL", "claude-sonnet-5-5")
MOCK_LLM = os.getenv("MOCK_LLM", "1") == "1"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./workbench.db")
WORKSPACES_DIR = os.getenv("WORKSPACES_DIR", "./workspaces")
DEFAULT_MAX_FIX_RETRIES = int(os.getenv("DEFAULT_MAX_FIX_RETRIES", "3"))
DEFAULT_CAPACITY = int(os.getenv("DEFAULT_CAPACITY", "10"))
MAX_SPRINTS = int(os.getenv("MAX_SPRINTS", "3"))
LLM_PRICE_INPUT_PER_MTOK = float(os.getenv("LLM_PRICE_INPUT_PER_MTOK", "2.0"))
LLM_PRICE_OUTPUT_PER_MTOK = float(os.getenv("LLM_PRICE_OUTPUT_PER_MTOK", "10.0"))
