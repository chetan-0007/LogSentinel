"""Central configuration read from environment variables.

Values are resolved at import time so the whole app shares one source of truth.
"""
import os

# --- LLM provider ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "claude-sonnet-4-5" if LLM_PROVIDER == "anthropic" else "llama-3.1-8b-instant",
)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
LLM_RETRY_DELAY_SECONDS = float(os.getenv("LLM_RETRY_DELAY_SECONDS", "2"))


# --- Kafka ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "logs")

# --- API base URL (used by the MCP server to reach FastAPI) ---
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# --- MCP server ---
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))

# --- Deployment ---
RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT")
