"""Scripted chat models and selectors for offline tests."""

import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

HYBRID_ROLES = {
    "classify": "local",
    "conversational": "local",
    "plan": "nosana",
    "execute": "nosana",
}
NAMES = {"nosana": "qwen/qwen3.8-27b", "local": "qwen3.5:2b-q4_K_M"}


class StatusError(Exception):
    """An API error that carries an HTTP status, like openai.APIStatusError."""

    def __init__(self, status_code: int, message: str = "status error"):
        super().__init__(f"{status_code}: {message}")
        self.status_code = status_code


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class ScriptedChatModel(BaseChatModel):
    """Plays back a script, one item per call.

    AIMessage → returned; Exception → raised; (text, Exception) → `text` is
    streamed, then the exception is raised (a reply that drops mid-stream).
    """

    script: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)
    tool_binds: list = Field(default_factory=list)  # number of tools per bind_tools() call

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.tool_binds.append(len(tools))
        return self

    def _next(self, messages):
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError("ScriptedChatModel: script exhausted")
        return self.script.pop(0)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        item = self._next(messages)
        if isinstance(item, tuple):
            raise item[1]
        if isinstance(item, BaseException):
            raise item
        return ChatResult(generations=[ChatGeneration(message=item)])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        item = self._next(messages)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, tuple):
            text, error = item
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
            raise error
        chunk = AIMessageChunk(
            content=item.content,
            tool_call_chunks=[
                {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
                for i, c in enumerate(item.tool_calls)
            ],
        )
        yield ChatGenerationChunk(message=chunk)


def tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


NOSANA_ROLES = {role: "nosana" for role in HYBRID_ROLES}
LOCAL_ROLES = {role: "local" for role in HYBRID_ROLES}


def fresh_state(*messages):
    from chat_cli.session import ChatSession

    state = ChatSession.fresh_state()
    state["messages"] = list(messages)
    return state


def make_selector(nosana=None, local=None, roles=None, fallback=True, clock=None, cooldown_s=60.0):
    from models.selector import ModelSelector

    models = {k: v for k, v in {"nosana": nosana, "local": local}.items() if v is not None}
    return ModelSelector(
        models=models,
        names={k: NAMES[k] for k in models},
        roles=dict(roles or HYBRID_ROLES),
        fallback=fallback,
        cooldown_s=cooldown_s,
        clock=clock or FakeClock(),
    )


def install(**kwargs):
    from models import selector

    sel = make_selector(**kwargs)
    selector.install(sel)
    return sel
