import dataclasses
import os
import pathlib
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

import httpx
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

base_dir = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(base_dir / ".env")

DEFAULT_LOCAL_MODEL = "qwen3:1.7b-q4_K_M"
NOSANA_URL = "https://inference.nosana.com/v1"
MODEL_TYPES = ("OLLAMA", "NOSANA", "HYBRID")

# Which backend runs each node. HYBRID keeps routing and chat on the laptop and
# sends planning and tool use, where the small models fail, to Nosana.
ROLES = ("classify", "conversational", "plan", "execute")
HYBRID_ROLES = {"classify": "local", "conversational": "local", "plan": "nosana", "execute": "nosana"}
HYBRID_NUM_CTX = 8192  # the 2B at 8K is 3.6 GB, 100% GPU on a 4 GB card


@dataclass(frozen=True)
class Config:
    model_type: str
    nosana_model: str
    nosana_base_url: str
    nosana_timeout: float  # read timeout: the longest gap between streamed bytes
    nosana_max_retries: int
    ollama_model: str
    ollama_base_url: str
    ollama_timeout: float
    num_ctx: Optional[int]  # None keeps Ollama's default of 4,096
    reasoning: bool
    fallback: bool  # may a Nosana role fall back to the local model?
    cooldown_s: float  # how long a failed backend is skipped
    roles: Dict[str, str]

    @property
    def uses_nosana(self) -> bool:
        return "nosana" in self.roles.values()

    @property
    def uses_local(self) -> bool:
        return "local" in self.roles.values() or self.fallback


def _get(env: Mapping[str, str], key: str, default: str = "") -> str:
    return (env.get(key) or default).strip()


def _flag(env: Mapping[str, str], key: str, default: bool) -> bool:
    value = _get(env, key).lower()
    return default if not value else value in ("1", "true", "yes", "on")


def resolve_config(env: Mapping[str, str]) -> Config:
    """Read the settings from `env` (no network, no key check)."""
    model_type = _get(env, "MODEL_TYPE", "OLLAMA").upper()
    if model_type not in MODEL_TYPES:
        raise ValueError(f"Unknown MODEL_TYPE '{model_type}'. Use OLLAMA, NOSANA or HYBRID.")
    roles = {
        "OLLAMA": dict.fromkeys(ROLES, "local"),
        "NOSANA": dict.fromkeys(ROLES, "nosana"),
        "HYBRID": dict(HYBRID_ROLES),
    }[model_type]
    hybrid = model_type == "HYBRID"
    return Config(
        model_type=model_type,
        nosana_model=_get(env, "NOSANA_MODEL"),
        nosana_base_url=_get(env, "NOSANA_BASE_URL", NOSANA_URL).rstrip("/"),
        nosana_timeout=float(_get(env, "NOSANA_TIMEOUT", "60")),
        nosana_max_retries=int(_get(env, "NOSANA_MAX_RETRIES", "1")),
        ollama_model=_get(env, "OLLAMA_MODEL", DEFAULT_LOCAL_MODEL),
        ollama_base_url=_get(env, "OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_timeout=float(_get(env, "OLLAMA_TIMEOUT", "60")),
        num_ctx=int(_get(env, "OLLAMA_NUM_CTX", "0")) or (HYBRID_NUM_CTX if hybrid else None),
        # Thinking-only models (e.g. qwen3:4b = Qwen3-4B-Thinking-2507) ignore think=false and
        # leak their reasoning into the reply; "true" keeps it in a separate field instead.
        reasoning=_flag(env, "OLLAMA_REASONING", False),
        fallback=model_type != "OLLAMA" and _flag(env, "NOSANA_FALLBACK", hybrid),
        cooldown_s=float(_get(env, "NOSANA_COOLDOWN", "60")),
        roles=roles,
    )


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


def build_nosana(cfg: Config, api_key: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=cfg.nosana_model,
        base_url=cfg.nosana_base_url,
        api_key=api_key,
        # A dead node fails in 5 s; a hung one after 60 s without a byte, twice at most
        timeout=httpx.Timeout(cfg.nosana_timeout, connect=5.0),
        max_retries=cfg.nosana_max_retries,
        stream_usage=True,  # final chunk carries token counts (what you're billed on)
    )


def build_ollama(cfg: Config) -> ChatOllama:
    return ChatOllama(
        model=cfg.ollama_model,
        base_url=cfg.ollama_base_url,
        keep_alive=-1,
        reasoning=cfg.reasoning,
        num_ctx=cfg.num_ctx,
        client_kwargs={"timeout": cfg.ollama_timeout},
    )


def describe(cfg: Optional[Config] = None) -> str:
    """One line for the CLI header: which model does what."""
    cfg = cfg or CONFIG
    local = f"{cfg.ollama_model} (local)"
    nosana = f"{cfg.nosana_model} (Nosana)"
    if cfg.model_type == "HYBRID":
        line = f"hybrid · routing + chat: {local} · planning + tools: {nosana}"
        return line if cfg.fallback else line + " · no fallback"
    if cfg.model_type == "NOSANA":
        return nosana + (f" · fallback: {local}" if cfg.fallback else "")
    return local


CONFIG = resolve_config(os.environ)
MODEL_TYPE = CONFIG.model_type
REASONING = CONFIG.reasoning
NUM_CTX = CONFIG.num_ctx
API_KEY = None
nosana_llm = None
local_llm = None

if CONFIG.uses_nosana:
    API_KEY = _get(os.environ, "NOSANA_API_KEY")
    if not API_KEY.startswith("nos_"):
        raise RuntimeError("NOSANA_API_KEY missing or invalid (must start with 'nos_').")
    if not CONFIG.nosana_model:
        CONFIG = dataclasses.replace(
            CONFIG, nosana_model=_pick_nosana_model(CONFIG.nosana_base_url, API_KEY)
        )
    nosana_llm = build_nosana(CONFIG, API_KEY)

if CONFIG.uses_local:
    local_llm = build_ollama(CONFIG)

# Kept for older callers: the "main" model is Nosana whenever Nosana is used.
llm = nosana_llm if nosana_llm is not None else local_llm
MODEL_NAME = CONFIG.nosana_model if CONFIG.uses_nosana else CONFIG.ollama_model
BASE_URL = CONFIG.nosana_base_url if CONFIG.uses_nosana else CONFIG.ollama_base_url
LOCAL_MODEL_NAME = CONFIG.ollama_model if local_llm is not None else None


if __name__ == "__main__":
    print(f"[{MODEL_TYPE}] {describe()}")
    for chunk in llm.stream("hello"):
        print(chunk.content, end="", flush=True)
    print()
