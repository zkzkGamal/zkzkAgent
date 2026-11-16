import httpx
import pytest
from langchain_core.messages import AIMessage

from models.LLM import resolve_config
from models import selector as model_selector
from models.selector import AllBackendsFailed, run_role
from tests.fakes import FakeClock, ScriptedChatModel, StatusError, install, make_selector

HYBRID_ENV = {
    "MODEL_TYPE": "HYBRID",
    "OLLAMA_MODEL": "qwen3.5:2b-q4_K_M",
    "NOSANA_MODEL": "qwen/qwen3.8-27b",
}


# ---- config ---------------------------------------------------------------
def test_resolve_hybrid_defaults():
    cfg = resolve_config(HYBRID_ENV)
    assert cfg.roles == {
        "classify": "local", "conversational": "local", "plan": "nosana", "execute": "nosana",
    }
    assert cfg.num_ctx == 8192
    assert cfg.fallback is True
    assert cfg.nosana_timeout == 60
    assert cfg.nosana_max_retries == 1
    assert cfg.cooldown_s == 60
    assert cfg.ollama_timeout == 60


def test_resolve_nosana_defaults():
    cfg = resolve_config({"MODEL_TYPE": "NOSANA", "NOSANA_MODEL": "qwen/qwen3.8-27b"})
    assert set(cfg.roles.values()) == {"nosana"}
    assert cfg.fallback is False
    assert cfg.num_ctx is None


def test_resolve_env_overrides():
    cfg = resolve_config({**HYBRID_ENV, "OLLAMA_NUM_CTX": "4096", "NOSANA_FALLBACK": "false",
                          "NOSANA_TIMEOUT": "30", "OLLAMA_TIMEOUT": "120"})
    assert (cfg.num_ctx, cfg.fallback, cfg.nosana_timeout, cfg.ollama_timeout) == (4096, False, 30, 120)


def test_resolve_unknown_type_raises():
    with pytest.raises(ValueError):
        resolve_config({"MODEL_TYPE": "FOO"})


# ---- breaker and order -----------------------------------------------------
def test_order_primary_then_fallback():
    sel = make_selector(nosana=ScriptedChatModel(), local=ScriptedChatModel())
    assert sel.order("plan") == ["nosana", "local"]
    assert sel.order("classify") == ["local", "nosana"]


def test_order_without_fallback_is_primary_only():
    sel = make_selector(nosana=ScriptedChatModel(), local=ScriptedChatModel(), fallback=False)
    sel.record("plan", "nosana", httpx.ConnectError("down"))
    assert sel.order("plan") == ["nosana"]


def test_order_skips_open_breaker():
    sel = make_selector(nosana=ScriptedChatModel(), local=ScriptedChatModel())
    sel.record("plan", "nosana", httpx.ConnectError("down"))
    assert sel.order("plan") == ["local"]


def test_breaker_reopens_after_cooldown():
    clock = FakeClock()
    sel = make_selector(nosana=ScriptedChatModel(), local=ScriptedChatModel(), clock=clock)
    sel.record("plan", "nosana", httpx.ConnectError("down"))
    clock.now += 61
    assert sel.order("plan") == ["nosana", "local"]


def test_auth_error_keeps_breaker_open():
    clock = FakeClock()
    install(
        nosana=ScriptedChatModel(script=[StatusError(401, "invalid api key")]),
        local=ScriptedChatModel(script=[ConnectionError("ollama down")]),
        clock=clock,
    )
    with pytest.raises(AllBackendsFailed) as failed:
        run_role("plan", lambda chat, backend: chat.invoke("hi"))
    clock.now += 10_000
    assert model_selector.current().order("execute") == ["local"]
    assert "NOSANA_API_KEY" in failed.value.user_message()


def test_other_error_keeps_breaker_closed():
    sel = make_selector(nosana=ScriptedChatModel(), local=ScriptedChatModel())
    sel.record("plan", "nosana", StatusError(400, "bad request"))
    assert sel.order("plan") == ["nosana", "local"]


def test_success_closes_breaker():
    sel = make_selector(nosana=ScriptedChatModel(), local=ScriptedChatModel())
    sel.record("plan", "nosana", httpx.ConnectError("down"))
    sel.reset("nosana")
    assert sel.order("plan") == ["nosana", "local"]


# ---- run_role --------------------------------------------------------------
def test_run_role_falls_back_and_records():
    sel = install(
        nosana=ScriptedChatModel(script=[ConnectionError("refused")]),
        local=ScriptedChatModel(script=[AIMessage(content="local plan")]),
    )
    result = run_role("plan", lambda chat, backend: chat.invoke("hi").content)
    assert result == "local plan"
    assert sel.events[0]["ok"] is False and sel.events[0]["backend"] == "nosana"
    assert sel.events[-1] == {
        "role": "plan", "backend": "local", "ok": True, "error": None, "kind": None, "fallback": True,
    }


def test_run_role_all_fail():
    install(
        nosana=ScriptedChatModel(script=[httpx.ReadTimeout("slow")]),
        local=ScriptedChatModel(script=[ConnectionError("ollama down")]),
    )
    with pytest.raises(AllBackendsFailed) as failed:
        run_role("plan", lambda chat, backend: chat.invoke("hi"))
    text = failed.value.user_message()
    for part in ("Nosana (qwen/qwen3.8-27b)", "local (qwen3.5:2b-q4_K_M)", "ReadTimeout", "ConnectionError"):
        assert part in text


def test_label():
    sel = make_selector(nosana=ScriptedChatModel(), local=ScriptedChatModel())
    assert sel.label("nosana") == "Nosana (qwen/qwen3.8-27b)"
    assert sel.label("local") == "local (qwen3.5:2b-q4_K_M)"
    assert sel.other("nosana") == "local"
