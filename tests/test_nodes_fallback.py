import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tests.fakes import NOSANA_ROLES, ScriptedChatModel, fresh_state, install

ROUTE_CHAT = AIMessage(content='{"route": "CONVERSATIONAL", "rationale": "small talk"}')
ROUTE_DIRECT = AIMessage(content='{"route": "DIRECT_EXECUTION", "rationale": "one step"}')


def test_classify_falls_back_to_other_backend():
    from agent_nodes.classify_node import classify_node

    install(
        local=ScriptedChatModel(script=[ConnectionError("ollama down")]),
        nosana=ScriptedChatModel(script=[ROUTE_DIRECT]),
    )
    result = classify_node(fresh_state(HumanMessage(content="which kernel is this?")))
    assert result["category"] == "DIRECT_EXECUTION"


def test_classify_both_down():
    from core.agent import app

    install(
        local=ScriptedChatModel(script=[ConnectionError("ollama down")]),
        nosana=ScriptedChatModel(script=[httpx.ConnectError("nosana down")]),
    )
    state = app.invoke(fresh_state(HumanMessage(content="hello")))
    last = state["messages"][-1]
    assert isinstance(last, AIMessage)
    assert "local (qwen3.5:2b-q4_K_M)" in last.content
    assert "Nosana (qwen/qwen3.8-27b)" in last.content
    assert state["category"] is None


def test_plan_falls_back_mid_stream():
    from agent_nodes.plan_node import plan_node

    install(
        nosana=ScriptedChatModel(script=[("1. Create the fol", httpx.ReadError("drop"))]),
        local=ScriptedChatModel(script=[AIMessage(content="1. Create the folder.\n2. Write app.py.")]),
    )
    result = plan_node(fresh_state(HumanMessage(content="build a calculator app")))
    assert result["pending_plan"].startswith("1. Create the folder.\n2. Write app.py.")
    assert "Planned by local (qwen3.5:2b-q4_K_M)" in result["pending_plan"]


def test_chat_has_no_tools_and_short_history_on_fallback():
    from agent_nodes.conversation_node import conversation_node

    nosana = ScriptedChatModel(script=[httpx.ConnectError("down")])
    local = ScriptedChatModel(script=[AIMessage(content="hi there")])
    install(nosana=nosana, local=local, roles=NOSANA_ROLES)
    history = [
        (HumanMessage if i % 2 == 0 else AIMessage)(content=f"message {i}") for i in range(10)
    ]
    result = conversation_node(fresh_state(*history))
    sent = local.calls[0]
    assert isinstance(sent[0], SystemMessage)
    assert [m.content for m in sent[1:]] == [f"message {i}" for i in range(4, 10)]
    assert nosana.tool_binds == [] and local.tool_binds == []
    assert result["messages"][-1].content == "hi there"


def test_execute_uses_selected_model():
    from core.agent import app

    nosana = ScriptedChatModel(script=[AIMessage(content="The kernel is 6.8.0.")])
    install(local=ScriptedChatModel(script=[ROUTE_DIRECT]), nosana=nosana)
    state = app.invoke(fresh_state(HumanMessage(content="which kernel is this?")))
    assert state["messages"][-1].content == "The kernel is 6.8.0."
    assert nosana.tool_binds and nosana.tool_binds[0] > 10  # the executor binds all tools
