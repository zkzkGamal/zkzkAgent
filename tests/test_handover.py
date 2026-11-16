from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_nodes.handover import PLAN_HINT, build_handover, done_steps, plan_text, task_start


def _task(plan: str = "1. List the folder.\n2. Write app.py."):
    return [
        HumanMessage(content="an older request"),
        AIMessage(content="older answer"),
        HumanMessage(content="build a calculator in /tmp/calc"),
        AIMessage(content=plan + PLAN_HINT),
        HumanMessage(content="ok"),
        AIMessage(content="", tool_calls=[
            {"name": "get_files_info", "args": {"working_directory": "/tmp/calc"}, "id": "c1"},
        ]),
        ToolMessage(content="- app.py: file_size=10", tool_call_id="c1"),
        HumanMessage(content="I'm about to run…", additional_kwargs={"zkzk": "confirm"}),
        HumanMessage(content="yes"),
        HumanMessage(content="continue"),
    ]


def test_task_start_skips_control_replies():
    assert task_start(_task()) == 2
    assert task_start([AIMessage(content="hi")]) == 0


def test_plan_text_strips_the_hint():
    assert plan_text(_task(), 2) == "1. List the folder.\n2. Write app.py."
    assert plan_text(_task()[:3], 2) is None


def test_done_steps_lists_tool_calls_that_ran():
    steps = done_steps(_task(), 2)
    assert len(steps) == 1
    assert steps[0].startswith("get_files_info(working_directory=/tmp/calc) → - app.py")


def test_build_handover_is_short_and_complete():
    messages = _task(plan="x" * 20_000)
    text = build_handover(messages, 2, "Nosana (qwen/qwen3.8-27b) stopped: ConnectError: refused")
    assert len(text) <= 6000
    assert "build a calculator in /tmp/calc" in text
    assert "get_files_info" in text
    assert "ConnectError" in text
    assert text.rstrip().endswith("then reply with a short summary.")
