from langchain_ollama import ChatOllama
import environ , pathlib , os

base_dir = pathlib.Path(__file__).parent.parent
env = environ.Env()
environ.Env.read_env(base_dir / ".env")

MODEL_NAME = (os.getenv("OLLAMA_MODEL") or "qwen3:1.7b-q4_K_M").strip()
BASE_URL = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip()

llm = ChatOllama(
    model=MODEL_NAME,
    timeout=30,
    base_url=BASE_URL,
    use_mmap=True,
    keep_alive=1000000,
    stream=True,
)
