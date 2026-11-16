"""Which model answers each node, and what happens when one fails.

Every node has a role (classify, plan, conversational, execute) and each role
has a primary backend ("nosana" or "local", see models/LLM.py). Each backend
has a circuit breaker: after an outage it is skipped for a cooldown, so a dead
Nosana costs its timeout once, not on every call. A rejected API key keeps it
skipped until the agent restarts.

Stateless nodes (classify, plan, chat) use run_role(), which moves on to the
other backend at once. The executor never switches inside a task: see
agent_nodes/execute_node.py.
"""

import logging
import time
from typing import Callable, Dict, List, Optional, Tuple, TypeVar

import httpx

logger = logging.getLogger(__name__)
T = TypeVar("T")

_OUTAGE_TYPES: tuple = (httpx.TransportError, ConnectionError, TimeoutError)
try:
    import openai

    _OUTAGE_TYPES += (openai.APIConnectionError,)  # APITimeoutError is a subclass
except ImportError:  # pragma: no cover
    pass


def classify_error(exc: BaseException) -> str:
    """'auth' (bad key or no credits), 'outage' (worth skipping the backend) or 'other'."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status in (401, 403):
            return "auth"
        if status >= 500 or status in (408, 409, 429):
            return "outage"
        return "other"
    if isinstance(exc, _OUTAGE_TYPES):
        return "outage"
    return "other"


def error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:200]}"


AUTH_HINT = "Check NOSANA_API_KEY (restart after changing it) and your Nosana credits."


class Breaker:
    def __init__(self, cooldown_s: float, clock: Callable[[], float] = time.monotonic):
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._open_until = 0.0
        self.last_error: Optional[str] = None

    def available(self) -> bool:
        return self._clock() >= self._open_until

    def record(self, exc: Optional[BaseException]) -> None:
        if exc is None:
            self.reset()
            return
        kind = classify_error(exc)
        if kind == "other":  # a bad request or a bad reply, not a dead backend
            return
        self.last_error = error_text(exc)
        self._open_until = float("inf") if kind == "auth" else self._clock() + self.cooldown_s

    def reset(self) -> None:
        self._open_until = 0.0
        self.last_error = None


class AllBackendsFailed(RuntimeError):
    def __init__(self, errors: List[Tuple[str, BaseException]]):
        self.errors = errors  # (backend label, error), in the order they were tried
        super().__init__(self.user_message())

    def user_message(self) -> str:
        parts = " ".join(f"{label}: {error_text(exc).rstrip('.')}." for label, exc in self.errors)
        text = f"No model could answer. {parts}"
        if any(label.startswith("Nosana") and classify_error(exc) == "auth" for label, exc in self.errors):
            text += f" {AUTH_HINT}"
        return text


class ModelSelector:
    def __init__(self, models: Dict, names: Dict[str, str], roles: Dict[str, str],
                 fallback: bool, cooldown_s: float, clock: Callable[[], float] = time.monotonic):
        self.models = dict(models)
        self.names = dict(names)
        self.roles = dict(roles)
        self.fallback = fallback
        self.breakers = {backend: Breaker(cooldown_s, clock) for backend in self.models}
        self.events: List[dict] = []
        self._chains: Dict[tuple, object] = {}

    def primary(self, role: str) -> str:
        return self.roles[role]

    def other(self, backend: str) -> Optional[str]:
        return next((b for b in self.models if b != backend), None)

    def order(self, role: str) -> List[str]:
        """Backends to try for `role`, best first."""
        first = self.primary(role)
        second = self.other(first) if self.fallback else None
        if second is None:
            return [first]  # nothing to fall back to: always try the primary
        if self.breakers[first].available():
            return [first, second]
        if self.breakers[second].available():
            return [second]
        return [first, second]  # both marked down: try them anyway

    def chat(self, backend: str, tools: Optional[list] = None):
        key = (backend, tools is not None)
        if key not in self._chains:
            model = self.models[backend]
            self._chains[key] = model.bind_tools(tools) if tools is not None else model
        return self._chains[key]

    def label(self, backend: str) -> str:
        return f"{'Nosana' if backend == 'nosana' else 'local'} ({self.names.get(backend, '?')})"

    def record(self, role: str, backend: str, exc: Optional[BaseException]) -> None:
        self.breakers[backend].record(exc)
        self.events.append({
            "role": role,
            "backend": backend,
            "ok": exc is None,
            "error": error_text(exc) if exc is not None else None,
            "kind": classify_error(exc) if exc is not None else None,
            "fallback": backend != self.primary(role),
        })
        if exc is not None:
            logger.warning(f"[MODEL] {role} on {self.label(backend)} failed: {error_text(exc)}")

    def reset(self, backend: str) -> None:
        self.breakers[backend].reset()

    def last_failure(self, role: str, backend: str):
        """The latest failed event of `role` on `backend`, if any."""
        return next(
            (e for e in reversed(self.events) if e["role"] == role and e["backend"] == backend and not e["ok"]),
            None,
        )

    def why(self, role: str, backend: str) -> str:
        """Why `backend` could not serve `role`: its error, plus the key hint for a 401."""
        event = self.last_failure(role, backend)
        if event is None:
            return "it is marked unavailable after an earlier failure"
        return event["error"].rstrip(".") + (f". {AUTH_HINT}" if event["kind"] == "auth" else "")


def notice(text: str) -> None:
    print(f"\n[{text}]\n", flush=True)


def run_role(role: str, call: Callable[[object, str], T], tools: Optional[list] = None) -> T:
    """Run `call(chat_model, backend)` on the role's backends in order until one works."""
    sel = current()
    errors: List[Tuple[str, BaseException]] = []
    for backend in sel.order(role):
        if errors:
            label, exc = errors[-1]
            notice(f"{label} failed ({type(exc).__name__}) — using {sel.label(backend)}")
        try:
            result = call(sel.chat(backend, tools), backend)
        except Exception as exc:  # noqa: BLE001 — any model failure moves on
            sel.record(role, backend, exc)
            errors.append((sel.label(backend), exc))
            continue
        sel.record(role, backend, None)
        return result
    raise AllBackendsFailed(errors)


_current: Optional[ModelSelector] = None


def from_config() -> ModelSelector:
    from models import LLM

    models, names = {}, {}
    if LLM.nosana_llm is not None:
        models["nosana"], names["nosana"] = LLM.nosana_llm, LLM.CONFIG.nosana_model
    if LLM.local_llm is not None:
        models["local"], names["local"] = LLM.local_llm, LLM.CONFIG.ollama_model
    return ModelSelector(models, names, LLM.CONFIG.roles, LLM.CONFIG.fallback, LLM.CONFIG.cooldown_s)


def current() -> ModelSelector:
    global _current
    if _current is None:
        _current = from_config()
    return _current


def install(sel: ModelSelector) -> None:
    """Replace the selector (tests, benchmark harnesses)."""
    global _current
    _current = sel
