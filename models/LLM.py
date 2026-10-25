import os
import pathlib

import httpx
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

base_dir = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(base_dir / ".env")

DEFAULT_LOCAL_MODEL = "qwen3:1.7b-q4_K_M"
NOSANA_URL = "https://inference.nosana.com/v1"

MODEL_TYPE = (os.getenv("MODEL_TYPE") or "OLLAMA").strip().upper()


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _pick_nosana_model(base_url: str, api_key: str) -> str:
    """Models are only listed while a GPU is serving them, so pick a live one."""
    r = httpx.get(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    r.raise_for_status()
    models = [m for m in r.json()["data"] if m.get("available", True)]
    if not models:
        raise RuntimeError("No Nosana models are being served right now.")
    return models[0]["id"]


if MODEL_TYPE == "NOSANA":
    API_KEY = _env("NOSANA_API_KEY")
    if not API_KEY.startswith("nos_"):
        raise RuntimeError("NOSANA_API_KEY missing or invalid (must start with 'nos_').")
    BASE_URL = _env("NOSANA_BASE_URL", NOSANA_URL).rstrip("/")
    MODEL_NAME = _env("NOSANA_MODEL") or _pick_nosana_model(BASE_URL, API_KEY)

    llm = ChatOpenAI(
        model=MODEL_NAME,
        base_url=BASE_URL,
        api_key=API_KEY,
        timeout=120,
        max_retries=2,
        stream_usage=True,  # final chunk carries token counts (what you're billed on)
    )

elif MODEL_TYPE == "OLLAMA":
    MODEL_NAME = _env("OLLAMA_MODEL", DEFAULT_LOCAL_MODEL)
    BASE_URL = _env("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    llm = ChatOllama(
        model=MODEL_NAME,
        base_url=BASE_URL,
        keep_alive=-1,
        reasoning=False,
        client_kwargs={"timeout": 60},
    )
else:
    raise ValueError(f"Unknown MODEL_TYPE '{MODEL_TYPE}'. Use OLLAMA or NOSANA.")


if __name__ == "__main__":
    print(f"[{MODEL_TYPE}] {MODEL_NAME} @ {BASE_URL}")
    for chunk in llm.stream("hello"):
        print(chunk.content, end="", flush=True)
    print()