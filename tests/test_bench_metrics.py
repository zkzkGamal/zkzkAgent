import types
import uuid

import httpx
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tests.fakes import ScriptedChatModel, install, tool_call

ROUTE_DIRECT = AIMessage(content='{"route": "DIRECT_EXECUTION", "rationale": "one step"}')
PRICE = (0.20, 2.00)


def _row(success=True, nosana=(1, 400, 50), local=(3, 600, 50), **extra):
    return {
        "backend": "hybrid", "success": success, "tokens_in": nosana[1] + local[1],
        "tokens_out": nosana[2] + local[2],
        "by_backend": {
            "nosana": {"calls": nosana[0], "tokens_in": nosana[1], "tokens_out": nosana[2]},
            "local": {"calls": local[0], "tokens_in": local[1], "tokens_out": local[2]},
        },
        **extra,
    }


def test_run_cost_counts_only_nosana_tokens():
    from benchmark.report import run_cost

    assert abs(run_cost(_row(), PRICE) - (400 * 0.20 + 50 * 2.00) / 1e6) < 1e-12
    assert abs(run_cost({"tokens_in": 1000, "tokens_out": 10}, PRICE) - (1000 * 0.2 + 10 * 2) / 1e6) < 1e-12


def test_split_section_shares():
    from benchmark.report import split_section

    rows = [_row(), _row(success=False, fallback_calls=2, interruptions=1)]
    lines = split_section(rows, ["hybrid"], {"hybrid": PRICE})
    hybrid = next(line for line in lines if line.startswith("| hybrid"))
    cells = [c.strip() for c in hybrid.strip("|").split("|")]
    assert cells[1:6] == ["8", "6", "2", "75%", "59%"]  # calls, local, nosana, share of calls, of tokens
    assert cells[6:8] == ["2", "1"]  # fallback calls, interrupted runs
    assert cells[8] == "$0.0004"  # 2 runs × $0.00018, over 1 successful task


def test_split_section_skips_old_rows():
    from benchmark.report import split_section

    assert split_section([{"backend": "nosana", "success": True}], ["nosana"], {}) == []


def test_meter_tags_calls_by_backend():
    from benchmark.run_one import Meter

    meter = Meter()
    for kind, tokens in (("openai-chat", 100), ("chat-ollama", 30)):
        run_id = uuid.uuid4()
        meter.on_chat_model_start({}, [[]], run_id=run_id, invocation_params={"_type": kind})
        message = AIMessage(content="x", usage_metadata={
            "input_tokens": tokens, "output_tokens": 5, "total_tokens": tokens + 5,
        })
        meter.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=run_id)
    by_backend = meter.as_row()["by_backend"]
    assert by_backend["nosana"] == {"calls": 1, "tokens_in": 100, "tokens_out": 5, "errors": 0}
    assert by_backend["local"] == {"calls": 1, "tokens_in": 30, "tokens_out": 5, "errors": 0}


def test_driver_continues_once_after_interruption(tmp_path, monkeypatch):
    from benchmark import guards
    from benchmark.run_one import Meter, run_conversation
    from core.agent import app

    monkeypatch.setattr(guards, "_sandbox", tmp_path)
    install(
        local=ScriptedChatModel(script=[ROUTE_DIRECT, AIMessage(content="done locally")]),
        nosana=ScriptedChatModel(script=[
            tool_call("get_files_info", {"working_directory": str(tmp_path)}, "c1"),
            httpx.ConnectError("refused"),
        ]),
    )
    talk = run_conversation(app, types.SimpleNamespace(follow_up=None), "list it", Meter())
    assert talk["continues"] == 1
    assert talk["state"]["messages"][-1].content == "done locally"


def _warm(capsys):
    from benchmark.run_one import warm_up
    from core.agent import app

    row = {"backend": "test", "task": "warmup", "success": False, "error": None}
    code = warm_up(app, row)
    capsys.readouterr()
    return code, row


def test_warmup_fails_when_a_backend_is_down(capsys):
    install(
        local=ScriptedChatModel(script=[
            AIMessage(content='{"route": "CONVERSATIONAL", "rationale": "x"}'),
            AIMessage(content="hello"), AIMessage(content="OK"),
        ]),
        nosana=ScriptedChatModel(script=[httpx.ConnectError("down")]),
    )
    code, row = _warm(capsys)
    assert code == 1 and "Nosana" in row["error"] and "ConnectError" in row["error"]


def test_warmup_passes_when_every_backend_answers(capsys):
    install(
        local=ScriptedChatModel(script=[
            AIMessage(content='{"route": "CONVERSATIONAL", "rationale": "x"}'),
            AIMessage(content="hello"), AIMessage(content="OK"),
        ]),
        nosana=ScriptedChatModel(script=[AIMessage(content="OK")]),
    )
    code, row = _warm(capsys)
    assert code == 0 and row["success"] is True
