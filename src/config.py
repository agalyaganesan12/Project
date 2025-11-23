# src/config.py
import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings


# ------------ ENV LOADING ------------

def load_envs() -> None:
    """
    Load environment variables and print a small confirmation.
    Call this once at app startup.
    """
    load_dotenv()

    missing = []
    required = ["OPENAI_API_KEY", "NEON_DB_URL", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]
    for key in required:
        if not os.getenv(key):
            missing.append(key)

    if missing:
        # Don't crash, but it's good to know.
        print("⚠️ Missing env vars:", ", ".join(missing))
    else:
        print("Environment variables loaded and validated successfully.")


# Load immediately when this module is imported
load_envs()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEON_DB_URL = os.getenv("NEON_DB_URL")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


# ------------ LLM & EMBEDDINGS ------------

# You can change models here if you want
LLM_MODEL_NAME = "gpt-3.5-turbo"
EMBEDDING_MODEL_NAME = "text-embedding-3-large"

llm = ChatOpenAI(
    model=LLM_MODEL_NAME,
    temperature=0.2,
    api_key=OPENAI_API_KEY,
)

# Separate LLM for vision tasks (GPT-3.5-turbo does NOT support images)
llm_vision = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2,
    api_key=OPENAI_API_KEY,
)

embeddings = OpenAIEmbeddings(
    model=EMBEDDING_MODEL_NAME,
    api_key=OPENAI_API_KEY,
)
