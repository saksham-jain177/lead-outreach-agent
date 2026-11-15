"""Config: tiny .env loader (no python-dotenv dependency)."""
import os

DEFAULT_MODEL_CHAIN = (
    "google/gemma-4-31b-it:free,"
    "nvidia/nemotron-3.5-lightning:free,"
    "inclusionai/ling-3.2-flash:free"
)


def load_env(path=".env"):
    """Parse a simple KEY=VALUE .env file into os.environ (existing vars win)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def cfg(key, default=""):
    return os.environ.get(key, default)


def model_chain():
    raw = cfg("OPENROUTER_MODELS", DEFAULT_MODEL_CHAIN)
    return [m.strip() for m in raw.split(",") if m.strip()]


load_env()
