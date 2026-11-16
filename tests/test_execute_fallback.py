import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from tests.fakes import LOCAL_ROLES, ScriptedChatModel, fresh_state, install, tool_call

ROUTE_DIRECT = AIMessage(content='{"route": "DIRECT_EXECUTION", "rationale": "one step"}')
ROUTE_PLAN = AIMessage(content='{"route": "NEEDS_PLANNING", "rationale": "many steps"}')
ROUTE_CHAT = AIMessage(content='{"route": "CONVERSATIONAL", "rationale": "chat"}')


def _send(app, state, text):
    state["messages"].append(HumanMessage(content=text))
    state["iteration_count"] = 0
    return app.invoke(state)


def _list_dir(tmp_path):
    return tool_call("get_files_info", {"working_directory": str(tmp_path), "directory": "."}, "c1")


def _interrupted_run(tmp_path, failure, local_script=()):
    from core.agent import app

    nosana = ScriptedChatModel(script=[_list_dir(tmp_path), failure])
    local = ScriptedChatModel(script=[ROUTE_DIRECT, *local_script])
    install(nosana=nosana, local=local)
    state = app.invoke(fresh_state(HumanMessage(content=f"what is in {tmp_path}?")))
    return app, state, nosana, local


def test_midtask_failure_keeps_progress(tmp_path):
    app, state, nosana, local = _interrupted_run(tmp_path, httpx.ConnectError("refused"))
    assert [m.tool_call_id for m in state["messages"] if isinstance(m, ToolMessage)] == ["c1"]
    assert state["interrupted"]["backend"] == "nosana"
    offer = state["messages"][-1].content
    assert "'retry'" in offer and "'continue'" in offer and "ConnectError" in offer
    assert "1 step" in offer


def test_midstream_drop_is_caught(tmp_path):
    app, state, nosana, local = _interrupted_run(tmp_path, ("Here is", httpx.ReadError("drop")))
    assert state["interrupted"]["backend"] == "nosana"
    assert "ReadError" in state["messages"][-1].content


def test_continue_hands_over_summary(tmp_path):
    app, state, nosana, local = _interrupted_run(
        tmp_path, httpx.ConnectError("refused"), local_script=[AIMessage(content="done")]
    )
    state = _send(app, state, "continue")
    sent = local.calls[-1]
    assert isinstance(sent[0], SystemMessage)
    assert "get_files_info" in sent[1].content and "taking over" in sent[1].content
    assert [m.content for m in sent[2:]] == ["continue"]
    assert state["messages"][-1].content == "done"
    assert state["takeover"] is None and state["interrupted"] is None


def test_retry_uses_full_history(tmp_path):
    app, state, nosana, local = _interrupted_run(tmp_path, httpx.ConnectError("refused"))
    nosana.script.append(AIMessage(content="finished"))
    state = _send(app, state, "retry")
    sent = nosana.calls[-1]
    assert any(isinstance(m, ToolMessage) and m.tool_call_id == "c1" for m in sent)
    assert "already ran" in sent[-1].content and "get_files_info" in sent[-1].content
    assert state["messages"][-1].content == "finished"
    assert state["interrupted"] is None


def test_failure_before_first_step():
    from core.agent import app

    nosana = ScriptedChatModel(script=[
        AIMessage(content="1. List the folder."),
        httpx.ConnectError("refused"),
        AIMessage(content="done"),
    ])
    install(nosana=nosana, local=ScriptedChatModel(script=[ROUTE_PLAN]))
    state = app.invoke(fresh_state(HumanMessage(content="tidy my project")))
    state = _send(app, state, "ok")
    assert "No steps" in state["messages"][-1].content
    state = _send(app, state, "retry")
    sent = nosana.calls[-1]
    assert any("1. List the folder." in str(m.content) for m in sent)
    assert "are done" not in sent[-1].content and "already ran" not in sent[-1].content
    assert "Nothing has run yet" in sent[-1].content and "plan" in sent[-1].content
    assert state["messages"][-1].content == "done"


def test_new_turn_uses_local_while_breaker_open(tmp_path):
    app, state, nosana, local = _interrupted_run(
        tmp_path, httpx.ConnectError("refused"),
        local_script=[ROUTE_DIRECT, AIMessage(content="It is noon.")],
    )
    state = _send(app, state, "what time is it?")
    sent = local.calls[-1]
    assert [type(m).__name__ for m in sent] == ["SystemMessage", "HumanMessage"]
    assert sent[1].content == "what time is it?"
    assert state["messages"][-1].content == "It is noon."
    assert state["interrupted"] is None


def test_new_request_after_interruption_clears_it(tmp_path):
    app, state, nosana, local = _interrupted_run(
        tmp_path, httpx.ConnectError("refused"),
        local_script=[ROUTE_CHAT, AIMessage(content="Why did the chicken…")],
    )
    state = _send(app, state, "tell me a joke")
    assert state["messages"][-1].content == "Why did the chicken…"
    assert state["interrupted"] is None and state["takeover"] is None


def test_local_failure_offers_retry_only():
    from core.agent import app
    from tests.fakes import make_selector
    from models import selector

    local = ScriptedChatModel(script=[ROUTE_DIRECT, httpx.ReadTimeout("slow")])
    selector.install(make_selector(local=local, roles=LOCAL_ROLES, fallback=False))
    state = app.invoke(fresh_state(HumanMessage(content="which kernel?")))
    offer = state["messages"][-1].content
    assert "'retry'" in offer and "'continue'" not in offer
    assert state["interrupted"]["backend"] == "local"


def test_auth_failure_offer_names_the_key():
    from core.agent import app
    from tests.fakes import StatusError

    install(
        nosana=ScriptedChatModel(script=[StatusError(401, "invalid api key")]),
        local=ScriptedChatModel(script=[ROUTE_DIRECT]),
    )
    state = app.invoke(fresh_state(HumanMessage(content="which kernel?")))
    offer = state["messages"][-1].content
    assert "NOSANA_API_KEY" in offer and "credits" in offer
    assert "'continue'" in offer


def test_plan_note_gives_the_reason():
    from agent_nodes.plan_node import plan_node
    from tests.fakes import StatusError

    install(
        nosana=ScriptedChatModel(script=[StatusError(401, "invalid api key")]),
        local=ScriptedChatModel(script=[AIMessage(content="1. Do it.")]),
    )
    result = plan_node(fresh_state(HumanMessage(content="build it")))
    assert "NOSANA_API_KEY" in result["pending_plan"]
