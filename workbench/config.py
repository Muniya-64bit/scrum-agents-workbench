import os

from dotenv import load_dotenv

load_dotenv()

LLM_MODES = ("mock", "live", "record", "replay")
LLM_FALLBACKS = ("error", "mock")
LLM_PROVIDERS = ("anthropic", "ollama")


def _choice(name: str, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValueError(f"{name}={value!r} is invalid; allowed values: {', '.join(allowed)}")
    return value

MODEL = os.getenv("WORKBENCH_MODEL", "claude-sonnet-5-5")


def model_for(role: str) -> str:
    """Model of one agent role: WORKBENCH_MODEL_<ROLE> (for example WORKBENCH_MODEL_DEVELOPER),
    else WORKBENCH_MODEL. A code model for Developer and QA and a general one for the rest is a
    typical split on a local server."""
    return os.getenv(f"WORKBENCH_MODEL_{role.upper()}") or MODEL


# LLM_MODE wins; without it MOCK_LLM=1 means mock and MOCK_LLM=0 means live (back-compat)
LLM_MODE = _choice("LLM_MODE", os.getenv("LLM_MODE")
                   or ("mock" if os.getenv("MOCK_LLM", "1") == "1" else "live"), LLM_MODES)
# True when no live model runs: mock and replay (also keeps the DevOps agent from docker builds)
MOCK_LLM = LLM_MODE in ("mock", "replay")
LLM_SCENARIO_DIR = os.getenv("LLM_SCENARIO_DIR", "")
LLM_REPLAY_FALLBACK = _choice("LLM_REPLAY_FALLBACK", os.getenv("LLM_REPLAY_FALLBACK", "error"),
                              LLM_FALLBACKS)
# Which backend answers live calls: the Claude API, or a local Ollama server (no API key needed)
LLM_PROVIDER = _choice("LLM_PROVIDER", os.getenv("LLM_PROVIDER", "anthropic"), LLM_PROVIDERS)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "1800"))
# When set, every endpoint except /health needs `Authorization: Bearer <token>` (or ?token=...,
# which a browser EventSource needs). Empty means no authentication: run it locally.
API_TOKEN = os.getenv("WORKBENCH_API_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./workbench.db")
WORKSPACES_DIR = os.getenv("WORKSPACES_DIR", "./workspaces")
DEFAULT_MAX_FIX_RETRIES = int(os.getenv("DEFAULT_MAX_FIX_RETRIES", "3"))
DEFAULT_CAPACITY = int(os.getenv("DEFAULT_CAPACITY", "10"))
MAX_SPRINTS = int(os.getenv("MAX_SPRINTS", "3"))
LLM_PRICE_INPUT_PER_MTOK = float(os.getenv("LLM_PRICE_INPUT_PER_MTOK", "2.0"))
LLM_PRICE_OUTPUT_PER_MTOK = float(os.getenv("LLM_PRICE_OUTPUT_PER_MTOK", "10.0"))
